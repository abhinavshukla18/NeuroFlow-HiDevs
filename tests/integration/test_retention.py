from tests.integration.helpers import run_in_api

SCRIPT = '''
import asyncio, uuid
from db import pool
from db.pool import get_pool
from jobs.retention import run_retention
from pipelines.generation.generator import ensure_default_pipeline

async def main():
    await pool.create_pool()
    p = get_pool()
    pid = await ensure_default_pipeline()
    old_run = await p.fetchval(
        "INSERT INTO pipeline_runs (pipeline_id, query, status, created_at) "
        "VALUES ($1, 'old run', 'complete', now() - interval '100 days') RETURNING id", pid)
    ev_run = await p.fetchval(
        "INSERT INTO pipeline_runs (pipeline_id, query, status, created_at) "
        "VALUES ($1, 'old eval run', 'complete', now() - interval '200 days') RETURNING id", pid)
    await p.execute(
        "INSERT INTO evaluations (run_id, faithfulness, overall_score, evaluated_at) "
        "VALUES ($1, 0.9, 0.9, now() - interval '200 days')", ev_run)
    doc = await p.fetchval(
        "INSERT INTO documents (filename, source_type, content_hash, metadata, status) "
        "VALUES ('arch.txt', 'text', $1, '{}'::jsonb, 'archived') RETURNING id", uuid.uuid4().hex)
    await p.execute(
        "INSERT INTO chunks (document_id, content, chunk_index, token_count) VALUES ($1, 'x', 0, 1)", doc)
    counts = await run_retention()
    print(counts["pipeline_runs"] >= 1, counts["evaluations"] >= 1, counts["chunks"] >= 1)
    print(await p.fetchval("SELECT count(*) FROM pipeline_runs WHERE id = $1", old_run) == 0)
    print(await p.fetchval("SELECT count(*) FROM evaluations WHERE run_id = $1", ev_run) == 0)
    print(await p.fetchval("SELECT count(*) FROM chunks WHERE document_id = $1", doc) == 0)
    await p.execute("DELETE FROM documents WHERE id = $1", doc)
    await p.execute("DELETE FROM pipeline_runs WHERE id = $1", ev_run)
    await pool.close_pool()

asyncio.run(main())
'''


def test_retention_deletes_old_records():
    out = run_in_api(SCRIPT).split()
    assert out == ["True", "True", "True", "True", "True", "True"], out