from uuid import UUID, uuid4

from db.pool import get_pool
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from pipelines.finetuning.extractor import (
    extract_training_pairs,
    format_pair,
    mark_included,
    write_jsonl,
)
from pipelines.finetuning.job_manager import submit_finetune_job
from pipelines.finetuning.tracker import run_url, start_training_job

router = APIRouter(prefix="/finetune", tags=["finetune"])


def _pool(request: Request):
    return get_pool()


def _redis(request: Request):
    return request.app.state.arq


class FinetuneRequest(BaseModel):
    base_model: str = Field("gpt-4o-mini", description="Model to fine-tune.", examples=["gpt-4o-mini"])
    domain: str = Field("general", description="Task type the tuned model is routed for.", examples=["general"])
    limit: int = Field(1000, description="Maximum number of candidate pairs to consider.", examples=[1000])


@router.post("/jobs")
async def create_job(body: FinetuneRequest, request: Request):
    pool = _pool(request)
    rows, rejected = await extract_training_pairs(pool, body.limit)
    if not rows:
        raise HTTPException(400, detail={"error": "no qualifying pairs", "rejected": rejected})

    job_id = uuid4()
    path = write_jsonl(job_id, rows)
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO finetune_jobs (id, base_model, status, training_pair_count)
               VALUES ($1, $2, 'running', $3)""",
            job_id, body.base_model, len(rows),
        )
    run_id = start_training_job(job_id, rows, body.base_model, path)
    provider_job_id = await submit_finetune_job(path, body.base_model)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE finetune_jobs SET mlflow_run_id=$2, provider_job_id=$3 WHERE id=$1",
            job_id, run_id, provider_job_id,
        )
    await mark_included(pool, job_id, rows)
    await _redis(request).enqueue_job(
        "poll_finetune_job", str(job_id), provider_job_id, run_id, body.domain,
        _defer_by=5,
    )
    return {"job_id": str(job_id), "pairs": len(rows), "rejected": rejected}


@router.get("/jobs")
async def list_jobs(request: Request):
    async with _pool(request).acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, base_model, status, training_pair_count, created_at, completed_at "
            "FROM finetune_jobs ORDER BY created_at DESC"
        )
    return [dict(r) for r in rows]


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID, request: Request):
    async with _pool(request).acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM finetune_jobs WHERE id=$1", job_id)
    if not row:
        raise HTTPException(404, "job not found")
    out = dict(row)
    if out.get("mlflow_run_id"):
        out["mlflow_run_url"] = run_url(out["mlflow_run_id"])
    return out


@router.get("/training-data/preview")
async def preview(request: Request):
    rows, rejected = await extract_training_pairs(_pool(request), 1000)
    return {
        "qualifying": len(rows),
        "rejected": rejected,
        "samples": [format_pair(r) for r in rows[:5]],
    }