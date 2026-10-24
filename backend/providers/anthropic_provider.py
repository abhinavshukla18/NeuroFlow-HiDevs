import asyncio
import time
from typing import AsyncGenerator

from anthropic import AsyncAnthropic, RateLimitError

from providers.base import BaseLLMProvider, ChatMessage, GenerationResult

# USD per million tokens (hardcoded; verify against Anthropic's pricing page)
PRICES = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
}
CONTEXT_WINDOWS = {"claude-haiku-4-5": 200_000, "claude-sonnet-4-5": 200_000}
MAX_RETRIES = 3
DEFAULT_MAX_TOKENS = 1024


class AnthropicProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5",
        embedder: BaseLLMProvider | None = None,
    ):
        self.model = model
        self.embedder = embedder  # Anthropic has no embeddings API; delegate if given
        self.client = AsyncAnthropic(api_key=api_key)

    @property
    def cost_per_input_token(self) -> float:
        return PRICES[self.model]["input"] / 1_000_000

    @property
    def cost_per_output_token(self) -> float:
        return PRICES[self.model]["output"] / 1_000_000

    @property
    def context_window(self) -> int:
        return CONTEXT_WINDOWS.get(self.model, 200_000)

    @staticmethod
    def _split(messages: list[ChatMessage]) -> tuple[str | None, list[dict]]:
        """System messages go top-level in the Anthropic API, not in messages."""
        system_parts = [m.content for m in messages if m.role == "system" and isinstance(m.content, str)]
        chat = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        return ("\n\n".join(system_parts) or None), chat

    def _params(self, messages: list[ChatMessage], kwargs: dict) -> dict:
        system, chat = self._split(messages)
        params = {"model": self.model, "messages": chat, "max_tokens": DEFAULT_MAX_TOKENS, **kwargs}
        if system:
            params["system"] = system
        return params

    @staticmethod
    def _delay(exc: RateLimitError, attempt: int) -> float:
        response = getattr(exc, "response", None)
        retry_after = response.headers.get("retry-after") if response is not None else None
        return float(retry_after) if retry_after else 2**attempt

    async def complete(self, messages: list[ChatMessage], **kwargs) -> GenerationResult:
        params = self._params(messages, kwargs)
        start = time.perf_counter()
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.client.messages.create(**params)
                break
            except RateLimitError as exc:
                if attempt == MAX_RETRIES:
                    raise
                await asyncio.sleep(self._delay(exc, attempt))
        latency_ms = (time.perf_counter() - start) * 1000
        usage = response.usage
        cost = (
            usage.input_tokens * self.cost_per_input_token
            + usage.output_tokens * self.cost_per_output_token
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return GenerationResult(
            content=text,
            model=self.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            finish_reason=response.stop_reason or "",
        )

    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncGenerator[str, None]:
        params = self._params(messages, kwargs)
        for attempt in range(MAX_RETRIES + 1):
            started = False
            try:
                async with self.client.messages.stream(**params) as stream:
                    async for text in stream.text_stream:
                        started = True
                        yield text
                return
            except RateLimitError as exc:
                if started or attempt == MAX_RETRIES:
                    raise
                await asyncio.sleep(self._delay(exc, attempt))

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.embedder is None:
            raise NotImplementedError(
                "Anthropic has no embeddings API. Pass embedder=OpenAIProvider(...) to delegate."
            )
        return await self.embedder.embed(texts)