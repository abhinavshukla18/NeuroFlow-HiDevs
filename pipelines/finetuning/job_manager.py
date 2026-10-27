import json
import os
from uuid import UUID

from db.pool import get_pool

from pipelines.finetuning.tracker import log_job_result

ROUTER_KEY = "router:models"
POLL_SECONDS = 60


def _mock() -> bool:
    return not os.getenv("OPENAI_API_KEY")


async def submit_finetune_job(jsonl_path: str, base_model: str) -> str:
    if _mock():
        return "mock-ftjob-001"
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    with open(jsonl_path, "rb") as f:
        file_resp = await client.files.create(file=f, purpose="fine-tune")
    job = await client.fine_tuning.jobs.create(training_file=file_resp.id, model=base_model)
    return job.id


async def get_provider_status(provider_job_id: str) -> dict:
    if _mock():
        return {
            "status": "succeeded",
            "fine_tuned_model": "ft:gpt-4o-mini:neuroflow:mock",
            "training_loss": 0.41,
            "validation_loss": 0.47,
            "trained_tokens": 12345,
        }
    from openai import AsyncOpenAI
    job = await AsyncOpenAI().fine_tuning.jobs.retrieve(provider_job_id)
    return {
        "status": job.status,
        "fine_tuned_model": job.fine_tuned_model,
        "training_loss": None,
        "validation_loss": None,
        "trained_tokens": job.trained_tokens,
    }


async def register_in_router(redis, model_name: str, domain: str) -> None:
    raw = await redis.get(ROUTER_KEY)
    models = json.loads(raw) if raw else []
    models = [m for m in models if m.get("model") != model_name]
    models.append({
        "model": model_name,
        "provider": "openai",
        "task_type": domain,
        "fine_tuned": True,
    })
    await redis.set(ROUTER_KEY, json.dumps(models))


async def poll_finetune_job(ctx, job_id: str, provider_job_id: str,
                            mlflow_run_id: str, domain: str = "general"):
    pool, redis = get_pool(), ctx["redis"]
    info = await get_provider_status(provider_job_id)
    status = info["status"]

    if status in ("validating_files", "queued", "running"):
        await redis.enqueue_job(
            "poll_finetune_job", job_id, provider_job_id, mlflow_run_id, domain,
            _defer_by=POLL_SECONDS,
        )
        return status

    async with pool.acquire() as conn:
        if status == "succeeded":
            model = info["fine_tuned_model"]
            await conn.execute(
                """UPDATE finetune_jobs
                   SET status='succeeded', provider_job_id=$2,
                       metrics=$3::jsonb, completed_at=now()
                   WHERE id=$1""",
                UUID(job_id), model,
                json.dumps({k: info[k] for k in
                            ("training_loss", "validation_loss", "trained_tokens")}),
            )
            await register_in_router(redis, model, domain)
            log_job_result(mlflow_run_id, UUID(job_id), info, model)
        else:
            await conn.execute(
                "UPDATE finetune_jobs SET status='failed', completed_at=now() WHERE id=$1",
                UUID(job_id),
            )
    return status