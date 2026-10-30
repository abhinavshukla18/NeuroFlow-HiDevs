import asyncio
import logging

from resilience.circuit_breaker import get_redis

log = logging.getLogger(__name__)

TIMEOUTS = {
    "embedding": 10,
    "chat_completion": 60,
    "reranking": 15,
    "evaluation": 120,
    "file_extraction": 30,
    "url_fetch": 15,
}


async def with_timeout(task_type: str, coro):
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUTS[task_type])
    except asyncio.TimeoutError:
        log.warning("timeout: %s after %ss", task_type, TIMEOUTS[task_type])
        await get_redis().incr(f"timeouts:{task_type}")
        raise TimeoutError(f"{task_type} timed out after {TIMEOUTS[task_type]}s")