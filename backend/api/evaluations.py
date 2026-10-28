import json
import uuid

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from db.pool import get_pool
from resilience.circuit_breaker import get_redis

router = APIRouter()
CHANNEL = "evaluations:new"

SELECT = """
SELECT e.id, e.run_id, e.faithfulness, e.answer_relevance, e.context_precision,
       e.context_recall, e.overall_score, e.evaluated_at,
       r.query, r.generation, p.id AS pipeline_id, p.name AS pipeline_name
FROM evaluations e
JOIN pipeline_runs r ON r.id = e.run_id
JOIN pipelines p ON p.id = r.pipeline_id
WHERE e.overall_score IS NOT NULL
"""


def _item(r) -> dict:
    d = dict(r)
    for k in ("id", "run_id", "pipeline_id"):
        d[k] = str(d[k])
    d["evaluated_at"] = d["evaluated_at"].isoformat() if d["evaluated_at"] else None
    return d


@router.get("/evaluations")
async def list_evaluations(limit: int = Query(100, ge=1, le=200)):
    rows = await get_pool().fetch(SELECT + " ORDER BY e.evaluated_at DESC LIMIT $1", limit)
    return [_item(r) for r in rows]


@router.get("/evaluations/stream")
async def stream():
    async def events():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if msg is None:
                    continue
                try:
                    run_id = uuid.UUID(json.loads(msg["data"])["run_id"])
                except Exception:
                    continue
                row = await get_pool().fetchrow(SELECT + " AND e.run_id = $1", run_id)
                if row:
                    yield {"data": json.dumps(_item(row))}
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()

    return EventSourceResponse(events(), ping=15)

@router.get("/evaluations/{run_id}")
async def get_evaluation(run_id: uuid.UUID):
    row = await get_pool().fetchrow(SELECT + " AND e.run_id = $1", run_id)
    if row is None:
        raise HTTPException(404, "Not evaluated yet")
    return _item(row)