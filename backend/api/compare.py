import asyncio
import time
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from api.pipelines import load_pipeline
from db.pool import get_pool
from pipelines.generation.generator import _enqueue_evaluation, create_run, generate_full
from services.pipeline_runtime import config_for

router = APIRouter()
EVAL_WAIT_SECONDS = 20


class CompareRequest(BaseModel):
    query: str
    pipeline_a_id: uuid.UUID
    pipeline_b_id: uuid.UUID


async def _run_one(query: str, pipeline_id: uuid.UUID) -> dict:
    run_id = await create_run(str(pipeline_id), query)
    started = time.perf_counter()
    result = await generate_full(run_id)
    total_ms = round((time.perf_counter() - started) * 1000)

    row = await get_pool().fetchrow(
        "SELECT pipeline_id, pipeline_version, metadata FROM pipeline_runs WHERE id = $1", run_id
    )
    config = await config_for(row["pipeline_id"], row["pipeline_version"])
    if result["status"] == "complete" and not config.evaluation.auto_evaluate:
        _enqueue_evaluation(run_id)  # comparisons are always evaluated
    metadata = row["metadata"]
    if isinstance(metadata, str):
        import json
        metadata = json.loads(metadata)
    return {
        "run_id": run_id,
        "pipeline_id": str(pipeline_id),
        "pipeline_version": row["pipeline_version"],
        "status": result["status"],
        "generation": result.get("response"),
        "retrieval_latency_ms": metadata.get("retrieval_latency_ms"),
        "total_latency_ms": total_ms,
        "chunks_used": metadata.get("chunks_used"),
        "eval_score": None,
        "eval_pending": True,
    }


async def _wait_for_scores(sides: list[dict]) -> None:
    deadline = time.monotonic() + EVAL_WAIT_SECONDS
    while time.monotonic() < deadline:
        pending = [s for s in sides if s["eval_pending"] and s["status"] == "complete"]
        if not pending:
            return
        for side in pending:
            score = await get_pool().fetchval(
                "SELECT overall_score FROM evaluations WHERE run_id = $1", side["run_id"]
            )
            if score is not None:
                side["eval_score"] = round(float(score), 4)
                side["eval_pending"] = False
        await asyncio.sleep(1)


@router.post("/pipelines/compare")
async def compare(body: CompareRequest):
    await load_pipeline(body.pipeline_a_id)
    await load_pipeline(body.pipeline_b_id)

    started = time.perf_counter()
    a, b = await asyncio.gather(
        _run_one(body.query, body.pipeline_a_id),
        _run_one(body.query, body.pipeline_b_id),
    )
    compare_ms = round((time.perf_counter() - started) * 1000)
    await _wait_for_scores([a, b])
    return {"query": body.query, "compare_latency_ms": compare_ms, "pipeline_a": a, "pipeline_b": b}