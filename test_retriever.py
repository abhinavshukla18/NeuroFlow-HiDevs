import asyncio

from db import pool
from pipelines.retrieval.query_processor import heuristic_analysis
from pipelines.retrieval.retriever import Retriever


async def main():
    await pool.create_pool()
    retriever = Retriever()
    analysis = heuristic_analysis("What is the NeuroFlow retrieval augmented generation platform?")
    dense, sparse, meta = await asyncio_gather(retriever, analysis)
    print("dense:", len(dense), "sparse:", len(sparse), "metadata:", len(meta))
    fused = await retriever.retrieve(analysis, k=10)
    for r in fused[:5]:
        print(round(r.score, 4), r.strategies, r.source_name, r.content[:50].replace("\n", " "))
    assert dense and sparse
    assert any(len(r.strategies) > 1 for r in fused), "expected a chunk found by 2 strategies"
    print("PASS")
    await pool.close_pool()


async def asyncio_gather(retriever, analysis):
    import asyncio
    return await asyncio.gather(
        retriever._dense_retrieval(analysis.all_queries, 10),
        retriever._sparse_retrieval(analysis.all_queries, 10),
        retriever._metadata_retrieval(analysis.original, {"source_type": "none"}, 10),
    )


asyncio.run(main())