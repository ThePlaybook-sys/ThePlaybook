"""Internal service-to-service auth guard (DEMO-4, Decision 2).

Identical to `apps/ai-orchestrator/app/internal_auth.py` -- the already-
established, already-provisioned project convention (Milestone 3, Phase 2:
one `INTERNAL_SERVICE_TOKEN` per environment, shared across the internal
mesh -- `api-gateway`, `ai-orchestrator`, `sports-intel-layer`,
`worker-scheduled`, `worker-market-monitor` -- generated independently per
environment via `secrets.token_hex(32)`, never reused across environments,
never set on `frontend`; see `docs/ops/secrets-management.md`). Confirmed
by direct inspection before reuse, not assumed: `sports-intel-layer` had
zero prior usage of `INTERNAL_SERVICE_TOKEN` in its own app code (the
Railway variable was provisioned in Milestone 3 but nothing here validated
it against an actual endpoint until now) -- this is the first internal
route sports-intel-layer itself has ever guarded with it, not a new
credential or a redesign of the existing one.

Not Demo-specific: this guard is a general internal-service seam. DEMO-4
is its first real caller inside this service.
"""
import hmac
import os

from fastapi import Header, HTTPException


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    """Guards internal-only endpoints -- never accepts a user JWT, only
    this environment's own internal service token. Constant-time
    comparison avoids leaking token length/prefix via response-time side
    channels. Never logs the header value in either the success or
    failure path.
    """
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN")
    if not expected:
        raise HTTPException(status_code=500, detail="Internal service token not configured")
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="Invalid internal service token")
