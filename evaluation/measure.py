import asyncio
import json
import math
import re
import time

from config import get_settings
from db import pool
from db.pool import get_pool
from evaluation.judge import EvaluationJudge
from pipelines.generation.generator import create_run, generate_full
from pipelines.retrieval.pipeline import RetrievalPipeline

N_RETRIEVAL = 50
N_GEN = 30
STOP = set("the a an of and to in is are was were for on with as by at from that this it be or which".split())


def make_question(text: str) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 8]
    base = max(sentences[:4], key=len) if sentences else " ".join(text.split()[:25])
    words = [w for w in re.findall(r"[A-Za-z0-9\-]+", base) if w.lower() not in STOP]
    words = [w for i, w in enumerate(words) if i % 4 != 3]
    return " ".join(words[:14])


def p95(values):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, math.ceil(0.95 * len(s)) - 1)]


def avg(values):
    return round(sum(values) / len(values), 4) if values else None


async def main():
    await pool.create_pool()
    settings = get_settings()
    rows = await get_pool().fetch(
        "SELECT id::text AS id, content FROM chunks WHERE token_count >= 40 "
        "ORDER BY md5(id::text) LIMIT $1",
        N_RETRIEVAL,
    )
    questions = [(r["id"], make_question(r["content"])) for r in rows]

    # --- retrieval: Hit@10 and MRR@10 on hybrid + reranked results
    rp = RetrievalPipeline.from_settings()
    hits, rrs = [], []
    for truth, q in questions:
        _, fused = await rp._search(q, 20)
        ranked = [x.chunk_id for x in await rp.reranker.rerank(q, fused, top_k=10)]
        rank = ranked.index(truth) + 1 if truth in ranked else None
        hits.append(1.0 if rank else 0.0)
        rrs.append(1 / rank if rank else 0.0)

    # --- generation + evaluation + latency
    judge = EvaluationJudge.from_settings()
    scores = {k: [] for k in ("faithfulness", "answer_relevance", "context_precision", "context_recall", "overall_score")}
    latencies = []
    for _, q in questions[:N_GEN]:
        started = time.perf_counter()
        run_id = await create_run(None, q)
        result = await generate_full(run_id)
        latencies.append(time.perf_counter() - started)
        if result.get("status") != "complete":
            continue
        try:
            ev = await judge.evaluate(run_id)
        except Exception:
            continue
        for k in scores:
            if ev.get(k) is not None:
                scores[k].append(float(ev[k]))

    out = {
        "hit_rate_at_10": avg(hits),
        "mrr_at_10": avg(rrs),
        "faithfulness": avg(scores["faithfulness"]),
        "answer_relevance": avg(scores["answer_relevance"]),
        "context_precision": avg(scores["context_precision"]),
        "context_recall": avg(scores["context_recall"]),
        "overall_score": avg(scores["overall_score"]),
        "p95_latency_s": round(p95(latencies), 3) if latencies else None,
        "n_retrieval_questions": len(questions),
        "n_generation_questions": len(scores["overall_score"]),
        "embeddings": "fake" if settings.fake_embeddings else ("local" if settings.local_models else "real"),
        "llm": "real" if (settings.openai_api_key or settings.anthropic_api_key) else "fake",
    }
    print(json.dumps(out))
    await pool.close_pool()


asyncio.run(main())