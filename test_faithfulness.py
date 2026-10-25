import asyncio
from types import SimpleNamespace

from config import get_settings
from evaluation.metrics.faithfulness import evaluate_faithfulness

CTX = "[Source 1 — a.pdf]\nHNSW is a graph based index for approximate nearest neighbour search. It was introduced in 2016."
GOOD = "HNSW is a graph based index for nearest neighbour search [Source 1]."
BAD = "HNSW was invented by aliens on Mars. It cures all diseases."
REFUSAL = "The provided context does not contain enough information to answer this question."
run = asyncio.run

good = run(evaluate_faithfulness("What is HNSW?", GOOD, CTX))
bad = run(evaluate_faithfulness("What is HNSW?", BAD, CTX))
print("heuristic:", good, bad)
assert good >= 0.9 and bad <= 0.1
assert run(evaluate_faithfulness("q", BAD, "")) == 0.0
assert run(evaluate_faithfulness("q", REFUSAL, "")) == 1.0
print("PASS heuristic path and empty-context rules")


class FakeClient:
    async def chat(self, messages, criteria, **kwargs):
        text = messages[0].content
        if text.startswith("List every factual"):
            return SimpleNamespace(content='["HNSW is a graph index", "It was invented on Mars"]')
        claim = text.split("Claim:")[1]
        return SimpleNamespace(content="no" if "Mars" in claim else "yes")


get_settings().openai_api_key = "test"
score = run(evaluate_faithfulness("What is HNSW?", BAD, CTX, client=FakeClient()))
print("llm path:", score)
assert score == 0.5
print("PASS LLM path (claims extracted, each judged, averaged)")