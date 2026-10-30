import json

from db.pool import get_pool
from models.pipeline import PipelineConfig


async def config_for(pipeline_id, version=None) -> PipelineConfig:
    row = await get_pool().fetchrow(
        "SELECT p.name, p.description, v.config FROM pipelines p "
        "JOIN pipeline_versions v ON v.pipeline_id = p.id AND v.version = COALESCE($2, p.version) "
        "WHERE p.id = $1",
        pipeline_id, version,
    )
    if row is None:
        raise ValueError(f"Pipeline {pipeline_id} (version {version}) not found")
    config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
    return PipelineConfig.from_row(row["name"], row["description"], config)