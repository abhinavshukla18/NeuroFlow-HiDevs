import asyncio
from types import SimpleNamespace

from config import get_settings
from pipelines.retrieval import RetrievalResult
from pipelines.retrieval.reranker import Reranker, parse_score

assert parse_score("8") == 8 and parse_score("Score: 7.5") == 7.5 and parse_score("n/a") == 0 and parse_score("42") == 10
print("PASS parse_score")


class FakeClient:
    async def chat(self, messages, criteria, **kwargs):
        text = messages[0].content
        return SimpleNamespace(content="9" if "needle" in text.split("Passage:")[1] else "1")


candidates = [RetrievalResult(chunk_id=str(i), content="filler text " * 5, score=1 / (60 + i)) for i in range(10)]
candidates[7].content = "this passage contains the needle answer"

settings = get_settings()
settings.openai_api_key = "test"  # pretend a key exists so the API path runs

reranked = asyncio.run(Reranker(FakeClient()).rerank("find the needle", candidates, top_k=5))
print([(r.chunk_id, r.score) for r in reranked])
assert reranked[0].chunk_id == "7" and reranked[0].metadata["rrf_score"] > 0
print("PASS reranker moves the relevant chunk from rank 8 to rank 1")

settings.openai_api_key = ""
unchanged = asyncio.run(Reranker(FakeClient()).rerank("x", candidates, top_k=3))
assert [r.chunk_id for r in unchanged] == ["0", "1", "2"]
print("PASS no key: keeps RRF order")