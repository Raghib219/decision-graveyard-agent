"""
Lightweight API-key auth for the Decision Graveyard Agent.

Usage:
  - Set API_KEY=<your-secret> in .env (or leave unset to disable auth)
  - Protected endpoints receive:  Authorization: Bearer <key>
  - The UI and /status are always public

If API_KEY is not set, auth is disabled (all requests pass through).
This keeps the hackathon demo easy to run while providing real
protection when deployed publicly.
"""

import os
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_API_KEY     = os.getenv("API_KEY", "")   # empty = auth disabled
_AUTH_SCHEME = HTTPBearer(auto_error=False)


def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(_AUTH_SCHEME),
) -> None:
    """
    FastAPI dependency — call as:  Depends(verify_api_key)

    - If API_KEY is not set in .env: always passes (auth disabled)
    - If API_KEY is set: validates the Bearer token
    """
    if not _API_KEY:
        return   # auth not configured — open access

    if credentials is None or credentials.credentials != _API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. "
                   "Pass: Authorization: Bearer <your-API_KEY>",
            headers={"WWW-Authenticate": "Bearer"},
        )


def auth_status() -> dict:
    return {"auth_enabled": bool(_API_KEY)}
