import json
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from db.pool import get_pool
from pipelines.generation.generator import create_run, generate_full, run_events

router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    pipeline_id: uuid.UUID | None = None
    stream: bool = False


@router.post("/query")
async def query(body: QueryRequest):
    if not body.query.strip():
        raise HTTPException(400, "Query must not be empty")
    if body.pipeline_id is not None:
        exists = await get_pool().fetchval("SELECT 1 FROM pipelines WHERE id = $1", body.pipeline_id)
        if not exists:
            raise HTTPException(404, "Pipeline not found")

    run_id = await create_run(str(body.pipeline_id) if body.pipeline_id else None, body.query)
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