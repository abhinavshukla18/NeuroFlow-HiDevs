async def test_health(client):
    r = await client.get("/health")
    assert r.status_code in (200, 503)


async def test_auth_required():
    import httpx
    from tests.integration.conftest import BASE_URL
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        assert (await c.get("/pipelines")).status_code == 401