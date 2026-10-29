"""NeuroFlow API: async FastAPI app."""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from api import analytics, auth, chunks, compare, evaluations, ingest, pipelines, query, runs
from api.finetune import router as finetune_router
from arq import create_pool
from arq.connections import RedisSettings
from config import get_settings
from db import health, migrations, pool
from db.pool import get_pool
from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from monitoring.metrics import active_circuit_breakers_open, eval_faithfulness, eval_overall
from monitoring.metrics import queue_depth as queue_depth_gauge
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from resilience.backpressure import queue_depth
from resilience.circuit_breaker import CircuitBreaker, get_redis
from security.auth import get_current_user, require_scope

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    return response

app.include_router(auth.router)
app.include_router(ingest.router, dependencies=[Depends(get_current_user)])
app.include_router(query.router, dependencies=[Depends(require_scope("query"))])
app.include_router(runs.router, dependencies=[Depends(require_scope("query"))])
app.include_router(pipelines.router, dependencies=[Depends(get_current_user)])
app.include_router(compare.router, dependencies=[Depends(require_scope("query"))])
app.include_router(analytics.router, dependencies=[Depends(require_scope("query"))])
app.include_router(evaluations.router, dependencies=[Depends(require_scope("query"))])
app.include_router(chunks.router, dependencies=[Depends(require_scope("query"))])
app.include_router(finetune_router, dependencies=[Depends(require_scope("admin"))])

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
    try:
        rows = await get_pool().fetch(
            "SELECT r.pipeline_id::text AS pid, avg(e.faithfulness) AS f, avg(e.overall_score) AS o "
            "FROM evaluations e JOIN pipeline_runs r ON r.id = e.run_id "
            "WHERE e.evaluated_at > now() - interval '24 hours' GROUP BY r.pipeline_id"
        )
        for r in rows:
            eval_faithfulness.labels(pipeline_id=r["pid"]).set(float(r["f"] or 0))
            eval_overall.labels(pipeline_id=r["pid"]).set(float(r["o"] or 0))
        queue_depth_gauge.set(await queue_depth())
        open_count = 0
        for name in ("openai", "anthropic"):
            if (await CircuitBreaker(name).status())["state"] == "open":
                open_count += 1
        active_circuit_breakers_open.set(open_count)
    except Exception:
        pass
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)