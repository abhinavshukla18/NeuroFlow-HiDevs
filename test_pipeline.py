import asyncio

from db import pool
from pipelines.retrieval.pipeline import RetrievalPipeline


async def main():
    await pool.create_pool()
    pipeline = RetrievalPipeline.from_settings()
    out = await pipeline.run("What is the NeuroFlow retrieval augmented generation platform?", k=5)
    print("type:", out["query_type"], "| filters:", out["filters"], "| queries:", out["queries"])
    for r in out["results"]:
        print(round(r.score, 4), r.strategies, r.source_name, r.content[:50].replace("\n", " "))
    ctx = out["context"]
    print(ctx.metadata["sources"], ctx.total_tokens, "tokens")
    print(ctx.context[:300])
    assert out["results"] and ctx.chunks_used and ctx.total_tokens <= 4000
    print("PASS")
    await pool.close_pool()


asyncio.run(main())