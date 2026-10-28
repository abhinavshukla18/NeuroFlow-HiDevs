import os
import time
from contextlib import asynccontextmanager

from datetime import datetime, timezone

from monitoring.metrics import circuit_breaker_trips

import redis.asyncio as aioredis

CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

_redis = None


def get_redis():
    global _redis
    if _redis is None:
        _redis = aioredis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            decode_responses=True,
        )
    return _redis


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5,
                 recovery_timeout: int = 60, half_open_max_calls: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.k_state = f"circuit:{name}:state"
        self.k_fail = f"circuit:{name}:failure_count"
        self.k_opened = f"circuit:{name}:opened_at"
        self.k_half = f"circuit:{name}:half_open_calls"

    async def _before_call(self) -> None:
        r = get_redis()
        state = await r.get(self.k_state) or CLOSED
        if state == OPEN:
            opened_at = float(await r.get(self.k_opened) or 0)
            if time.time() - opened_at < self.recovery_timeout:
                raise CircuitOpenError(f"circuit '{self.name}' is open")
            await r.set(self.k_state, HALF_OPEN)
            circuit_breaker_trips.labels(provider=self.name).inc()
            await r.set(self.k_half, 0)
            state = HALF_OPEN
        if state == HALF_OPEN:
            n = await r.incr(self.k_half)
            if n > self.half_open_max_calls:
                raise CircuitOpenError(f"circuit '{self.name}' half-open limit reached")

    async def _on_success(self) -> None:
        r = get_redis()
        await r.set(self.k_state, CLOSED)
        await r.set(self.k_fail, 0)
        await r.delete(self.k_opened, self.k_half)

    async def _on_failure(self) -> None:
        r = get_redis()
        state = await r.get(self.k_state) or CLOSED
        count = await r.incr(self.k_fail)
        if state == HALF_OPEN or count >= self.failure_threshold:
            await r.set(self.k_state, OPEN)
            await r.set(self.k_opened, time.time())

    async def status(self) -> dict:
        r = get_redis()
        opened = await r.get(self.k_opened)
        return {
            "state": await r.get(self.k_state) or CLOSED,
            "failure_count": int(await r.get(self.k_fail) or 0),
            "opened_at": datetime.fromtimestamp(float(opened), timezone.utc).isoformat() if opened else None,
        }


@asynccontextmanager
async def circuit_breaker(name: str, **kwargs):
    cb = CircuitBreaker(name, **kwargs)
    await cb._before_call()
    try:
        yield
    except CircuitOpenError:
        raise
    except Exception:
        await cb._on_failure()
        raise
    else:
        await cb._on_success()