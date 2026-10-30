from fastapi import HTTPException, Response

from resilience.circuit_breaker import get_redis


async def queue_depth() -> int:
    r = get_redis()
    if await r.type("queue:ingest") == "list":
        return await r.llen("queue:ingest")
    return await r.zcard("arq:queue")  # arq's default queue is a sorted set


async def check_backpressure(response: Response) -> dict | None:
    depth = await queue_depth()
    if depth > 100:
        raise HTTPException(
            status_code=503,
            detail={"error": "ingestion_queue_full", "queue_depth": depth, "retry_after": 30},
            headers={"Retry-After": "30"},
        )
    if depth > 50:
        response.status_code = 202
        return {"warning": "high_queue_depth", "estimated_wait_minutes": max(1, depth // 10)}
    return None