import asyncio
import time
from typing import AsyncGenerator

from openai import AsyncOpenAI, RateLimitError

from providers.base import BaseLLMProvider, ChatMessage, GenerationResult

# USD per million tokens
PRICES = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}
CONTEXT_WINDOWS = {"gpt-4o": 128_000, "gpt-4o-mini": 128_000}
MAX_RETRIES = 3
EMBED_BATCH_SIZE = 100


class OpenAIProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        embedding_model: str = "text-embedding-3-small",
    ):
        self.model = model
        self.embedding_model = embedding_model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    @property
    def cost_per_input_token(self) -> float:
        return PRICES[self.model]["input"] / 1_000_000

    @property
    def cost_per_output_token(self) -> float:
        return PRICES[self.model]["output"] / 1_000_000

    @property
    def context_window(self) -> int:
        return CONTEXT_WINDOWS.get(self.model, 128_000)

    @staticmethod
    def _to_api(messages: list[ChatMessage]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def _with_retry(self, call):
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await call()
            except RateLimitError as exc:
                if attempt == MAX_RETRIES:
                    raise
                retry_after = None
                response = getattr(exc, "response", None)
                if response is not None:
                    retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after else 2**attempt
                await asyncio.sleep(delay)

    async def complete(self, messages: list[ChatMessage], **kwargs) -> GenerationResult:
        start = time.perf_counter()
        response = await self._with_retry(
            lambda: self.client.chat.completions.create(
                model=self.model, messages=self._to_api(messages), **kwargs
            )
        )
        latency_ms = (time.perf_counter() - start) * 1000
        usage = response.usage
        cost = (
            usage.prompt_tokens * self.cost_per_input_token
            + usage.completion_tokens * self.cost_per_output_token
        )
        choice = response.choices[0]
        return GenerationResult(
            content=choice.message.content or "",
            model=self.model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            finish_reason=choice.finish_reason or "",
        )

    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncGenerator[str, None]:
        stream = await self._with_retry(
            lambda: self.client.chat.completions.create(
                model=self.model, messages=self._to_api(messages), stream=True, **kwargs
            )
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            response = await self._with_retry(
                lambda b=batch: self.client.embeddings.create(
                    model=self.embedding_model, input=b
                )
            )
            vectors.extend(item.embedding for item in response.data)
        return vectors