import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from redis.asyncio import Redis

from config import get_settings
from db.pool import get_pool
from pipelines.generation.citations import parse_citations
from pipelines.generation.prompt_builder import build_messages
from pipelines.ingestion.chunker import count_tokens
from pipelines.retrieval.pipeline import RetrievalPipeline
from providers.fake_provider import FakeProvider
from providers.router import RoutingCriteria

logger = logging.getLogger("neuroflow.generation")
EVAL_QUEUE = "queue:evaluate"

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
    await pool.execute(
        "INSERT INTO pipelines (name, config) VALUES ('default', '{}'::jsonb) ON CONFLICT (name) DO NOTHING"
    )
    return str(await pool.fetchval("SELECT id FROM pipelines WHERE name = 'default'"))


async def create_run(pipeline_id: str | None, query: str) -> str:
    pool = get_pool()
    pipeline_id = pipeline_id or await ensure_default_pipeline()
    run_id = await pool.fetchval(
        "INSERT INTO pipeline_runs (pipeline_id, query, status) VALUES ($1, $2, 'queued') RETURNING id",
        pipeline_id, query,
    )
    return str(run_id)


async def _select_provider():
    settings = get_settings()
    if not (settings.openai_api_key or settings.anthropic_api_key):
        provider = FakeProvider()
        return provider, provider.model
    from providers.client import get_client
    client = get_client()
    cfg = await client.router.select(RoutingCriteria(task_type="rag_generation"))
    return client._provider(cfg), cfg.model


def _public_citation(c: dict) -> dict:
    out = {
        "source": c["reference"],
        "chunk_id": c["chunk_id"],
        "document": c["document_name"],
        "page": c["page_number"],
    }
    if c.get("invalid_citation"):
        out["invalid_citation"] = True
    return out


async def run_events(run_id: str) -> AsyncGenerator[dict, None]:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE pipeline_runs SET status = 'running' WHERE id = $1 AND status = 'queued' RETURNING query", run_id
    )
    if row is None:
        raise RunNotAvailable(run_id)
    query = row["query"]
    started = time.perf_counter()

    try:
        yield {"type": "retrieval_start"}
        out = await RetrievalPipeline.from_settings().run(query)
        ctx = out["context"]
        yield {"type": "retrieval_complete", "chunk_count": len(ctx.chunks_used), "sources": ctx.sources}

        messages = build_messages(query, ctx.context, out["query_type"])
        prompt_text = "\n\n".join(f"[{m.role}]\n{m.content}" for m in messages)
        await pool.execute(
            "UPDATE pipeline_runs SET prompt = $2, retrieved_chunk_ids = $3::uuid[], "
            "metadata = metadata || $4::jsonb WHERE id = $1",
            run_id, prompt_text, [c["chunk_id"] for c in ctx.chunks_used],
            json.dumps({"query_type": out["query_type"], "filters": out["filters"]}),
        )

        provider, model = await _select_provider()
        parts: list[str] = []
        async for token in provider.stream(messages):
            parts.append(token)
            yield {"type": "token", "delta": token}
        response = "".join(parts)

        citations = [c.to_dict() for c in parse_citations(response, ctx.chunks_used)]
        latency_ms = round((time.perf_counter() - started) * 1000)
        await pool.execute(
            "UPDATE pipeline_runs SET generation = $2, input_tokens = $3, output_tokens = $4, "
            "model_used = $5, latency_ms = $6, status = 'complete', metadata = metadata || $7::jsonb WHERE id = $1",
            run_id, response, count_tokens(prompt_text), count_tokens(response), model, latency_ms,
            json.dumps({"citations": citations}),
        )
        _enqueue_evaluation(run_id)  # not awaited: generation never waits on evaluation
        logger.info(json.dumps({"event": "generation_complete", "run_id": run_id, "latency_ms": latency_ms}))
        yield {"type": "done", "run_id": run_id, "citations": [_public_citation(c) for c in citations]}

    except Exception as exc:
        logger.exception("Generation failed for %s", run_id)
        await pool.execute(
            "UPDATE pipeline_runs SET status = 'failed', "
            "metadata = metadata || jsonb_build_object('error', $2::text) WHERE id = $1",
            run_id, str(exc)[:500],
        )
        yield {"type": "error", "message": str(exc)}


async def generate_full(run_id: str) -> dict:
    response, done, error = [], None, None
    async for event in run_events(run_id):
        if event["type"] == "token":
            response.append(event["delta"])
        elif event["type"] == "done":
            done = event
        elif event["type"] == "error":
            error = event["message"]
    if error:
        return {"run_id": run_id, "status": "failed", "error": error}
    return {"run_id": run_id, "status": "complete", "response": "".join(response), "citations": done["citations"]}