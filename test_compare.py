import uuid

import httpx

from evaluation.eval_data import ENTRIES

c = httpx.Client(base_url="http://localhost:8000", timeout=180)
tag = uuid.uuid4().hex[:6]
a = c.post("/pipelines", json={"name": f"cmp-wide-{tag}", "retrieval": {"top_k_after_rerank": 8, "dense_k": 30}}).json()["pipeline_id"]
b = c.post("/pipelines", json={"name": f"cmp-narrow-{tag}", "retrieval": {"top_k_after_rerank": 2, "reranker": "none"}}).json()["pipeline_id"]

for _, question in ENTRIES[:5]:
    r = c.post("/pipelines/compare", json={"query": question, "pipeline_a_id": a, "pipeline_b_id": b})
    assert r.status_code == 200, r.text
    d = r.json()
    A, B = d["pipeline_a"], d["pipeline_b"]
    print(f"A chunks={A['chunks_used']} score={A['eval_score']} total={A['total_latency_ms']}ms | "
          f"B chunks={B['chunks_used']} score={B['eval_score']} total={B['total_latency_ms']}ms | "
          f"compare={d['compare_latency_ms']}ms")
    assert A["status"] == B["status"] == "complete"
    assert A["eval_score"] is not None and B["eval_score"] is not None, "evaluation scores missing"
    assert d["compare_latency_ms"] < 0.85 * (A["total_latency_ms"] + B["total_latency_ms"]), "not running in parallel"
print("PASS side-by-side results with scores, and the two pipelines ran in parallel")