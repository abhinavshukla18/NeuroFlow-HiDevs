import asyncio
import json
import logging
import time

from opentelemetry import trace
from redis.asyncio import Redis

from config import get_settings
from db.pool import get_pool
from evaluation.metrics import llm_available
from evaluation.metrics.answer_relevance import evaluate_answer_relevance
from evaluation.metrics.context_precision import evaluate_context_precision
from evaluation.metrics.context_recall import evaluate_context_recall
from evaluation.metrics.faithfulness import evaluate_faithfulness
from pipelines.generation.prompt_builder import build_system_prompt
from services.pipeline_runtime import config_for

logger = logging.getLogger("neuroflow.evaluation")
tracer = trace.get_tracer("neuroflow.evaluation")

EVAL_QUEUE = "queue:evaluate"
TRAINING_THRESHOLD = 0.8
WEIGHTS = {"faithfulness": 0.35, "answer_relevance": 0.30, "context_precision": 0.20, "context_recall": 0.15}


def _as_dict(value) -> dict:
    if isinstance(value, str):
        return json.loads(value)
    return dict(value or {})


async def _timed(name: str, coro):
    start = time.perf_counter()
    value = await coro
    return name, value, round((time.perf_counter() - start) * 1000)


def overall_score(scores: dict) -> float:
    return sum(WEIGHTS[name] * scores[name] for name in WEIGHTS)


class EvaluationJudge:
    def __init__(self, client=None):
        self.client = client

    @classmethod
    def from_settings(cls) -> "EvaluationJudge":
        settings = get_settings()
        client = None
        if settings.openai_api_key or settings.anthropic_api_key:
            from providers.client import get_client
            client = get_client()
        return cls(client)

    async def _load(self, run_id: str):
        pool = get_pool()
        run = await pool.fetchrow(
            "SELECT id, query, generation, retrieved_chunk_ids, metadata, pipeline_id, pipeline_version FROM pipeline_runs WHERE id = $1"
        )
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        if not run["generation"]:
            raise ValueError(f"Run {run_id} has no generation to evaluate")
        chunk_ids = list(run["retrieved_chunk_ids"] or [])
        rows = await pool.fetch(
            "SELECT c.id, c.content, d.filename FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.id = ANY($1::uuid[])",
            chunk_ids,
        )
        by_id = {r["id"]: r for r in rows}
        ordered = [by_id[cid] for cid in chunk_ids if cid in by_id]
        chunks = [r["content"] for r in ordered]
        context = "\n\n".join(f"[Source {i} — {r['filename']}]\n{r['content']}" for i, r in enumerate(ordered, 1))
        return run, chunks, context

    async def evaluate(self, run_id: str) -> dict:
        run, chunks, context = await self._load(run_id)
        threshold = (await config_for(run["pipeline_id"],run["pipeline_version"])).evaluation.training_threshold
        query, answer = run["query"], run["generation"]

        with tracer.start_as_current_span("evaluation.judge") as span:
            started = time.perf_counter()
            results = await asyncio.gather(
                _timed("faithfulness", evaluate_faithfulness(query, answer, context, self.client)),
                _timed("answer_relevance", evaluate_answer_relevance(query, answer, self.client)),
                _timed("context_precision", evaluate_context_precision(query, chunks, answer, self.client)),
                _timed("context_recall", evaluate_context_recall(query, chunks, answer, self.client)),
            )
            total_ms = round((time.perf_counter() - started) * 1000)
            scores = {name: value for name, value, _ in results}
            timings = {name: ms for name, _, ms in results}
            overall = overall_score(scores)

            for name, value in scores.items():
                span.set_attribute(name, value)
            span.set_attribute("overall_score", overall)
            span.set_attribute("run_id", run_id)

            judge_model = "llm-judge" if llm_available() else "heuristic-fallback"
            await self._store(run_id, scores, overall, judge_model)
            await update_calibration_flag(run_id)
            created_pair = overall > threshold and await self._store_training_pair(run, context)

            logger.info(json.dumps({
                "event": "evaluation_complete", "run_id": run_id, "overall": round(overall, 3),
                "total_ms": total_ms, "metric_ms": timings, "training_pair": bool(created_pair),
            }))
            return {"run_id": run_id, **scores, "overall_score": overall, "total_ms": total_ms,
                    "metric_ms": timings, "training_pair": bool(created_pair)}

    async def _store(self, run_id: str, scores: dict, overall: float, judge_model: str) -> None:
        await get_pool().execute(
            "INSERT INTO evaluations (run_id, faithfulness, answer_relevance, context_precision, "
            "context_recall, overall_score, judge_model) VALUES ($1, $2, $3, $4, $5, $6, $7) "
            "ON CONFLICT (run_id) DO UPDATE SET faithfulness = EXCLUDED.faithfulness, "
            "answer_relevance = EXCLUDED.answer_relevance, context_precision = EXCLUDED.context_precision, "
            "context_recall = EXCLUDED.context_recall, overall_score = EXCLUDED.overall_score, "
            "judge_model = EXCLUDED.judge_model, evaluated_at = NOW()",
            run_id, scores["faithfulness"], scores["answer_relevance"], scores["context_precision"],
            scores["context_recall"], overall, judge_model,

        try:
            import json as _json
            r = Redis.from_url(get_settings().redis_url)
            await r.publish("evaluations:new", _json.dumps({"run_id": str(run_id)}))
            await r.aclose()
        except Exception:
            pass
        )

    async def _store_training_pair(self, run, context: str) -> bool:
        metadata = _as_dict(run["metadata"])
        system_prompt = build_system_prompt(metadata.get("query_type", "factual"))
        user_message = f"<context>\n{context}\n</context>\n\n{run['query']}"
        status = await get_pool().execute(
            "INSERT INTO training_pairs (run_id, system_prompt, user_message, assistant_message, quality_score) "
            "SELECT $1, $2, $3, $4, (SELECT overall_score FROM evaluations WHERE run_id = $1) "
            "WHERE NOT EXISTS (SELECT 1 FROM training_pairs WHERE run_id = $1)",
            run["id"], system_prompt, user_message, run["generation"],
        )
        return status.endswith("1")


async def consume_forever(judge: EvaluationJudge, stop: asyncio.Event) -> None:
    redis = Redis.from_url(get_settings().redis_url)
    try:
        while not stop.is_set():
            item = await redis.brpop(EVAL_QUEUE, timeout=5)
            if item is None:
                continue
            try:
                await judge.evaluate(json.loads(item[1])["run_id"])
            except Exception:
                logger.exception("Evaluation failed for %s", item[1])
    finally:
        await redis.aclose()

async def update_calibration_flag(run_id: str) -> bool | None:
    pool = get_pool()
    row = await pool.fetchrow("SELECT overall_score, user_rating FROM evaluations WHERE run_id = $1", run_id)
    if row is None or row["overall_score"] is None or row["user_rating"] is None:
        return None
    needed = abs(row["overall_score"] - row["user_rating"] / 5) > 0.3
    await pool.execute(
        "UPDATE evaluations SET metadata = metadata || $2::jsonb WHERE run_id = $1",
        run_id, json.dumps({"calibration_needed": needed}),
    )
    return needed