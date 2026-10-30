import time
import uuid

import httpx
import numpy as np

c = httpx.Client(base_url="http://localhost:8000", timeout=120)
pid = c.post("/pipelines", json={"name": f"an-{uuid.uuid4().hex[:6]}"}).json()["pipeline_id"]
for _ in range(6):
    assert c.post("/query", json={"query": "What is the NeuroFlow platform?", "pipeline_id": pid}).json()["status"] == "complete"
time.sleep(10)

runs = c.get(f"/pipelines/{pid}/runs", params={"page_size": 100}).json()
assert runs["total"] == 6 and len(runs["items"]) == 6
latencies = [r["latency_ms"] for r in runs["items"]]
a = c.get(f"/pipelines/{pid}/analytics").json()
print(a["total_latency_ms"], a["retrieval_latency_ms"], a["avg_evaluation_scores"], a["cost_per_query_usd"])

expected = {50: np.percentile(latencies, 50), 95: np.percentile(latencies, 95), 99: np.percentile(latencies, 99)}
got = a["total_latency_ms"]
assert abs(got["p95"] - expected[95]) < 1.0 and abs(got["p50"] - expected[50]) < 1.0 and abs(got["p99"] - expected[99]) < 1.0
assert got["p50"] <= got["p95"] <= got["p99"]
assert len(a["queries_per_day"]) == 30 and a["queries_per_day"][-1]["queries"] >= 6
assert a["avg_evaluation_scores"]["overall_score"] is not None
assert c.get(f"/pipelines/{pid}/runs", params={"page_size": 2, "page": 2}).json()["items"].__len__() == 2
print("PASS p50/p95/p99 match an independent calculation; 30-day series, scores and cost returned")