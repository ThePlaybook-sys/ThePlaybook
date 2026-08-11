"""TEMPORARY diagnostic (Mac, 2026-08-11/12) -- captures real SportsDataIO
Free Trial responses for six NFL categories, to validate our ASSUMED
fixture shapes against reality before any 3C-ii implementation. See
PROGRESS.md for the full approved plan this implements and why each
safeguard below exists. **This file and its route registration in
main.py are removed in a follow-up commit immediately after capture,
regardless of outcome** -- it should not exist on `dev` any longer than
the validation window.

Safeguards, per Mac's explicit corrections to the original plan:
- Gated on RAILWAY_ENVIRONMENT_NAME=="dev" (caller, see main.py) AND
  RAILWAY_SERVICE_ID present AND a valid X-Diagnostic-Token header,
  checked against SPORTSDATAIO_DIAGNOSTIC_TOKEN -- a fresh, temporary
  token minted only for this exercise, entirely separate from
  INTERNAL_SERVICE_TOKEN (that boundary is not reused or weakened here).
- SPORTSDATAIO_API_KEY is read from the environment and sent only via the
  Ocp-Apim-Subscription-Key header -- never a URL query parameter, never
  logged, never present in this endpoint's own error responses.
- Logging is metadata-only (category, endpoint path -- which never
  contains the key or any query secret, HTTP status, top-level type, item
  count, success/failure). The full captured response body is returned in
  the HTTP response for the caller to save as a file/artifact -- it is
  never written to a log line.
- A hard ceiling of 12 total provider requests for the process lifetime,
  enforced here, not left to operator discipline -- once reached, further
  categories in the same or a later invocation (within this process) are
  skipped and reported as such, not attempted.
- One request per category per invocation; no automatic retry of any
  kind, including on 401/403/429/malformed-body responses. A second,
  narrower invocation (via the `categories` query param) targeting only
  the specific categories that failed is how a corrected endpoint path
  gets re-tried -- a deliberate, human-in-the-loop second call, not a
  loop in this code.
- One-shot guard: a module-level, in-memory flag refuses any invocation
  after the first, for the lifetime of this process. This resets on a
  container restart -- an explicit, known limitation of an in-memory
  guard, not a durable lock. Acceptable here specifically because this is
  a same-session, immediately-deleted diagnostic and no redeploy/restart
  is planned between the approved capture run and its removal.
"""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Header, HTTPException

router = APIRouter()

_logger = logging.getLogger("sports-intel-layer.diagnostics")

_BASE_URL = "https://api.sportsdata.io"
_MAX_TOTAL_REQUESTS = 12

#: ASSUMED season/week/team scoping -- kept small deliberately to keep
#: each captured response small and the call budget cheap. Corrected on
#: a real 404 via a second, narrower invocation, not guessed twice here.
_SEASON = "2026REG"
_WEEK = 1
_TEAM = "KC"

_CATEGORIES: dict[str, str] = {
    "injuries": f"/v3/nfl/scores/json/InjuriesByWeek/{_SEASON}/{_WEEK}",
    "rosters": f"/v3/nfl/scores/json/Players/{_TEAM}",
    "schedules": f"/v3/nfl/scores/json/Schedules/{_SEASON}",
    "team_stats": f"/v3/nfl/scores/json/TeamGameStatsByWeek/{_SEASON}/{_WEEK}",
    "player_stats": f"/v3/nfl/scores/json/PlayerGameStatsByWeek/{_SEASON}/{_WEEK}",
    "depth_charts": "/v3/nfl/scores/json/DepthCharts",
}

# In-memory only, process-lifetime only -- see module docstring.
_state = {"already_run": False, "total_requests": 0}


@router.get("/diagnostics/sportsdataio-capture")
async def sportsdataio_capture(
    x_diagnostic_token: str | None = Header(default=None),
    categories: str | None = None,
):
    if not os.environ.get("RAILWAY_SERVICE_ID"):
        raise HTTPException(status_code=404)

    expected_token = os.environ.get("SPORTSDATAIO_DIAGNOSTIC_TOKEN")
    if not expected_token or x_diagnostic_token != expected_token:
        raise HTTPException(status_code=401, detail="invalid diagnostic token")

    if _state["already_run"]:
        raise HTTPException(
            status_code=423,
            detail="capture already attempted this process lifetime -- one-shot guard engaged",
        )
    _state["already_run"] = True

    api_key = os.environ.get("SPORTSDATAIO_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="SPORTSDATAIO_API_KEY not configured")

    wanted = set(categories.split(",")) if categories else set(_CATEGORIES)
    results: dict[str, dict] = {}

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=15.0) as client:
        for name, path in _CATEGORIES.items():
            if name not in wanted:
                continue

            if _state["total_requests"] >= _MAX_TOTAL_REQUESTS:
                results[name] = {"status": "skipped", "reason": "budget ceiling reached"}
                _logger.warning("SPORTSDATAIO_CAPTURE: %s skipped, budget ceiling reached", name)
                continue

            _state["total_requests"] += 1
            try:
                response = await client.get(path, headers={"Ocp-Apim-Subscription-Key": api_key})
            except httpx.HTTPError as exc:
                results[name] = {"status": "failed", "error_type": type(exc).__name__}
                _logger.warning(
                    "SPORTSDATAIO_CAPTURE: category=%s path=%s transport_error=%s",
                    name, path, type(exc).__name__,
                )
                continue

            if response.status_code != 200:
                results[name] = {
                    "status": "failed",
                    "http_status": response.status_code,
                    "endpoint_attempted": path,
                }
                _logger.warning(
                    "SPORTSDATAIO_CAPTURE: category=%s path=%s http_status=%s FAILED",
                    name, path, response.status_code,
                )
                continue

            try:
                body = response.json()
            except ValueError:
                results[name] = {
                    "status": "failed",
                    "http_status": 200,
                    "reason": "non-JSON body",
                    "endpoint_attempted": path,
                }
                _logger.warning(
                    "SPORTSDATAIO_CAPTURE: category=%s path=%s FAILED non-JSON body", name, path
                )
                continue

            top_level_type = "array" if isinstance(body, list) else "object"
            item_count = len(body) if isinstance(body, list) else 1
            results[name] = {
                "status": "success",
                "http_status": 200,
                "endpoint_attempted": path,
                "top_level_type": top_level_type,
                "item_count": item_count,
                "raw_response": body,
            }
            _logger.warning(
                "SPORTSDATAIO_CAPTURE: category=%s path=%s SUCCESS type=%s items=%s",
                name, path, top_level_type, item_count,
            )

    return {
        "total_requests_made": _state["total_requests"],
        "budget_ceiling": _MAX_TOTAL_REQUESTS,
        "results": results,
    }
