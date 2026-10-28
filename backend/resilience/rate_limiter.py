import asyncio
import time
import uuid

from fastapi import HTTPException, Request

from resilience.circuit_breaker import get_redis

TOKEN_BUCKET_LUA = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local tokens = tonumber(redis.call('GET', KEYS[1]))
local last = tonumber(redis.call('GET', KEYS[2]))
if tokens == nil then tokens = capacity; last = now end
tokens = math.min(capacity, tokens + (now - last) * rate)
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
else
  wait = (1 - tokens) / rate
end
redis.call('SET', KEYS[1], tokens)
redis.call('SET', KEYS[2], now)
return tostring(wait)
"""


async def acquire_token(name: str, capacity: float, rate: float, max_wait: float = 30) -> None:
    r = get_redis()
    keys = [f"rpb:{name}:tokens", f"rpb:{name}:ts"]
    deadline = time.time() + max_wait
    while True:
        wait = float(await r.eval(TOKEN_BUCKET_LUA, 2, *keys, capacity, rate, time.time()))
        if wait <= 0:
            return
        if time.time() + wait > deadline:
            raise TimeoutError(f"rate limit wait exceeded for {name}")
        await asyncio.sleep(wait)


async def acquire_llm_token(provider: str = "openai") -> None:
    await acquire_token(provider, capacity=3000, rate=50)


async def acquire_pipeline_token(pipeline_id: str, rpm: int = 60) -> None:
    await acquire_token(f"pipeline:{pipeline_id}", capacity=rpm, rate=rpm / 60)


async def check_rate_limit(key: str, limit: int, window: int) -> None:
    r = get_redis()
    now = time.time()
    k = f"ratelimit:{key}"
    pipe = r.pipeline()
    pipe.zremrangebyscore(k, 0, now - window)
    pipe.zadd(k, {f"{now}:{uuid.uuid4().hex}": now})
    pipe.zcard(k)
    pipe.zrange(k, 0, 0, withscores=True)
    pipe.expire(k, window)
    _, _, count, oldest, _ = await pipe.execute()
    if count > limit:
        retry = max(1, int(oldest[0][1] + window - now) + 1)
        raise HTTPException(
            status_code=429,
            detail="Too Many Requests",
            headers={"Retry-After": str(retry)},
        )


def ip_limit(name: str, limit: int, window: int):
    async def dependency(request: Request):
        ip = request.client.host if request.client else "unknown"
        await check_rate_limit(f"{name}:{ip}", limit, window)
    return dependency