"""NeuroFlow API: async FastAPI app."""

import logging
import time
from contextlib import asynccontextmanager

from db.pool import get_pool
from resilience.circuit_breaker import CircuitBreaker, get_redis
from resilience.backpressure import queue_depth

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from arq import create_pool
from arq.connections import RedisSettings



from api import ingest, query, runs, pipelines, compare, analytics
from api.finetune import router as finetune_router

from config import get_settings
from db import health, migrations, pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("neuroflow")

DEPENDENCY_UP = Gauge(
    "neuroflow_dependency_up",
    "1 if the last health check of the dependency passed, else 0",
    ["dependency"],
)


def setup_tracing() -> None:
    settings = get_settings()
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


setup_tracing()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    await pool.create_pool()
    applied = await migrations.apply_schema()
    app.state.arq = await create_pool(
        RedisSettings(host=settings.redis_host, port=settings.redis_port, password=settings.redis_password),
        default_queue_name="queue:ingest",
    )
    logger.info("Startup complete (schema applied now: %s)", applied)
    yield
    # Shutdown
    await app.state.arq.aclose()
    await pool.close_pool()
    trace.get_tracer_provider().shutdown()
    logger.info("Shutdown complete")


app = FastAPI(title="NeuroFlow API", version="0.1.0", lifespan=lifespan)
app.add_middleware(OpenTelemetryMiddleware)
app.include_router(query.router)
app.include_router(runs.router)
app.include_router(pipelines.router)
app.include_router(compare.router)
app.include_router(analytics.router)
app.include_router(finetune_router)


@app.get("/health")
async def get_health():
    checks = await health.check_all()
    for name, ok in checks.items():
        DEPENDENCY_UP.labels(dependency=name).set(1 if ok else 0)

    result = {n: {"status": "ok" if ok else "down"} for n, ok in checks.items()}

    try:
        t = time.perf_counter()
        await get_pool().fetchval("SELECT 1")
        result["postgres"] = {"status": "ok", "latency_ms": round((time.perf_counter() - t) * 1000)}
    except Exception:
        result["postgres"] = {"status": "down"}

    try:
        r = get_redis()
        t = time.perf_counter()
        await r.ping()
        result["redis"] = {"status": "ok", "latency_ms": round((time.perf_counter() - t) * 1000)}
        depth = await queue_depth()
        workers = 1 if await r.exists("arq:queue:health-check") else 0
    except Exception:
        result["redis"] = {"status": "down"}
        depth, workers = None, 0

    breakers = {}
    for name in ("openai", "anthropic"):
        try:
            breakers[name] = await CircuitBreaker(name).status()
        except Exception:
            breakers[name] = {"state": "unknown"}

    if result["postgres"]["status"] != "ok" or result["redis"]["status"] != "ok":
        status = "critical"
    elif any(b.get("state") == "open" for b in breakers.values()) or not all(checks.values()):
        status = "degraded"
    else:
        status = "ok"

    body = {
        "status": status,
        "checks": {
            **result,
            "circuit_breakers": breakers,
            "queue_depth": depth,
            "worker_count": workers,
        },
    }
    return JSONResponse(content=body, status_code=503 if status == "critical" else 200)


@app.get("/metrics")
async def get_metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)