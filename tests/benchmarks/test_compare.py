import uuid


async def _make_pipeline(client, name: str, top_k: int) -> str:
    r = await client.post(
        "/pipelines",
        json={"name": name, "description": "ab test", "retrieval": {"top_k_after_rerank": top_k}},
    )
    assert r.status_code == 201, r.text
    return r.json()["pipeline_id"]


async def test_pipeline_ab_comparison(client):
    suffix = uuid.uuid4().hex[:6]
    a = await _make_pipeline(client, f"ab-a-{suffix}", 3)
    b = await _make_pipeline(client, f"ab-b-{suffix}", 8)

    r = await client.post(
        "/pipelines/compare",
        json={"query": "What is the main topic of the document?", "pipeline_a_id": a, "pipeline_b_id": b},
        timeout=180,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    print(body)

    flat = str(body)
    assert a in flat and b in flat
    assert len(body) >= 2