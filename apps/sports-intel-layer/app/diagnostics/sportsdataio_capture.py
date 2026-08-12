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
  enforced here, not left to operator discipline -- checked before every
  single provider call, not just at the top of a batch. Once reached, all
  further provider calls in the same or a later invocation (within this
  process) are skipped and reported as such, not attempted.
- One request per category per invocation; no automatic retry of any
  kind, including on 401/403/429/malformed-body responses. A second,
  narrower invocation (via the `categories` query param) targeting only
  the specific categories that failed is how a corrected endpoint path
  gets re-tried -- a deliberate, human-in-the-loop second call, not a
  loop in this code.
- Per-category attempt tracking (Mac, 2026-08-12 correction): a
  module-level, in-memory set records which categories have already been
  attempted (successfully or not) this process lifetime. A category in
  that set is skipped on any later invocation, reported as such, rather
  than silently re-called -- the same category cannot be accidentally
  re-attempted without an explicit code/process change. This replaced an
  earlier blanket one-shot guard that refused *any* second invocation
  regardless of category, which made a deliberate staged sequence
  (call one category, inspect, decide, call the next) impossible without
  a full redeploy between every single call -- a real gap against this
  diagnostic's own stated intent, not a hypothetical one. Still resets on
  a container restart, an explicit, known limitation of in-memory state,
  not a durable lock -- acceptable here for the same reason as before:
  same-session, immediately-deleted diagnostic.
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

#: Current-season scoping for categories that aren't week-scoped stats.
#: Schedules stays on the real upcoming season -- CONFIRMED from the first
#: capture pass that 2026REG Week 1 kicks off 2026-09-09, so this was never
#: wrong for Schedules and is left untouched.
_SEASON = "2026REG"
_TEAM = "KC"

#: Historical season/week correction (Mac, 2026-08-12): the original
#: 2026REG Week 1 scoping 404'd for injuries/team_stats/player_stats
#: because that week hasn't been played yet -- confirmed from the first
#: pass's own Schedules capture, not guessed. These three week-scoped
#: categories are corrected to the most recently completed regular season
#: instead, per Mac's explicit second-pass plan. Deliberately NOT another
#: guess at the current season.
_HISTORICAL_SEASON = "2025REG"
_HISTORICAL_WEEK = 1

_CATEGORIES: dict[str, str] = {
    "injuries": f"/v3/nfl/scores/json/InjuriesByWeek/{_HISTORICAL_SEASON}/{_HISTORICAL_WEEK}",
    "rosters": f"/v3/nfl/scores/json/Players/{_TEAM}",
    "schedules": f"/v3/nfl/scores/json/Schedules/{_SEASON}",
    "team_stats": f"/v3/nfl/scores/json/TeamGameStatsByWeek/{_HISTORICAL_SEASON}/{_HISTORICAL_WEEK}",
    "player_stats": f"/v3/nfl/scores/json/PlayerGameStatsByWeek/{_HISTORICAL_SEASON}/{_HISTORICAL_WEEK}",
    "depth_charts": "/v3/nfl/scores/json/DepthCharts",
}

# In-memory only, process-lifetime only -- see module docstring.
_state = {"total_requests": 0, "attempted_categories": set()}


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

    api_key = os.environ.get("SPORTSDATAIO_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="SPORTSDATAIO_API_KEY not configured")

    wanted = set(categories.split(",")) if categories else set(_CATEGORIES)
    results: dict[str, dict] = {}

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=15.0) as client:
        for name, path in _CATEGORIES.items():
            if name not in wanted:
                continue

            if name in _state["attempted_categories"]:
                results[name] = {
                    "status": "skipped",
                    "reason": "category already attempted this process lifetime -- explicit retry required",
                }
                _logger.warning("SPORTSDATAIO_CAPTURE: %s skipped, already attempted", name)
                continue

            if _state["total_requests"] >= _MAX_TOTAL_REQUESTS:
                results[name] = {"status": "skipped", "reason": "budget ceiling reached"}
                _logger.warning("SPORTSDATAIO_CAPTURE: %s skipped, budget ceiling reached", name)
                continue

            _state["total_requests"] += 1
            _state["attempted_categories"].add(name)
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
