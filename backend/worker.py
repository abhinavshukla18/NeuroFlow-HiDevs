import logging

from arq.connections import RedisSettings
from arq.worker import run_worker

import main  # noqa: F401  (sets up OpenTelemetry tracing)
from config import get_settings
from db import pool
from pipelines.ingestion.pipeline import process_document

logger = logging.getLogger("neuroflow.worker")
settings = get_settings()

QUEUE_NAME = "queue:ingest"


async def ingest_document(ctx, document_id: str, file_path: str, source_type: str) -> dict:
    return await process_document(document_id, file_path, source_type)


async def startup(ctx) -> None:
    await pool.create_pool()
    logger.info("Worker started, listening on %s", QUEUE_NAME)


async def shutdown(ctx) -> None:
    await pool.close_pool()
    logger.info("Worker stopped")


class WorkerSettings:
    functions = [ingest_document]
    queue_name = QUEUE_NAME
    redis_settings = RedisSettings(
        host=settings.redis_host, port=settings.redis_port, password=settings.redis_password
    )
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 4
    max_tries = 3
    job_timeout = 600


if __name__ == "__main__":
    run_worker(WorkerSettings)