import asyncio
import json
import logging

from db import pool
from db.pool import get_pool

logger = logging.getLogger("neuroflow.retention")


def _n(status: str) -> int:
    return int(status.split()[-1])


async def run_retention() -> dict:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            runs = await conn.execute(
                "DELETE FROM pipeline_runs r WHERE r.created_at < now() - interval '90 days' "
                "AND r.status = 'complete' "
                "AND NOT EXISTS (SELECT 1 FROM evaluations e WHERE e.run_id = r.id) "
                "AND NOT EXISTS (SELECT 1 FROM training_pairs t WHERE t.run_id = r.id)"
            )
            evals = await conn.execute(
                "DELETE FROM evaluations WHERE evaluated_at < now() - interval '180 days'"
            )
            chunks = await conn.execute(
                "DELETE FROM chunks WHERE document_id IN (SELECT id FROM documents WHERE status = 'archived')"
            )
    counts = {"pipeline_runs": _n(runs), "evaluations": _n(evals), "chunks": _n(chunks)}
    logger.info(json.dumps({"event": "data_retention", **counts}))
    return counts


if __name__ == "__main__":
    async def main() -> None:
        await pool.create_pool()
        print(json.dumps(await run_retention()))
        await pool.close_pool()

    asyncio.run(main())