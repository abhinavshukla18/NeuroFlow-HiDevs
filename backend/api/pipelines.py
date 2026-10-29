import json
import uuid

import asyncpg
from db.pool import get_pool
from fastapi import APIRouter, Depends, HTTPException
from models.pipeline import PipelineConfig
from pydantic import ValidationError
from security.auth import require_scope

router = APIRouter()


def _j(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


async def load_pipeline(pipeline_id: uuid.UUID):
    row = await get_pool().fetchrow(
        "SELECT id, name, description, config, version, status, created_at, updated_at FROM pipelines WHERE id = $1",
        pipeline_id,
    )
    if row is None:
        raise HTTPException(404, "Pipeline not found")
    return row


@router.post("/pipelines", status_code=201, dependencies=[Depends(require_scope("admin"))])
@router.patch("/pipelines/{pipeline_id}", dependencies=[Depends(require_scope("admin"))])
@router.delete("/pipelines/{pipeline_id}", dependencies=[Depends(require_scope("admin"))])
async def create_pipeline(cfg: PipelineConfig):
    stored = json.dumps(cfg.stored())
    try:
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                pid = await conn.fetchval(
                    "INSERT INTO pipelines (name, description, config, version, status) "
                    "VALUES ($1, $2, $3::jsonb, 1, 'active') RETURNING id",
                    cfg.name, cfg.description, stored,
                )
                await conn.execute(
                    "INSERT INTO pipeline_versions (pipeline_id, version, config) VALUES ($1, 1, $2::jsonb)",
                    pid, stored,
                )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "A pipeline with this name already exists")
    return {"pipeline_id": str(pid), "version": 1}


@router.get("/pipelines")
async def list_pipelines(include_archived: bool = False):
    rows = await get_pool().fetch(
        "SELECT p.id, p.name, p.description, p.version, p.status, p.created_at, "
        "r.created_at AS last_run_at, r.latency_ms AS last_latency_ms, r.status AS last_run_status, "
        "(SELECT count(*) FROM pipeline_runs WHERE pipeline_id = p.id) AS run_count, "
        "(SELECT round(avg(e.overall_score)::numeric, 3) FROM evaluations e "
        " JOIN pipeline_runs pr ON pr.id = e.run_id WHERE pr.pipeline_id = p.id) AS avg_overall_score "
        "FROM pipelines p LEFT JOIN LATERAL (SELECT created_at, latency_ms, status FROM pipeline_runs "
        " WHERE pipeline_id = p.id ORDER BY created_at DESC LIMIT 1) r ON true "
        "WHERE ($1 OR p.status <> 'archived') ORDER BY p.created_at",
        include_archived,
    )
    return [{**dict(r), "id": str(r["id"])} for r in rows]


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: uuid.UUID):
    row = await load_pipeline(pipeline_id)
    pool = get_pool()
    scores = await pool.fetchrow(
        "SELECT count(e.id) AS evaluated_runs, round(avg(e.faithfulness)::numeric, 3) AS faithfulness, "
        "round(avg(e.answer_relevance)::numeric, 3) AS answer_relevance, "
        "round(avg(e.context_precision)::numeric, 3) AS context_precision, "
        "round(avg(e.context_recall)::numeric, 3) AS context_recall, "
        "round(avg(e.overall_score)::numeric, 3) AS overall_score "
        "FROM evaluations e JOIN pipeline_runs pr ON pr.id = e.run_id WHERE pr.pipeline_id = $1",
        pipeline_id,
    )
    versions = await pool.fetch(
        "SELECT version, config, created_at FROM pipeline_versions WHERE pipeline_id = $1 ORDER BY version",
        pipeline_id,
    )
    return {
        "id": str(row["id"]), "name": row["name"], "description": row["description"],
        "version": row["version"], "status": row["status"], "config": _j(row["config"]),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "evaluation": dict(scores),
        "versions": [{"version": v["version"], "config": _j(v["config"]), "created_at": v["created_at"]} for v in versions],
    }


@router.patch("/pipelines/{pipeline_id}")
async def update_pipeline(pipeline_id: uuid.UUID, body: dict):
    row = await load_pipeline(pipeline_id)
    current = {**_j(row["config"]), "name": row["name"], "description": row["description"]}
    try:
        cfg = PipelineConfig(**_deep_merge(current, body))
    except ValidationError as exc:
        raise HTTPException(422, json.loads(exc.json()))

    new_version = row["version"] + 1
    stored = json.dumps(cfg.stored())
    try:
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO pipeline_versions (pipeline_id, version, config) VALUES ($1, $2, $3::jsonb)",
                    pipeline_id, new_version, stored,
                )
                await conn.execute(
                    "UPDATE pipelines SET name = $2, description = $3, config = $4::jsonb, version = $5, "
                    "updated_at = NOW() WHERE id = $1",
                    pipeline_id, cfg.name, cfg.description, stored, new_version,
                )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "A pipeline with this name already exists")
    return {"pipeline_id": str(pipeline_id), "version": new_version}


@router.delete("/pipelines/{pipeline_id}")
async def archive_pipeline(pipeline_id: uuid.UUID):
    await load_pipeline(pipeline_id)
    await get_pool().execute(
        "UPDATE pipelines SET status = 'archived', updated_at = NOW() WHERE id = $1", pipeline_id
    )
    return {"pipeline_id": str(pipeline_id), "status": "archived"}