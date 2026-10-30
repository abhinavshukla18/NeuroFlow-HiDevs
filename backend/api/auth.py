from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from security.auth import EXPIRES, authenticate, create_token

router = APIRouter()


class TokenRequest(BaseModel):
    client_id: str = Field(max_length=100, description="Client identifier.", examples=["admin-client"])
    client_secret: str = Field(max_length=200, description="Client secret.", examples=["your-client-secret"])


@router.post("/auth/token")
async def token(body: TokenRequest):
    scopes = authenticate(body.client_id, body.client_secret)
    if scopes is None:
        raise HTTPException(401, "Invalid client credentials")
    return {"access_token": create_token(body.client_id, scopes), "token_type": "bearer", "expires_in": EXPIRES}