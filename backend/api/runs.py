import uuid

from db.pool import get_pool
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from evaluation.judge import update_calibration_flag

router = APIRouter()


class RatingRequest(BaseModel):
    rating: int = Field(ge=1, le=5, description="1 (bad) to 5 (excellent).", examples=[5])


@router.patch("/runs/{run_id}/rating")
async def rate_run(run_id: uuid.UUID, body: RatingRequest):
    pool = get_pool()
    if not await pool.fetchval("SELECT 1 FROM pipeline_runs WHERE id = $1", run_id):
        raise HTTPException(404, "Run not found")
    await pool.execute(
        "INSERT INTO evaluations (run_id, user_rating) VALUES ($1, $2) "
        "ON CONFLICT (run_id) DO UPDATE SET user_rating = EXCLUDED.user_rating",
        run_id, body.rating,
    )
    flagged = await update_calibration_flag(str(run_id))
    return {"run_id": str(run_id), "rating": body.rating, "calibration_needed": flagged}