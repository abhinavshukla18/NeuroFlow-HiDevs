import asyncio
from types import SimpleNamespace

from config import get_settings
from evaluation.metrics.answer_relevance import evaluate_answer_relevance

run = asyncio.run
Q = "What is HNSW indexing?"
GOOD = "HNSW is a graph based index used for fast approximate nearest neighbour search [Source 1]."
BAD = "The monsoon brings heavy rain to India between June and September."

good = run(evaluate_answer_relevance(Q, GOOD))
bad = run(evaluate_answer_relevance(Q, BAD))
print("fallback path:", round(good, 2), round(bad, 2))
assert 0 <= bad <= 1 and 0 <= good <= 1 and good > bad
print("PASS fallback: relevant answer scores above irrelevant answer")


async def fake_embed(texts):
    return [[1.0, 0.0] if "hnsw" in t.lower() else [0.0, 1.0] for t in texts]


class FakeClient:
    async def chat(self, messages, criteria, **kwargs):
        return SimpleNamespace(content='["What is HNSW?", "How does HNSW search work?", "Which index is graph based?"]')


get_settings().openai_api_key = "test"
score = run(evaluate_answer_relevance(Q, GOOD, FakeClient(), embed=fake_embed))
print("llm path:", score)
assert score == 2 / 3
print("PASS LLM path: mean cosine of query vs generated questions")