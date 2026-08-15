"""TEMPORARY diagnostic (Mac, 2026-08-14) -- captures the real SportsDataIO
Free Trial response for exactly one endpoint, `/v3/nfl/scores/json/Teams`,
to independently verify the provider's own team-identifier field for all
32 current NFL teams before trusting it in `team_provider_ids`. Rebuilt
from the identical, already-proven 3C-ii pattern
(`git show 3ed116d^:apps/sports-intel-layer/app/diagnostics/sportsdataio_capture.py`)
-- same safeguards, scoped down to one category instead of six. **This
file and its route registration in main.py are removed in a follow-up
commit immediately after capture, regardless of outcome** -- it should
not exist on `dev` any longer than this verification window.

Safeguards (identical in kind to the 3C-ii original):
- Gated on RAILWAY_SERVICE_ID present (caller also gates on
  RAILWAY_ENVIRONMENT_NAME=="dev" in main.py) AND a valid
  X-Diagnostic-Token header, checked against SPORTSDATAIO_DIAGNOSTIC_TOKEN
  -- a fresh, temporary token minted only for this exercise, entirely
  separate from INTERNAL_SERVICE_TOKEN.
- SPORTSDATAIO_API_KEY is read from the environment and sent only via the
  Ocp-Apim-Subscription-Key header -- never a URL query parameter, never
  logged, never present in this endpoint's own error responses.
- Logging is metadata-only (endpoint path -- never contains the key --
  HTTP status, top-level type, item count, success/failure). The full
  captured response body is returned in the HTTP response for the caller
  to save as a file/artifact -- never written to a log line.
- A hard ceiling of exactly 1 total provider request for this process's
  lifetime -- checked before the call, not left to operator discipline.
  Once made (successfully or not), every later invocation in the same
  process is skipped and reported as such, never retried automatically.
"""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Header, HTTPException

router = APIRouter()

_logger = logging.getLogger("sports-intel-layer.diagnostics")

_BASE_URL = "https://api.sportsdata.io"
_PATH = "/v3/nfl/scores/json/Teams"
_MAX_TOTAL_REQUESTS = 1

# In-memory only, process-lifetime only -- see module docstring.
_state = {"total_requests": 0, "attempted": False}


@router.get("/diagnostics/sportsdataio-capture")
async def sportsdataio_capture(x_diagnostic_token: str | None = Header(default=None)):
    if not os.environ.get("RAILWAY_SERVICE_ID"):
        raise HTTPException(status_code=404)

    expected_token = os.environ.get("SPORTSDATAIO_DIAGNOSTIC_TOKEN")
    if not expected_token or x_diagnostic_token != expected_token:
        raise HTTPException(status_code=401, detail="invalid diagnostic token")

    if _state["attempted"]:
        return {
            "status": "skipped",
            "reason": "already attempted this process lifetime -- explicit redeploy required to retry",
            "total_requests_made": _state["total_requests"],
        }

    if _state["total_requests"] >= _MAX_TOTAL_REQUESTS:
        return {"status": "skipped", "reason": "budget ceiling reached", "total_requests_made": _state["total_requests"]}

    api_key = os.environ.get("SPORTSDATAIO_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="SPORTSDATAIO_API_KEY not configured")

    _state["attempted"] = True
    _state["total_requests"] += 1

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=15.0) as client:
        try:
            response = await client.get(_PATH, headers={"Ocp-Apim-Subscription-Key": api_key})
        except httpx.HTTPError as exc:
            _logger.warning("SPORTSDATAIO_CAPTURE: path=%s transport_error=%s", _PATH, type(exc).__name__)
            return {
                "status": "failed",
                "error_type": type(exc).__name__,
                "total_requests_made": _state["total_requests"],
            }

        if response.status_code != 200:
            _logger.warning(
                "SPORTSDATAIO_CAPTURE: path=%s http_status=%s FAILED", _PATH, response.status_code
            )
            return {
                "status": "failed",
                "http_status": response.status_code,
                "endpoint_attempted": _PATH,
                "total_requests_made": _state["total_requests"],
            }

        try:
            body = response.json()
        except ValueError:
            _logger.warning("SPORTSDATAIO_CAPTURE: path=%s FAILED non-JSON body", _PATH)
            return {
                "status": "failed",
                "http_status": 200,
                "reason": "non-JSON body",
                "endpoint_attempted": _PATH,
                "total_requests_made": _state["total_requests"],
            }

        top_level_type = "array" if isinstance(body, list) else "object"
        item_count = len(body) if isinstance(body, list) else 1
        _logger.warning(
            "SPORTSDATAIO_CAPTURE: path=%s SUCCESS type=%s items=%s", _PATH, top_level_type, item_count
        )

    return {
        "status": "success",
        "http_status": 200,
        "endpoint_attempted": _PATH,
        "top_level_type": top_level_type,
        "item_count": item_count,
        "total_requests_made": _state["total_requests"],
        "raw_response": body,
    }
