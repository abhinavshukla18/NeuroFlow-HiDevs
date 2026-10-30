import asyncio
import logging

import main  # noqa: F401  (sets up OpenTelemetry tracing)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from arq.connections import RedisSettings
from arq.worker import run_worker
from config import get_settings
from db import pool
from jobs.retention import run_retention
from prometheus_client import start_http_server

from evaluation.judge import EvaluationJudge, consume_forever
from pipelines.finetuning.job_manager import poll_finetune_job
from pipelines.ingestion.pipeline import process_document

logger = logging.getLogger("neuroflow.worker")
settings = get_settings()

QUEUE_NAME = "queue:ingest"


async def ingest_document(ctx, document_id: str, file_path: str, source_type: str) -> dict:
    return await process_document(document_id, file_path, source_type)


async def startup(ctx) -> None:
    start_http_server(9100)
    await pool.create_pool()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_retention, "cron", hour=3, minute=0)
    scheduler.start()
    ctx["scheduler"] = scheduler
    ctx["stop_eval"] = asyncio.Event()
    ctx["eval_task"] = asyncio.create_task(
        consume_forever(EvaluationJudge.from_settings(), ctx["stop_eval"])
    )
    logger.info("Worker started, listening on %s and queue:evaluate", QUEUE_NAME)


async def shutdown(ctx) -> None:
    ctx["scheduler"].shutdown(wait=False)
    ctx["stop_eval"].set()
    try:
        await asyncio.wait_for(ctx["eval_task"], timeout=10)
    except asyncio.TimeoutError:
        ctx["eval_task"].cancel()
    await pool.close_pool()
    logger.info("Worker stopped")

    
class WorkerSettings:
    functions = [ingest_document, poll_finetune_job]
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