import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

from config import get_settings
from db import pool
from evaluation.eval_data import ENTRIES
from pipelines.ingestion.pipeline import process_document
from pipelines.retrieval.pipeline import RetrievalPipeline
from pipelines.retrieval.query_processor import process_query

K = 10
RESULTS_FILE = Path(__file__).parent / "retrieval_results.json"


async def build_corpus() -> list[set[str]]:
    p = pool.get_pool()
    await p.execute("DELETE FROM documents WHERE filename LIKE 'eval_%.txt'")
    for i, (passage, _) in enumerate(ENTRIES):
        name = f"eval_{i:02d}.txt"
        path = Path(tempfile.gettempdir()) / name
        path.write_text(passage, encoding="utf-8")
        digest = hashlib.sha256(passage.encode()).hexdigest()
        doc_id = await p.fetchval(
            "INSERT INTO documents (filename, source_type, content_hash, status) "
            "VALUES ($1, 'text', $2, 'queued') ON CONFLICT (content_hash) DO NOTHING RETURNING id",
            name, digest,
        )
        if doc_id:
            await process_document(str(doc_id), str(path), "text")
    relevant: list[set[str]] = []
    for i in range(len(ENTRIES)):
        rows = await p.fetch(
            "SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.filename = $1",
            f"eval_{i:02d}.txt",
        )
        relevant.append({str(r["id"]) for r in rows})
    return relevant


def score(ranks: list[int | None]) -> dict:
    n = len(ranks)
    return {
        "hit_rate": round(sum(r is not None for r in ranks) / n, 4),
        "mrr": round(sum(1 / r for r in ranks if r) / n, 4),
    }


async def evaluate(name: str, search, relevant: list[set[str]]) -> dict:
    ranks = []
    for (_, question), rel in zip(ENTRIES, relevant):
        results = await search(question)
        ranks.append(next((j + 1 for j, r in enumerate(results[:K]) if r.chunk_id in rel), None))
    metrics = score(ranks)
    print(f"{name:<14} hit_rate={metrics['hit_rate']:.2f}  mrr={metrics['mrr']:.2f}")
    return metrics


async def main():
    settings = get_settings()
    await pool.create_pool()
    pipeline = RetrievalPipeline.from_settings()
    relevant = await build_corpus()

    async def dense_only(q):
        analysis = await process_query(q, pipeline.client)
        return await pipeline.retriever._dense_retrieval(analysis.all_queries, K)

    async def rrf_only(q):
        return await pipeline.retrieve(q, k=K, rerank=False)

    async def rrf_rerank(q):
        return await pipeline.retrieve(q, k=K, rerank=True)

    results = {
        "dense_only": await evaluate("dense_only", dense_only, relevant),
        "rrf_only": await evaluate("rrf_only", rrf_only, relevant),
        "rrf_rerank": await evaluate("rrf_rerank", rrf_rerank, relevant),
    }
    best = results["rrf_rerank"]
    report = {
        "num_queries": len(ENTRIES),
        "k": K,
        "embeddings": "local fastembed bge-small (zero-padded to 1536)" if settings.local_models else ("fake (random vectors)" if settings.fake_embeddings else "real"),
        "reranker_active": bool(settings.local_models or settings.openai_api_key or settings.anthropic_api_key),
        "results": results,
        "thresholds": {"hit_rate": 0.75, "mrr": 0.55},
        "passed": best["hit_rate"] > 0.75 and best["mrr"] > 0.55,
    }
    RESULTS_FILE.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    await pool.close_pool()


asyncio.run(main())