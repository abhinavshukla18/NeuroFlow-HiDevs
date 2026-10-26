import asyncio
from types import SimpleNamespace

from config import get_settings
from evaluation.metrics.context_precision import evaluate_context_precision
from evaluation.metrics.context_recall import evaluate_context_recall

run = asyncio.run
CHUNKS = [
    "HNSW is a graph based index for approximate nearest neighbour search.",
    "The monsoon brings heavy rain to India between June and September.",
    "Photosynthesis converts sunlight into glucose inside chloroplasts.",
]
ANSWER = "HNSW is a graph based index for nearest neighbour search [Source 1]."

p = run(evaluate_context_precision("What is HNSW?", CHUNKS, ANSWER))
print("precision:", round(p, 3))
assert abs(p - (1 / (1 + 1 / 2 + 1 / 3))) < 1e-9  # only rank 1 useful
assert run(evaluate_context_precision("q", [], ANSWER)) == 0.0

late = run(evaluate_context_precision("q", [CHUNKS[1], CHUNKS[2], CHUNKS[0]], ANSWER))
assert late < p, "a useful chunk at a later rank must score lower"
print("PASS precision: rank-weighted, earlier useful chunks score higher")

full = run(evaluate_context_recall("What is HNSW?", CHUNKS, ANSWER))
mixed = run(evaluate_context_recall("q", CHUNKS, ANSWER + " It was invented by aliens on Mars to cure diseases."))
print("recall:", full, mixed)
assert full == 1.0 and mixed == 0.5
assert run(evaluate_context_recall("q", [], ANSWER)) == 0.0
print("PASS recall: attributable sentences / total sentences")


class FakeClient:
    async def chat(self, messages, criteria, **kwargs):
        return SimpleNamespace(content="yes" if "graph based" in messages[0].content.split("Passage:")[-1] else "no")


get_settings().openai_api_key = "test"
assert run(evaluate_context_precision("q", CHUNKS, ANSWER, FakeClient())) == p
print("PASS LLM path")