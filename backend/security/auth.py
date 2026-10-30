import hmac
import os
import time

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

ALGORITHM = "HS256"
EXPIRES = 3600
bearer = HTTPBearer(auto_error=False)

SCOPES = {"ADMIN": ["query", "ingest", "admin"], "QUERY": ["query"]}


def _secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise HTTPException(500, "JWT_SECRET is not configured")
    return secret


def authenticate(client_id: str, client_secret: str) -> list[str] | None:
    for prefix, scopes in SCOPES.items():
        cid = os.getenv(f"{prefix}_CLIENT_ID")
        sec = os.getenv(f"{prefix}_CLIENT_SECRET")
        if cid and sec and hmac.compare_digest(client_id, cid) and hmac.compare_digest(client_secret, sec):
            return scopes
    return None


def create_token(client_id: str, scopes: list[str]) -> str:
    payload = {"sub": client_id, "scopes": scopes, "exp": int(time.time()) + EXPIRES}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    token = creds.credentials if creds else request.query_params.get("token")
    if not token:
        raise HTTPException(401, "Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return {"client_id": payload["sub"], "scopes": payload.get("scopes", [])}


def require_scope(scope: str):
    async def dependency(user: dict = Depends(get_current_user)) -> dict:
        if scope not in user["scopes"]:
            raise HTTPException(403, f"Scope '{scope}' required")
        return user

    return dependency