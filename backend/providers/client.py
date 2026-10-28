from redis.asyncio import Redis
from opentelemetry import trace

from config import Settings, get_settings
from monitoring.metrics import llm_cost, lm_calls_total
from providers.anthropic_provider import AnthropicProvider
from providers.base import BaseLLMProvider, ChatMessage, GenerationResult
from providers.openai_provider import OpenAIProvider
from providers.router import ModelConfig, ModelRouter, RoutingCriteria
from resilience.circuit_breaker import circuit_breaker
from resilience.rate_limiter import acquire_llm_token
from resilience.timeout_manager import with_timeout

tracer = trace.get_tracer("neuroflow.providers")


class NeuroFlowClient:
    def __init__(self, redis: Redis, settings: Settings):
        self.redis = redis
        self.settings = settings
        self.router = ModelRouter(redis)
        self._providers: dict[tuple[str, str], BaseLLMProvider] = {}

    def _provider(self, cfg: ModelConfig) -> BaseLLMProvider:
        key = (cfg.provider, cfg.model)
        if key in self._providers:
            return self._providers[key]

        if cfg.provider == "openai":
            if not self.settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is not set")
            if "embedding" in cfg.task_types:
                provider = OpenAIProvider(self.settings.openai_api_key, embedding_model=cfg.model)
            else:
                provider = OpenAIProvider(self.settings.openai_api_key, model=cfg.model)
        elif cfg.provider == "anthropic":
            if not self.settings.anthropic_api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is not set")
            provider = AnthropicProvider(self.settings.anthropic_api_key, model=cfg.model)
        else:
            raise ValueError(f"Unknown provider: {cfg.provider}")

        self._providers[key] = provider
        return provider

    async def _record(self, model: str, cost_usd: float) -> None:
        await self.redis.incr(f"metrics:model:{model}:calls")
        await self.redis.incrbyfloat(f"metrics:model:{model}:cost_usd", cost_usd)

    async def chat(
        self, messages: list[ChatMessage], routing_criteria: RoutingCriteria | None = None, **kwargs
    ) -> GenerationResult:
        criteria = routing_criteria or RoutingCriteria()
        cfg = await self.router.select(criteria)
        provider = self._provider(cfg)

        with tracer.start_as_current_span("llm.chat") as span:
            span.set_attribute("model", cfg.model)
            if cfg.provider == "openai":
                await acquire_llm_token("openai")
            async with circuit_breaker(cfg.provider):
                result = await with_timeout("chat_completion", provider.complete(messages, **kwargs))
            span.set_attribute("input_tokens", result.input_tokens)
            span.set_attribute("output_tokens", result.output_tokens)
            span.set_attribute("cost_usd", result.cost_usd)
            span.set_attribute("latency_ms", result.latency_ms)

        lm_calls_total.labels(
            provider=cfg.provider, model=cfg.model, task_type=criteria.task_type or "chat"
        ).inc()
        llm_cost.labels(model=cfg.model).observe(result.cost_usd)
        await self._record(cfg.model, result.cost_usd)
        return result

    async def embed(self, texts: list[str]) -> list[list[float]]:
        cfg = await self.router.select(RoutingCriteria(task_type="embedding"))
        provider = self._provider(cfg)

        with tracer.start_as_current_span("llm.embed") as span:
            if cfg.provider == "openai":
                await acquire_llm_token("openai")
            async with circuit_breaker(cfg.provider):
                vectors = await with_timeout("embedding", provider.embed(texts))
            approx_tokens = sum(len(t) for t in texts) // 4  # estimate: ~4 chars per token
            cost = approx_tokens * cfg.input_price / 1_000_000
            span.set_attribute("model", cfg.model)
            span.set_attribute("input_tokens", approx_tokens)
            span.set_attribute("output_tokens", 0)
            span.set_attribute("cost_usd", cost)

        lm_calls_total.labels(provider=cfg.provider, model=cfg.model, task_type="embedding").inc()
        llm_cost.labels(model=cfg.model).observe(cost)
        await self._record(cfg.model, cost)
        return vectors


_client: NeuroFlowClient | None = None


def get_client() -> NeuroFlowClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = NeuroFlowClient(Redis.from_url(settings.redis_url), settings)
    return _client