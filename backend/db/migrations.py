"""Apply the schema if it is missing."""

import logging
from pathlib import Path

from config import get_settings
from db.pool import get_pool

logger = logging.getLogger(__name__)

SCHEMA_LOCK_ID = 727001


async def schema_is_applied() -> bool:
    async with get_pool().acquire() as conn:
        return await conn.fetchval("SELECT to_regclass('public.documents') IS NOT NULL")


async def apply_schema() -> bool:
    """Apply the schema if missing. Returns True if it was applied now."""
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", SCHEMA_LOCK_ID)
            exists = await conn.fetchval("SELECT to_regclass('public.documents') IS NOT NULL")
            if exists:
                logger.info("Schema already applied")
                return False

            schema_file = Path(get_settings().schema_file)
            logger.info("Applying schema from %s", schema_file)
            await conn.execute(schema_file.read_text(encoding="utf-8"))
            return True