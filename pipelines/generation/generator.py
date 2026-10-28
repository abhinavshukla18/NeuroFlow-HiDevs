import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from opentelemetry import context as otel_context
from opentelemetry import trace
from redis.asyncio import Redis

from config import get_settings
from db.pool import get_pool
from monitoring.metrics import generation_latency, llm_cost, lm_calls_total, queries_total
from pipelines.generation.citations import parse_citations
from pipelines.generation.prompt_builder import build_messages
from pipelines.ingestion.chunker import count_tokens
from pipelines.retrieval.pipeline import RetrievalPipeline
from providers.fake_provider import FakeProvider
from providers.router import DEFAULT_MODELS, RoutingCriteria
from services.pipeline_runtime import config_for

logger = logging.getLogger("neuroflow.generation")
tracer = trace.get_tracer("neuroflow.generation")
EVAL_QUEUE = "queue:evaluate"
PRICES = {m["model"]: (m["input_price"], m["output_price"]) for m in DEFAULT_MODELS}

_background: set[asyncio.Task] = set()
_redis: Redis | None = None


class RunNotAvailable(Exception):
    pass


def _redis_client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url)
    return _redis


def _enqueue_evaluation(run_id: str) -> None:
    task = asyncio.create_task(_redis_client().lpush(EVAL_QUEUE, json.dumps({"run_id": run_id})))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def ensure_default_pipeline() -> str:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            pid = await conn.fetchval(
                "INSERT INTO pipelines (name, config) VALUES ('default', '{}'::jsonb) "
                "ON CONFLICT (name) DO NOTHING RETURNING id"
            )
            if pid:
                await conn.execute(
                    "INSERT INTO pipeline_versions (pipeline_id, version, config) VALUES ($1, 1, '{}'::jsonb)", pid
                )
    return str(await pool.fetchval("SELECT id FROM pipelines WHERE name = 'default'"))


async def create_run(pipeline_id: str | None, query: str) -> str:
    pool = get_pool()
    pipeline_id = pipeline_id or await ensure_default_pipeline()
    version = await pool.fetchval("SELECT version FROM pipelines WHERE id = $1", pipeline_id)
    run_id = await pool.fetchval(
        "INSERT INTO pipeline_runs (pipeline_id, pipeline_version, query, status) "
        "VALUES ($1, $2, $3, 'queued') RETURNING id",
        pipeline_id, version, query,
    )
    return str(run_id)


async def _select_provider(routing):
    settings = get_settings()
    if not (settings.openai_api_key or settings.anthropic_api_key):
        provider = FakeProvider()
        return provider, provider.model
    from providers.client import get_client
    client = get_client()
    cfg = await client.router.select(
        RoutingCriteria(task_type=routing.task_type, max_cost_per_call=routing.max_cost_per_call)
    )
    return client._provider(cfg), cfg.model


def _public_citation(c: dict) -> dict:
    out = {"source": c["reference"], "chunk_id": c["chunk_id"], "document": c["document_name"], "page": c["page_number"]}
    if c.get("invalid_citation"):
        out["invalid_citation"] = True
    return out


async def run_events(run_id: str) -> AsyncGenerator[dict, None]:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE pipeline_runs SET status = 'running' WHERE id = $1 AND status = 'queued' "
        "RETURNING query, pipeline_id, pipeline_version", run_id,
    )
    if row is None:
        raise RunNotAvailable(run_id)
    query = row["query"]
    pipeline_id = str(row["pipeline_id"])
    started = time.perf_counter()

    root = tracer.start_span("generation.pipeline")
    root.set_attribute("pipeline_id", pipeline_id)
    root.set_attribute("run_id", run_id)
    root_ctx = trace.set_span_in_context(root)

    try:
        config = await config_for(row["pipeline_id"], row["pipeline_version"])
        yield {"type": "retrieval_start"}

        ctx_token = otel_context.attach(root_ctx)
        try:
            out = await RetrievalPipeline.from_settings().run(
                query,
                k=config.retrieval.top_k_after_rerank,
                token_budget=config.generation.max_context_tokens,
                retrieval=config.retrieval,
                pipeline_id=pipeline_id,
                run_id=run_id,
            )
        finally:
            otel_context.detach(ctx_token)

        retrieval_ms = round((time.perf_counter() - started) * 1000)
        ctx = out["context"]
        yield {"type": "retrieval_complete", "chunk_count": len(ctx.chunks_used), "sources": ctx.sources}

        with tracer.start_as_current_span("generation.prompt_build", context=root_ctx) as sp:
            sp.set_attribute("pipeline_id", pipeline_id)
            sp.set_attribute("run_id", run_id)
            messages = build_messages(query, ctx.context, out["query_type"], config.generation.system_prompt_variant)
            prompt_text = "\n\n".join(f"[{m.role}]\n{m.content}" for m in messages)
            sp.set_attribute("chunk_count", len(ctx.chunks_used))
            sp.set_attribute("token_count", count_tokens(prompt_text))
        await pool.execute(
            "UPDATE pipeline_runs SET prompt = $2, retrieved_chunk_ids = $3::uuid[], "
            "metadata = metadata || $4::jsonb WHERE id = $1",
            run_id, prompt_text, [c["chunk_id"] for c in ctx.chunks_used],
            json.dumps({"query_type": out["query_type"], "filters": out["filters"],
                        "retrieval_latency_ms": retrieval_ms, "chunks_used": len(ctx.chunks_used)}),
        )

        provider, model = await _select_provider(config.generation.model_routing)
        provider_name = type(provider).__name__.replace("Provider", "").lower()
        gen_started = time.perf_counter()
        parts: list[str] = []

        llm_span = tracer.start_span("generation.llm_call", context=root_ctx)
        llm_span.set_attribute("pipeline_id", pipeline_id)
        llm_span.set_attribute("run_id", run_id)
        llm_span.set_attribute("model", model)
        try:
            async for tok in provider.stream(messages, temperature=config.generation.temperature):
                parts.append(tok)
                yield {"type": "token", "delta": tok}
            response = "".join(parts)
            generation_ms = round((time.perf_counter() - gen_started) * 1000)
            in_tok, out_tok = count_tokens(prompt_text), count_tokens(response)
            in_price, out_price = PRICES.get(model, (0, 0))
            cost = (in_tok * in_price + out_tok * out_price) / 1_000_000
            llm_span.set_attribute("input_tokens", in_tok)
            llm_span.set_attribute("output_tokens", out_tok)
            llm_span.set_attribute("cost_usd", cost)
            llm_span.set_attribute("latency_ms", generation_ms)
        finally:
            llm_span.end()

        generation_latency.labels(model=model).observe(generation_ms / 1000)