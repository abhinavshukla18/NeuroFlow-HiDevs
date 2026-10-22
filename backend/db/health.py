"""Connectivity checks for Postgres, Redis and MLflow.

Each check makes a real round trip to the service and returns True or False.
A check never raises: a failure or timeout simply returns False and is logged,
so one broken dependency cannot crash /health.
"""

import asyncio
import logging

import httpx
from redis.asyncio import Redis

from config import get_settings
from db.pool import get_pool

logger = logging.getLogger(__name__)


async def check_postgres() -> bool:
    """Borrow a connection from the pool and run SELECT 1."""
    settings = get_settings()
    try:
        async with asyncio.timeout(settings.health_check_timeout_seconds):
            async with get_pool().acquire() as conn:
                return await conn.fetchval("SELECT 1") == 1
    except Exception as exc:
        logger.warning("Postgres health check failed: %r", exc)
        return False


async def check_redis() -> bool:
    """Open a connection to Redis (with its password) and send PING."""
    settings = get_settings()
    client = Redis.from_url(settings.redis_url)
    try:
        async with asyncio.timeout(settings.health_check_timeout_seconds):
            return bool(await client.ping())
    except Exception as exc:
        logger.warning("Redis health check failed: %r", exc)
        return False
    finally:
        await client.aclose()


async def check_mlflow() -> bool:
    """Call MLflow's own /health endpoint and expect HTTP 200."""
    settings = get_settings()
    url = settings.mlflow_tracking_uri.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=settings.health_check_timeout_seconds) as client:
            response = await client.get(url)
            return response.status_code == 200
    except Exception as exc:
        logger.warning("MLflow health check failed: %r", exc)
        return False


async def check_all() -> dict[str, bool]:
    """Run all three checks at the same time and return their results."""
    postgres, redis, mlflow = await asyncio.gather(
        check_postgres(), check_redis(), check_mlflow()
    )
    return {"postgres": postgres, "redis": redis, "mlflow": mlflow}