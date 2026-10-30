import uuid

import httpx

c = httpx.Client(base_url="http://localhost:8000", timeout=30)
name = f"test-{uuid.uuid4().hex[:6]}"

r = c.post("/pipelines", json={"name": name, "retrieval": {"dense_k": 30}})
assert r.status_code == 201, r.text
pid = r.json()["pipeline_id"]
assert r.json()["version"] == 1
assert c.post("/pipelines", json={"name": name}).status_code == 409
assert c.post("/pipelines", json={"name": name + "x", "bogus": 1}).status_code == 422
assert any(p["id"] == pid for p in c.get("/pipelines").json())

g = c.get(f"/pipelines/{pid}").json()
assert g["config"]["retrieval"]["dense_k"] == 30 and g["version"] == 1

r = c.patch(f"/pipelines/{pid}", json={"retrieval": {"dense_k": 50}})
assert r.status_code == 200 and r.json()["version"] == 2
g = c.get(f"/pipelines/{pid}").json()
assert g["config"]["retrieval"]["dense_k"] == 50 and g["config"]["retrieval"]["sparse_k"] == 20
assert [v["version"] for v in g["versions"]] == [1, 2]
assert g["versions"][0]["config"]["retrieval"]["dense_k"] == 30, "old version must be preserved"
assert c.patch(f"/pipelines/{pid}", json={"retrieval": {"nope": 1}}).status_code == 422

assert c.delete(f"/pipelines/{pid}").status_code == 200
assert all(p["id"] != pid for p in c.get("/pipelines").json())
assert c.get(f"/pipelines/{pid}").json()["status"] == "archived"
print("PASS create, validate, list, get, versioned patch, soft delete")