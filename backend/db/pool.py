"""Shared asyncpg connection pool.

The pool is created once at startup and closed at shutdown, both driven by
the FastAPI lifespan function in main.py. Everything else calls get_pool().
"""

import asyncpg

from config import get_settings

_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    """Create the pool. Safe to call twice: the second call returns the same pool."""
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings()
    _pool = await asyncpg.create_pool(
        dsn=settings.postgres_dsn,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        command_timeout=30,
    )
    return _pool


def get_pool() -> asyncpg.Pool:
    """Return the shared pool. Raises if startup has not created it yet."""
    if _pool is None:
        raise RuntimeError("Database pool is not initialised. Was the app started with its lifespan?")
    return _pool


async def close_pool() -> None:
    """Close all connections. Called once at shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None