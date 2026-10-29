import uuid

from db.pool import get_pool
from fastapi import APIRouter, Query
from providers.router import DEFAULT_MODELS

from api.pipelines import load_pipeline

router = APIRouter()
PRICES = {m["model"]: (m["input_price"], m["output_price"]) for m in DEFAULT_MODELS}


def _round(value, places=3):
    return None if value is None else round(float(value), places)


def _pcts(values) -> dict:
    values = values or [None, None, None]
    return {"p50": _round(values[0], 1), "p95": _round(values[1], 1), "p99": _round(values[2], 1)}


@router.get("/pipelines/{pipeline_id}/runs")
async def pipeline_runs(pipeline_id: uuid.UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    await load_pipeline(pipeline_id)
    pool = get_pool()
    total = await pool.fetchval("SELECT count(*) FROM pipeline_runs WHERE pipeline_id = $1", pipeline_id)
    rows = await pool.fetch(
        "SELECT r.id, r.query, r.status, r.pipeline_version, r.model_used, r.latency_ms, r.input_tokens, "
        "r.output_tokens, r.created_at, e.faithfulness, e.answer_relevance, e.context_precision, "
        "e.context_recall, e.overall_score, e.user_rating "
        "FROM pipeline_runs r LEFT JOIN evaluations e ON e.run_id = r.id "
        "WHERE r.pipeline_id = $1 ORDER BY r.created_at DESC LIMIT $2 OFFSET $3",
        pipeline_id, page_size, (page - 1) * page_size,
    )
    items = []
    for r in rows:
        items.append({
            "run_id": str(r["id"]), "query": r["query"], "status": r["status"],
            "pipeline_version": r["pipeline_version"], "model_used": r["model_used"],
            "latency_ms": r["latency_ms"], "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"],
            "created_at": r["created_at"], "user_rating": r["user_rating"],
            "evaluation": {k: _round(r[k]) for k in
                           ("faithfulness", "answer_relevance", "context_precision", "context_recall", "overall_score")},
        })
    return {"page": page, "page_size": page_size, "total": total, "items": items}


@router.get("/pipelines/{pipeline_id}/analytics")
async def pipeline_analytics(pipeline_id: uuid.UUID):
    await load_pipeline(pipeline_id)
    pool = get_pool()

    stats = await pool.fetchrow(
        "SELECT count(*) AS completed_runs, "
        "percentile_cont(ARRAY[0.5, 0.95, 0.99]) WITHIN GROUP (ORDER BY (metadata->>'retrieval_latency_ms')::float) AS retrieval, "
        "percentile_cont(ARRAY[0.5, 0.95, 0.99]) WITHIN GROUP (ORDER BY latency_ms) AS total, "
        "avg((metadata->>'generation_latency_ms')::float) AS avg_generation_ms "
        "FROM pipeline_runs WHERE pipeline_id = $1 AND status = 'complete'",
        pipeline_id,
    )
    scores = await pool.fetchrow(
        "SELECT avg(e.faithfulness) AS faithfulness, avg(e.answer_relevance) AS answer_relevance, "
        "avg(e.context_precision) AS context_precision, avg(e.context_recall) AS context_recall, "
        "avg(e.overall_score) AS overall_score FROM evaluations e "
        "JOIN pipeline_runs r ON r.id = e.run_id WHERE r.pipeline_id = $1",
        pipeline_id,
    )
    usage = await pool.fetch(
        "SELECT model_used, count(*) AS n, coalesce(sum(input_tokens), 0) AS it, coalesce(sum(output_tokens), 0) AS ot "
        "FROM pipeline_runs WHERE pipeline_id = $1 AND status = 'complete' GROUP BY model_used",
        pipeline_id,
    )
    total_cost = sum(
        u["it"] * PRICES.get(u["model_used"], (0, 0))[0] / 1_000_000
        + u["ot"] * PRICES.get(u["model_used"], (0, 0))[1] / 1_000_000
        for u in usage
    )
    completed = stats["completed_runs"]
    daily = await pool.fetch(
        "SELECT d::date AS day, count(r.id) AS queries "
        "FROM generate_series((current_date - 29)::timestamp, current_date::timestamp, interval '1 day') d "
        "LEFT JOIN pipeline_runs r ON r.pipeline_id = $1 AND r.created_at::date = d::date "
        "GROUP BY d ORDER BY d",
        pipeline_id,
    )
    return {
        "pipeline_id": str(pipeline_id),
        "completed_runs": completed,
        "retrieval_latency_ms": _pcts(stats["retrieval"]),
        "total_latency_ms": _pcts(stats["total"]),
        "avg_generation_latency_ms": _round(stats["avg_generation_ms"], 1),
        "avg_evaluation_scores": {k: _round(v) for k, v in dict(scores).items()},
        "cost_per_query_usd": round(total_cost / completed, 6) if completed else None,
        "total_cost_usd": round(total_cost, 6),
        "queries_per_day": [{"date": str(d["day"]), "queries": d["queries"]} for d in daily],
    }