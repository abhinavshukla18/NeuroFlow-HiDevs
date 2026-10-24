import json
from dataclasses import dataclass, field

from redis.asyncio import Redis

ROUTER_KEY = "router:models"
LONG_CONTEXT_MIN = 100_000

DEFAULT_MODELS = [
    {"provider": "openai", "model": "gpt-4o-mini", "input_price": 0.15, "output_price": 0.60,
     "context_window": 128_000, "vision": True, "capable": False, "fine_tuned": False,
     "task_types": ["rag_generation", "classification"]},
    {"provider": "openai", "model": "gpt-4o", "input_price": 2.50, "output_price": 10.00,
     "context_window": 128_000, "vision": True, "capable": True, "fine_tuned": False,
     "task_types": ["rag_generation", "evaluation", "classification"]},
    {"provider": "anthropic", "model": "claude-haiku-4-5", "input_price": 1.00, "output_price": 5.00,
     "context_window": 200_000, "vision": True, "capable": False, "fine_tuned": False,
     "task_types": ["rag_generation", "classification"]},
    {"provider": "anthropic", "model": "claude-sonnet-4-5", "input_price": 3.00, "output_price": 15.00,
     "context_window": 200_000, "vision": True, "capable": True, "fine_tuned": False,
     "task_types": ["rag_generation", "evaluation", "classification"]},
    {"provider": "openai", "model": "text-embedding-3-small", "input_price": 0.02, "output_price": 0.0,
     "context_window": 8_191, "vision": False, "capable": False, "fine_tuned": False,
     "task_types": ["embedding"]},
]


class NoModelAvailable(Exception):
    pass


@dataclass
class RoutingCriteria:
    task_type: str = "rag_generation"  # rag_generation | evaluation | embedding | classification
    max_cost_per_call: float | None = None
    require_vision: bool = False
    require_long_context: bool = False  # > 32k tokens
    latency_budget_ms: int | None = None
    prefer_fine_tuned: bool = False
    estimated_input_tokens: int = 1000
    estimated_output_tokens: int = 500


@dataclass
class ModelConfig:
    provider: str
    model: str
    input_price: float  # USD per million tokens
    output_price: float
    context_window: int
    vision: bool = False
    capable: bool = False
    fine_tuned: bool = False
    task_types: list[str] = field(default_factory=list)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_price + output_tokens * self.output_price) / 1_000_000


class ModelRouter:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def get_models(self) -> list[ModelConfig]:
        raw = await self.redis.get(ROUTER_KEY)
        if raw is None:
            await self.register_models(DEFAULT_MODELS)
            data = DEFAULT_MODELS
        else:
            data = json.loads(raw)
        return [ModelConfig(**item) for item in data]

    async def register_models(self, models: list[dict]) -> None:
        await self.redis.set(ROUTER_KEY, json.dumps(models))

    async def select(self, criteria: RoutingCriteria) -> ModelConfig:
        candidates = [m for m in await self.get_models() if criteria.task_type in m.task_types]

        if criteria.task_type == "evaluation":
            candidates = [m for m in candidates if m.capable and not m.fine_tuned]
        if criteria.require_vision:
            candidates = [m for m in candidates if m.vision]
        if criteria.require_long_context:
            candidates = [m for m in candidates if m.context_window > LONG_CONTEXT_MIN]
        if criteria.max_cost_per_call is not None:
            candidates = [
                m for m in candidates
                if m.estimate_cost(criteria.estimated_input_tokens, criteria.estimated_output_tokens)
                <= criteria.max_cost_per_call
            ]

        if criteria.prefer_fine_tuned and criteria.task_type != "evaluation":
            fine_tuned = [m for m in candidates if m.fine_tuned]
            if fine_tuned:
                candidates = fine_tuned

        if not candidates:
            raise NoModelAvailable(f"No model satisfies {criteria}")

        return min(
            candidates,
            key=lambda m: m.estimate_cost(criteria.estimated_input_tokens, criteria.estimated_output_tokens),
        )