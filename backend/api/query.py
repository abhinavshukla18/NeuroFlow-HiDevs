import json
import uuid

from db.pool import get_pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from resilience.rate_limiter import ip_limit
from security.prompt_injection import detect_injection, llm_injection_check
from security.validators import clean_text
from sse_starlette.sse import EventSourceResponse

from pipelines.generation.generator import create_run, generate_full, run_events

router = APIRouter()


class QueryRequest(BaseModel):
    query: str = Field(max_length=5000)
    pipeline_id: uuid.UUID | None = None
    stream: bool = False

    @field_validator("query")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v)

@router.post("/query", dependencies=[Depends(ip_limit("query", 60, 60))])
async def query(body: QueryRequest):
    if not body.query.strip():
        raise HTTPException(400, "Query must not be empty")
    flag = detect_injection(body.query)
    if await llm_injection_check(body.query):
        raise HTTPException(
            400, detail={"error": "query_rejected", "reason": "potential_prompt_injection"}
        )
    if body.pipeline_id is not None:
        exists = await get_pool().fetchval("SELECT 1 FROM pipelines WHERE id = $1", body.pipeline_id)
        if not exists:
            raise HTTPException(404, "Pipeline not found")

    run_id = await create_run(str(body.pipeline_id) if body.pipeline_id else None, body.query)
    if flag:
        await get_pool().execute(
            "UPDATE pipeline_runs SET metadata = metadata || $2::jsonb WHERE id = $1",
            run_id, json.dumps(flag),
        )
    if body.stream:
        return {"run_id": run_id, "status": "queued", "stream_url": f"/query/{run_id}/stream"}
    return await generate_full(run_id)


@router.get("/query/{run_id}/stream")
async def stream(run_id: uuid.UUID):
    status = await get_pool().fetchval("SELECT status FROM pipeline_runs WHERE id = $1", run_id)
    if status is None:
        raise HTTPException(404, "Run not found")
    if status != "queued":
        raise HTTPException(409, f"Run is already {status}")

    async def events():
        async for event in run_events(str(run_id)):
            yield {"data": json.dumps(event)}

    return EventSourceResponse(events(), ping=15)