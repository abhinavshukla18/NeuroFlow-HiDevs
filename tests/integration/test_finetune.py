import json

import pytest

from tests.integration.helpers import run_in_api

SEED = '''
import asyncio
from db import pool
from db.pool import get_pool
from pipelines.generation.generator import ensure_default_pipeline

ANSWER = ("Based on the provided sources, the transformer architecture relies entirely on attention "
          "mechanisms instead of recurrence, which allows far more parallelization during training [Source 1]. ") * 2

async def main():
    await pool.create_pool()
    p = get_pool()
    pid = await ensure_default_pipeline()
    for i in range(15):
        run_id = await p.fetchval(
            "INSERT INTO pipeline_runs (pipeline_id, query, status, generation) "
            "VALUES ($1, $2, 'complete', $3) RETURNING id",
            pid, f"test question {i}", ANSWER)
        await p.execute(
            "INSERT INTO evaluations (run_id, faithfulness, answer_relevance, context_precision, "
            "context_recall, overall_score, judge_model) VALUES ($1, 0.95, 0.9, 0.9, 0.9, 0.92, 'test')",
            run_id)
        await p.execute(
            "INSERT INTO training_pairs (run_id, system_prompt, user_message, assistant_message, quality_score) "
            "VALUES ($1, $2, $3, $4, 0.9)",
            run_id, "You are a precise research assistant.",
            f"[Context]\\nTransformers use attention.\\n[Question]\\ntest question {i}", ANSWER)
    print("seeded")

asyncio.run(main())
'''

KEY_SET = "import os; print(bool(os.getenv('OPENAI_API_KEY')))"

READ = '''
import json
rows = [json.loads(l) for l in open("training_data/{job_id}.jsonl", encoding="utf-8")]
print(len(rows))
print(all([m["role"] for m in r["messages"]] == ["system", "user", "assistant"] for r in rows))
print(all("[Source" in r["messages"][2]["content"] for r in rows))
'''


async def test_finetune_extraction(client):
    if run_in_api(KEY_SET).strip() == "True":
        pytest.skip("OPENAI_API_KEY is set; this test would start a real fine-tune job")

    assert run_in_api(SEED).strip() == "seeded"

    r = await client.post("/finetune/jobs", json={"base_model": "gpt-4o-mini", "domain": "general"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pairs"] >= 15

    count, shape_ok, cite_ok = run_in_api(READ.format(job_id=body["job_id"])).split()
    assert int(count) >= 15
    assert shape_ok == "True"
    assert cite_ok == "True"
    