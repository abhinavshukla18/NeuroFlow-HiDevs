import asyncio

from db import pool
from pipelines.generation.generator import create_run, run_events


async def main():
    await pool.create_pool()
    run_id = await create_run(None, "What is the NeuroFlow retrieval augmented generation platform?")
    before = await pool.get_pool().fetchval("SELECT status FROM pipeline_runs WHERE id = $1", run_id)
    print("row exists before LLM call, status:", before)
    async for event in run_events(run_id):
        if event["type"] == "token":
            print(event["delta"], end="", flush=True)
        else:
            print("\n", event)
    row = await pool.get_pool().fetchrow(
        "SELECT status, model_used, input_tokens, output_tokens, latency_ms, left(prompt, 60) AS p, "
        "generation FROM pipeline_runs WHERE id = $1", run_id)
    print(dict(row))
    assert before == "queued" and row["status"] == "complete" and row["p"] and row["generation"]
    print("PASS")
    await pool.close_pool()


asyncio.run(main())