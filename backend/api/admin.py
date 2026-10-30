from fastapi import APIRouter
from pydantic import BaseModel, Field

from resilience.circuit_breaker import get_redis

router = APIRouter()


class ResetRequest(BaseModel):
    name: str = Field(description="Circuit breaker (provider) name to reset.", examples=["openai"])


@router.post("/admin/circuit-breaker/reset")
async def reset_circuit_breaker(body: ResetRequest):
    r = get_redis()
    keys = [f"circuit:{body.name}:{k}" for k in ("state", "failure_count", "opened_at", "half_open_calls")]
    await r.delete(*keys)
    return {"name": body.name, "state": "closed"}