import asyncio
import re
import statistics
import time
import uuid
from pathlib import Path

import httpx
import mlflow

BASE = "http://localhost:8000"
ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ["default", "precise", "concise"]
QUESTIONS = [
    "What is the main topic of the document?",
    "What problem does the paper try to solve?",
    "How does the attention mechanism work?",
    "What is multi-head attention?",
    "Why does the model avoid recurrence?",
    "What are positional encodings used for?",
    "What results does the paper report?",
    "What is the encoder-decoder structure?",
    "How is the model trained?",
    "What are the main advantages of this approach?",
]
METRICS = ["faithfulness", "answer_relevance", "context_precision", "context_recall", "overall_score"]


def env(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        m = re.match(rf"^{name}=(.*)$", line)
        if m:
            return m.group(1).strip()
    raise RuntimeError(f"{name} missing from .env")


async def evaluation_for(c: httpx.AsyncClient, run_id: str, timeout: int = 150):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = await c.get(f"/evaluations/{run_id}")
        if r.status_code == 200:
            return r.json()
        await asyncio.sleep(4)
    return None


async def main():
    mlflow.set_tracking_uri("http://localhost:5000")
    mlflow.set_experiment("neuroflow-prompt-ab")
    suffix = uuid.uuid4().hex[:6]
    rows = []
    async with httpx.AsyncClient(base_url=BASE, timeout=180) as c:
        tok = await c.post("/auth/token", json={
            "client_id": env("ADMIN_CLIENT_ID"), "client_secret": env("ADMIN_CLIENT_SECRET")})
        c.headers["Authorization"] = f"Bearer {tok.json()['access_token']}"

        for variant in VARIANTS:
            p = await c.post("/pipelines", json={
                "name": f"ab-{variant}-{suffix}",
                "generation": {"system_prompt_variant": variant},
            })
            p.raise_for_status()
            pid = p.json()["pipeline_id"]

            run_ids, latencies = [], []
            for q in QUESTIONS:
                t = time.perf_counter()
                r = await c.post("/query", json={"query": q, "pipeline_id": pid, "stream": False})
                if r.status_code == 200 and r.json().get("status") == "complete":
                    run_ids.append(r.json()["run_id"])
                    latencies.append(time.perf_counter() - t)

            scores = {m: [] for m in METRICS}
            for rid in run_ids:
                ev = await evaluation_for(c, rid)
                if ev:
                    for m in METRICS:
                        if ev.get(m) is not None:
                            scores[m].append(float(ev[m]))

            means = {m: round(statistics.mean(v), 4) for m, v in scores.items() if v}
            with mlflow.start_run(run_name=f"prompt-{variant}"):
                mlflow.log_param("system_prompt_variant", variant)
                mlflow.log_param("n_queries", len(run_ids))
                mlflow.log_metrics(means)
                if latencies:
                    mlflow.log_metric("avg_latency_s", round(statistics.mean(latencies), 3))
            rows.append((variant, len(run_ids), means))

    print("\n| variant | n | faithfulness | answer_relevance | context_precision | overall |")
    print("|---|---|---|---|---|---|")
    for variant, n, m in rows:
        print(f"| {variant} | {n} | {m.get('faithfulness')} | {m.get('answer_relevance')} | "
              f"{m.get('context_precision')} | {m.get('overall_score')} |")
    best = max(rows, key=lambda r: r[2].get("overall_score", 0))
    print(f"\nBest variant by overall score: {best[0]}")


asyncio.run(main())