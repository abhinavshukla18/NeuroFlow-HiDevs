import uuid

import httpx

c = httpx.Client(base_url="http://localhost:8000", timeout=120)
tag = uuid.uuid4().hex[:6]
wide = c.post("/pipelines", json={"name": f"wide-{tag}", "retrieval": {"top_k_after_rerank": 8}}).json()["pipeline_id"]
narrow = c.post("/pipelines", json={"name": f"narrow-{tag}", "retrieval": {"top_k_after_rerank": 2}}).json()["pipeline_id"]
q = {"query": "What is the NeuroFlow retrieval augmented generation platform?", "stream": False}
for pid in (wide, narrow):
    print(c.post("/query", json={**q, "pipeline_id": pid}).json()["status"])
c.patch(f"/pipelines/{narrow}", json={"retrieval": {"top_k_after_rerank": 3}})
print(c.post("/query", json={**q, "pipeline_id": narrow}).json()["status"])
print("narrow-" + tag)