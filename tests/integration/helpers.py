import asyncio
import json
import time
from pathlib import Path
import subprocess

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


async def ingest_test_document(client, path=None) -> dict:
    path = Path(path) if path else FIXTURES / "test_doc.pdf"
    with open(path, "rb") as f:
        r = await client.post("/ingest", files={"file": (path.name, f, "application/pdf")})
    r.raise_for_status()
    return r.json()


async def wait_for_status(client, doc_id: str, status: str = "complete", timeout: int = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = await client.get(f"/documents/{doc_id}")
        r.raise_for_status()
        doc = r.json()
        if doc["status"] == status:
            return doc
        if doc["status"] == "failed":
            raise AssertionError(f"ingestion failed: {doc.get('metadata')}")
        await asyncio.sleep(2)
    raise TimeoutError(f"document {doc_id} not '{status}' after {timeout}s")


async def submit_query(client, query: str, pipeline_id: str | None = None) -> str:
    r = await client.post("/query", json={"query": query, "pipeline_id": pipeline_id, "stream": True})
    r.raise_for_status()
    return r.json()["run_id"]


async def wait_for_generation(client, run_id: str, timeout: int = 30) -> dict:
    out = {"generation": "", "chunks_used": 0, "citations": [], "error": None}

    async def consume():
        async with client.stream("GET", f"/query/{run_id}/stream") as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                ev = json.loads(line[5:].strip())
                if ev["type"] == "retrieval_complete":
                    out["chunks_used"] = ev["chunk_count"]
                elif ev["type"] == "token":
                    out["generation"] += ev["delta"]
                elif ev["type"] == "done":
                    out["citations"] = ev["citations"]
                    return
                elif ev["type"] == "error":
                    out["error"] = ev["message"]
                    return

    await asyncio.wait_for(consume(), timeout=timeout)
    assert out["error"] is None, out["error"]
    return out


async def wait_for_evaluation(client, run_id: str, timeout: int = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = await client.get(f"/evaluations/{run_id}")
        if r.status_code == 200:
            return r.json()
        await asyncio.sleep(3)
    raise TimeoutError(f"run {run_id} not evaluated after {timeout}s")

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", "infra/docker-compose.yml", "--env-file", ".env"]


def run_in_api(script: str) -> str:
    """Run a python script inside the api container and return stdout."""
    out = subprocess.run(
        COMPOSE + ["exec", "-T", "api", "python", "-"],
        input=script, capture_output=True, text=True, cwd=ROOT, check=True,
    )
    return out.stdout


def clear_rate_limits() -> None:
    run_in_api(
        "import asyncio\n"
        "from resilience.circuit_breaker import get_redis\n"
        "async def m():\n"
        "    r = get_redis()\n"
        "    for k in await r.keys('ratelimit:*'):\n"
        "        await r.delete(k)\n"
        "asyncio.run(m())\n"
    )