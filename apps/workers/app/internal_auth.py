import hmac
import os

from fastapi import Header, HTTPException


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    """Guards internal-only endpoints (Orchestrator/Workers, Volume 2 §6/§10) —
    never accepts a user JWT, only this environment's own internal service
    token. Constant-time comparison avoids leaking token length/prefix via
    response-time side channels.
    """
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN")
    if not expected:
        raise HTTPException(status_code=500, detail="Internal service token not configured")
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="Invalid internal service token")
