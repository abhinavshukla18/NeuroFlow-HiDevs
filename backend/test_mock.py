import asyncio
import json
import time
from types import SimpleNamespace

import httpx
from openai import RateLimitError
from opentelemetry import trace
from redis.asyncio import Redis

import main  # noqa: F401  (sets up tracing to Jaeger)
from config import get_settings
from providers.base import ChatMessage, GenerationResult
from providers.client import NeuroFlowClient
from providers.openai_provider import OpenAIProvider
from providers.router import ROUTER_KEY, ModelRouter, RoutingCriteria

MSGS = [ChatMessage(role="user", content="hi")]

TEST_MODELS = [
    {"provider": "openai", "model": "fake-text", "input_price": 0.1, "output_price": 0.1,
     "context_window": 128_000, "vision": False, "capable": False, "fine_tuned": False,
     "task_types": ["rag_generation"]},
    {"provider": "openai", "model": "fake-vision", "input_price": 1.0, "output_price": 1.0,
     "context_window": 128_000, "vision": True, "capable": False, "fine_tuned": False,
     "task_types": ["rag_generation"]},
]


def make_provider(create):
    provider = OpenAIProvider(api_key="test")
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return provider


def chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


async def test_stream():
    async def create(**kwargs):
        async def gen():
            for t in ["Hel", "lo", " wor", "ld"]:
                await asyncio.sleep(0.2)
                yield chunk(t)
        return gen()

    times, start = [], time.perf_counter()
    async for token in make_provider(create).stream(MSGS):
        times.append(time.perf_counter() - start)
        print(token, end="", flush=True)
    print()
    assert len(times) == 4 and times[-1] - times[0] > 0.4
    print("PASS stream yields progressively", [round(t, 2) for t in times])


async def test_retry():
    calls = {"n": 0}

    async def create(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            response = httpx.Response(429, headers={"retry-after": "0"},
                                      request=httpx.Request("POST", "http://test"))
            raise RateLimitError("rate limited", response=response, body=None)
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
        )

    result = await make_provider(create).complete(MSGS)
    assert calls["n"] == 3 and result.content == "ok"
    print("PASS 429 retried twice, succeeded on attempt 3")


class FakeProvider:
    async def complete(self, messages, **kwargs):
        return GenerationResult("ok", "fake-text", 100, 50, 1.0, 0.01, "stop")


async def run():
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)

    await test_stream()
    await test_retry()

    await redis.set(ROUTER_KEY, json.dumps(TEST_MODELS))
    router = ModelRouter(redis)
    assert (await router.select(RoutingCriteria(require_vision=True))).model == "fake-vision"
    assert (await router.select(RoutingCriteria())).model == "fake-text"
    print("PASS vision routes to vision model, default routes to cheapest")

    await redis.delete("metrics:model:fake-text:calls", "metrics:model:fake-text:cost_usd")
    client = NeuroFlowClient(redis, settings)
    client._providers[("openai", "fake-text")] = FakeProvider()
    await client.chat(MSGS)
    await client.chat(MSGS)
    calls = int(await redis.get("metrics:model:fake-text:calls"))
    cost = float(await redis.get("metrics:model:fake-text:cost_usd"))
    assert calls == 2 and abs(cost - 0.02) < 1e-9
    print("PASS redis counters: calls =", calls, "cost =", cost)

    await redis.delete(ROUTER_KEY)  # defaults re-register on next use
    await redis.aclose()
    trace.get_tracer_provider().shutdown()  # flush spans to Jaeger


asyncio.run(run())