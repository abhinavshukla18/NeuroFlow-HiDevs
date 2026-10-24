import asyncio
import re
from dataclasses import replace

from config import get_settings
from pipelines.retrieval import RetrievalResult
from providers.base import ChatMessage
from providers.router import RoutingCriteria

PROMPT = (
    "Rate the relevance of this passage to the query on a scale of 0-10. "
    "Query: {query}. Passage: {passage}. Return only the number."
)
RERANK_POOL = 40
MAX_CONCURRENCY = 10
PASSAGE_CHARS = 2000
LOCAL_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def parse_score(text: str) -> float:
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    return min(max(float(match.group()), 0.0), 10.0) if match else 0.0


class Reranker:
    def __init__(self, client=None, mode: str = "api"):
        self.client = client
        self.mode = mode  # "api" | "local" | "none"
        self._local = None

    def _has_llm(self) -> bool:
        settings = get_settings()
        return self.client is not None and bool(settings.openai_api_key or settings.anthropic_api_key)

    async def _score_api(self, query: str, candidates: list[RetrievalResult]) -> list[float]:
        gate = asyncio.Semaphore(MAX_CONCURRENCY)

        async def one(candidate: RetrievalResult) -> float:
            async with gate:
                try:
                    result = await self.client.chat(
                        [ChatMessage("user", PROMPT.format(query=query, passage=candidate.content[:PASSAGE_CHARS]))],
                        RoutingCriteria(task_type="classification"),
                        max_tokens=5,
                    )
                    return parse_score(result.content)
                except Exception:
                    return 0.0

        return list(await asyncio.gather(*(one(c) for c in candidates)))

    async def _score_local(self, query: str, candidates: list[RetrievalResult]) -> list[float]:
        if self._local is None:
            from sentence_transformers import CrossEncoder  # optional dependency
            self._local = CrossEncoder(LOCAL_MODEL)
        pairs = [(query, c.content) for c in candidates]
        scores = await asyncio.to_thread(self._local.predict, pairs)
        return [float(s) for s in scores]

    async def rerank(self, query: str, candidates: list[RetrievalResult], top_k: int = 10) -> list[RetrievalResult]:
        pool = candidates[:RERANK_POOL]
        if self.mode == "none" or not pool or (self.mode == "api" and not self._has_llm()):
            return pool[:top_k]

        scores = await (self._score_local(query, pool) if self.mode == "local" else self._score_api(query, pool))
        ranked = sorted(
            zip(scores, range(len(pool)), pool),
            key=lambda item: (-item[0], item[1]),  # ties keep RRF order
        )
        return [
            replace(c, score=s, metadata={**c.metadata, "rrf_score": c.score})
            for s, _, c in ranked[:top_k]
        ]
    