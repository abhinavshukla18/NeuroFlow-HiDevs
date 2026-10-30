import io
import json
import os
import random
import re
import uuid
from pathlib import Path

from locust import HttpUser, between, events, task

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("load_test_results.json")

SAMPLE_QUERIES = [
    "What is the main topic of the document?",
    "How does attention work in transformers?",
    "Explain BM25 ranking.",
    "What is photosynthesis?",
    "Summarize the key ideas in the documents.",
]


def env_value(name: str) -> str:
    if os.getenv(name):
        return os.environ[name]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        m = re.match(rf"^{name}=(.*)$", line)
        if m:
            return m.group(1).strip()
    raise RuntimeError(f"{name} missing")


class NeuroFlowUser(HttpUser):
    abstract = True
    wait_time = between(1, 3)

    def on_start(self):
        r = self.client.post(
            "/auth/token",
            json={"client_id": env_value("ADMIN_CLIENT_ID"), "client_secret": env_value("ADMIN_CLIENT_SECRET")},
            name="/auth/token",
        )
        self.client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"


class QueryUser(NeuroFlowUser):
    weight = 7

    @task
    def query_pipeline(self):
        self.client.post("/query", json={"query": random.choice(SAMPLE_QUERIES), "stream": False}, name="/query")


class IngestUser(NeuroFlowUser):
    weight = 2

    @task
    def ingest_document(self):
        text = f"Load test document {uuid.uuid4()}. " + "NeuroFlow retrieval augmented generation test content. " * 40
        self.client.post(
            "/ingest",
            files={"file": ("load.txt", io.BytesIO(text.encode()), "text/plain")},
            name="/ingest",
        )


class AdminUser(NeuroFlowUser):
    weight = 1

    @task
    def check_evaluations(self):
        self.client.get("/evaluations", name="/evaluations")


@events.quitting.add_listener
def write_results(environment, **kwargs):
    total = environment.stats.total
    q = environment.stats.get("/query", "POST")
    p95 = q.get_response_time_percentile(0.95) if q.num_requests else None
    error_rate = (total.num_failures / total.num_requests * 100) if total.num_requests else 100
    passed = p95 is not None and p95 < 5000 and error_rate < 2
    OUT.write_text(json.dumps({
        "users": environment.parsed_options.num_users,
        "run_time": environment.parsed_options.run_time,
        "total_requests": total.num_requests,
        "failures": total.num_failures,
        "error_rate_percent": round(error_rate, 2),
        "query_p50_ms": q.get_response_time_percentile(0.5) if q.num_requests else None,
        "query_p95_ms": p95,
        "query_p99_ms": q.get_response_time_percentile(0.99) if q.num_requests else None,
        "requests_per_second": round(total.total_rps, 2),
        "passed": passed,
    }, indent=2))
    environment.process_exit_code = 0 if passed else 1