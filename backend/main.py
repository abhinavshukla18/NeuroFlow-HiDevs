"""NeuroFlow API: async FastAPI app."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

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
    await pool.create_pool()
    applied = await migrations.apply_schema()
    logger.info("Startup complete (schema applied now: %s)", applied)
    yield
    # Shutdown
    await pool.close_pool()
    trace.get_tracer_provider().shutdown()
    logger.info("Shutdown complete")


app = FastAPI(title="NeuroFlow API", version="0.1.0", lifespan=lifespan)
app.add_middleware(OpenTelemetryMiddleware)


@app.get("/health")
async def get_health():
    checks = await health.check_all()
    for name, ok in checks.items():
        DEPENDENCY_UP.labels(dependency=name).set(1 if ok else 0)

    all_ok = all(checks.values())
    body = {"status": "ok" if all_ok else "degraded", "checks": checks}
    return JSONResponse(content=body, status_code=200 if all_ok else 503)


@app.get("/metrics")
async def get_metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)