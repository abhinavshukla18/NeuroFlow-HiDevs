import asyncio
import math
import random
import re

from db import pool
from db.pool import get_pool
from pipelines.retrieval.pipeline import RetrievalPipeline

N = 50
random.seed(7)
STOP = set("the a an of and to in is are was were for on with as by at from that this it be or which".split())


async def make_question(client, text: str) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 8]
    base = max(sentences[:4], key=len) if sentences else " ".join(text.split()[:25])
    if client is not None:
        try:
            from providers.base import ChatMessage

            prompt = (
                "Write one short question that this passage answers. Do not copy phrases "
                f"verbatim. Reply with the question only.\n\nPassage:\n{text[:1200]}"
            )
            res = await client.chat([ChatMessage(role="user", content=prompt)])
            out = (getattr(res, "content", None) or getattr(res, "text", "") or "").strip()
            if len(out) > 10:
                return out
        except Exception:
            pass
    words = [w for w in re.findall(r"[A-Za-z0-9\-]+", base) if w.lower() not in STOP]
    words = [w for i, w in enumerate(words) if i % 4 != 3]
    return " ".join(words[:14])


def score(ranked_ids: list[str], truth: str) -> dict:
    rank = next((i for i, cid in enumerate(ranked_ids[:10], 1) if cid == truth), None)
    return {
        "hit5": 1.0 if rank and rank <= 5 else 0.0,
        "hit10": 1.0 if rank else 0.0,
        "mrr": 1 / rank if rank else 0.0,
        "ndcg": 1 / math.log2(rank + 1) if rank else 0.0,
    }


async def main():
    await pool.create_pool()
    rp = RetrievalPipeline.from_settings()
    rows = await get_pool().fetch(
        "SELECT id::text AS id, content FROM chunks WHERE token_count >= 40 ORDER BY random() LIMIT $1", N
    )
    names = ["Dense only", "Sparse only", "Hybrid (RRF)", "Hybrid + reranked"]
    totals = {n: [] for n in names}

    for row in rows:
        q = await make_question(rp.client, row["content"])
        _, fused = await rp._search(q, 20)
        dense = await rp.retriever._dense_retrieval([q], 20)
        sparse = await rp.retriever._sparse_retrieval([q], 20)
        reranked = await rp.reranker.rerank(q, fused, top_k=10)
        runs = {"Dense only": dense, "Sparse only": sparse, "Hybrid (RRF)": fused, "Hybrid + reranked": reranked}
        for name, res in runs.items():
            totals[name].append(score([r.chunk_id for r in res], row["id"]))

    def avg(name, key):
        vals = [s[key] for s in totals[name]]
        return sum(vals) / len(vals) if vals else 0.0

    print("# Retrieval benchmark\n")
    print(f"Questions: {len(rows)} (ground truth = the chunk each question was generated from)\n")
    print("| Method | Hit@5 | Hit@10 | MRR@10 | NDCG@10 |")
    print("|---|---|---|---|---|")
    for n in names:
        print(f"| {n} | {avg(n,'hit5'):.3f} | {avg(n,'hit10'):.3f} | {avg(n,'mrr'):.3f} | {avg(n,'ndcg'):.3f} |")
    base, best = avg("Dense only", "mrr"), avg("Hybrid + reranked", "mrr")
    gain = (best - base) / base * 100 if base else float("inf")
    print(f"\nHybrid + reranked vs Dense only, MRR@10 improvement: {gain:.1f}% (target: >= 15%)")
    await pool.close_pool()


asyncio.run(main())