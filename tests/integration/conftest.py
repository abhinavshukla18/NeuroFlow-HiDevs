import os
import re
from pathlib import Path

import httpx
import pytest_asyncio

BASE_URL = os.getenv("NEUROFLOW_URL", "http://localhost:8000")
ROOT = Path(__file__).resolve().parents[2]


def env_value(name: str) -> str:
    if os.getenv(name):
        return os.environ[name]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        m = re.match(rf"^{name}=(.*)$", line)
        if m:
            return m.group(1).strip()
    raise RuntimeError(f"{name} not found in environment or .env")


async def login(client: httpx.AsyncClient, prefix: str) -> str:
    r = await client.post(
        "/auth/token",
        json={
            "client_id": env_value(f"{prefix}_CLIENT_ID"),
            "client_secret": env_value(f"{prefix}_CLIENT_SECRET"),
        },
    )
    r.raise_for_status()
    return r.json()["access_token"]


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120) as c:
        c.headers["Authorization"] = f"Bearer {await login(c, 'ADMIN')}"
        yield c