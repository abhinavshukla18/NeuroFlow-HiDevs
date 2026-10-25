import asyncio
import re
import time
from typing import AsyncGenerator

from providers.base import BaseLLMProvider, ChatMessage, GenerationResult

SOURCE_RE = re.compile(r"\[Source (\d+) — ([^\]]+)\]\n(.+?)(?=\n\n\[Source \d+ —|\n</context>|\Z)", re.DOTALL)
NO_CONTEXT = "The provided context does not contain enough information to answer this question."


def _first_sentence(text: str) -> str:
    sentence = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return sentence.rstrip(".!?")


class FakeProvider(BaseLLMProvider):
    """Development stand-in used when no API key is set. Builds an answer from the context."""

    model = "fake-llm"

    def _answer(self, messages: list[ChatMessage]) -> str:
        sources = SOURCE_RE.findall(str(messages[-1].content))
        if not sources:
            return NO_CONTEXT
        parts = [f"{_first_sentence(body)} [Source {number}]" for number, _, body in sources[:2]]
        return "Based on the provided context, " + ". Additionally, ".join(parts) + "."

    async def complete(self, messages: list[ChatMessage], **kwargs) -> GenerationResult:
        start = time.perf_counter()
        text = self._answer(messages)
        return GenerationResult(text, self.model, 0, 0, (time.perf_counter() - start) * 1000, 0.0, "stop")

    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncGenerator[str, None]:
        for token in re.findall(r"\S+\s*", self._answer(messages)):
            await asyncio.sleep(0.05)
            yield token

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("FakeProvider does not embed")

    @property
    def cost_per_input_token(self) -> float:
        return 0.0

    @property
    def cost_per_output_token(self) -> float:
        return 0.0

    @property
    def context_window(self) -> int:
        return 128_000