"""MANSA Phase 8.3B -- Player Season-Stats Single-Call Diagnostic
(2026-09-08, HQ-authorized).

TEMPORARY, DIAGNOSTIC-ONLY module. Answers one question with the minimum
possible external activity: does MySportsFeeds' real `player_stats_totals`
endpoint return legitimate, usable player-level performance data? This is
evidence-gathering, not activation -- **no player performance data is
persisted by this module.** The raw response is only logged (Railway
deploy log), matching this project's own "capture first, classify by
hand, decide what to build next" discipline from every prior MSF
diagnostic pass.

**Exactly ONE live request, guarded by Phase 8.3A's own
`activation_run_markers`** (reused verbatim, new `run_key` -- HQ's
explicit "do not create a second idempotency framework" instruction). No
retries, no fanout across NE/SEA/BUF, no pagination follow-up, no second
call to confirm the result.

## Request design provenance

- **Feed key / endpoint**: `seasonal_player_stats` -> `player_stats_
  totals.json`, confirmed directly from the vendored `mysportsfeeds-node`
  SDK's own feed table (`API_v2_0.js`): `{season: true, endpoint:
  'player_stats_totals'}` -- no `path` entry, meaning no game/week/date
  segment is required, identical shape to `seasonal_team_stats` (already
  confirmed real and working in Phase 8.3A).
- **Base URL / auth**: `https://api.mysportsfeeds.com/v2.1/pull`, HTTP
  Basic (`username=api_key`, `password="MYSPORTSFEEDS"` literal) --
  identical provenance and value to every prior real MySportsFeeds call
  this project has made (Phase 8.2 roster adapter, Phase 8.3A team
  season-stats).
- **`team` filter param**: sourced from the SDK's own bundled `README.md`
  documented usage example for the ancestor v1.x feed in the same
  player-stats-totals family (`cumulative_player_stats`): `msf.getData(
  'nfl', '2015-2016-regular', 'cumulative_player_stats', 'json', {team:
  'dallas-cowboys'})`. This is real SDK-provided documentation, not an
  invented parameter -- but it is disclosed here exactly as strong, not
  certain: the v1.x example uses a full team-name slug, and this
  project's own `team_gamelogs` attempt with a `team` filter on a
  DIFFERENT v2.1 endpoint still returned 400 (Phase 8.3 audit,
  unresolved, explicitly not retried this pass). The value used below is
  the MySportsFeeds team abbreviation (`"NE"`), matching every one of
  this project's own confirmed-real v2.1 captures
  (`team_stats_totals`/`standings` both key teams by `.abbreviation`),
  not the v1.x slug format -- the best evidence-based choice available
  without inventing anything new. **Whether this filter is honored,
  ignored, or rejected by the real v2.1 endpoint is exactly the open
  question this one call answers -- not assumed either way.**
- **Season**: `2025-2026-regular` (the completed prior season), not the
  current `2026-2027-regular` season -- chosen because Phase 8.3A's own
  team-level activation showed the current season is genuinely all-zero
  (season hasn't started, first game 2026-09-10). Using the prior,
  completed season maximizes the chance this one authorized call returns
  non-zero player data, per HQ's "prefer a request capable of
  determining whether meaningful fields exist without a second call"
  instruction.
- **Target**: `NE` -- of the three already-identity-resolved candidates
  (NE, SEA, BUF), NE has the deepest existing real evidence to cross-
  check against (17 real `players`/`roster_memberships` rows and 17 real
  named `lineup` slots spanning QB/RB/WR/TE/OL/DL/LB/DB/K from Phase 8.2,
  maximizing role-coverage cross-check potential in this one call).
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from app.master_refresh.production_clients import build_msf_player_stats_diagnostic_client

_MSF_PASSWORD = "MYSPORTSFEEDS"  # CONFIRMED literal, not a real password -- SDK's own authenticate() example
_PLAYER_STATS_TOTALS_PATH = "/nfl/2025-2026-regular/player_stats_totals.json"
_TARGET_TEAM = "NE"

#: This diagnostic's own dedicated run_key -- distinct from Phase 8.3A's
#: `phase-8.3a-team-season-stats-activation-2026-09-08`, reusing the same
#: `activation_run_markers` table/mechanism (HQ's explicit "do not create
#: a second idempotency framework" instruction), not a second guard.
_RUN_KEY = "phase-8.3b-player-stats-diagnostic-2026-09-08"


class PlayerStatsDiagnosticSkipped(Exception):
    """Raised (and caught by the caller) when this pass's run_key is
    already claimed in activation_run_markers -- an overlapping/duplicate
    container boot, not an error. Per HQ's explicit instruction: if the
    guard indicates the run already executed, make zero provider calls."""


def _msf_auth_header(api_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{api_key}:{_MSF_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


async def _claim_run_marker() -> None:
    supabase_url = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        response = await client.post(
            "/rest/v1/activation_run_markers",
            json={"run_key": _RUN_KEY},
            headers=headers,
        )
    if response.status_code == 409:
        raise PlayerStatsDiagnosticSkipped(
            f"run_key {_RUN_KEY!r} already claimed -- skipping duplicate diagnostic call"
        )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"failed to claim activation_run_markers row for {_RUN_KEY!r}: "
            f"{response.status_code} {response.text}"
        )


def _quota_relevant_headers(headers: httpx.Headers) -> dict[str, str]:
    """Extracts any response header whose name suggests rate-limit/quota
    relevance -- defensive, case-insensitive substring match, since
    MySportsFeeds' own header names for this have never been observed
    live by this project (Phase 7's own odds_api_credit_ledger docstring
    already flags that trusting an unverified vendor header name is
    fragile; this function only records what's actually present, makes
    no assumption about which headers to expect)."""
    interesting_substrings = ("rate", "limit", "quota", "remaining", "requests", "retry")
    return {
        key: value
        for key, value in headers.items()
        if any(substring in key.lower() for substring in interesting_substrings)
    }


async def run_msf_player_stats_diagnostic() -> dict[str, Any]:
    """Claims this pass's run_key, then makes exactly ONE real
    `player_stats_totals` request (team=NE, season=2025-2026-regular) if
    the guard is acquired. Returns the full raw evidence envelope
    (request params, HTTP status, response headers, response body,
    timestamp) for logging -- never persists anything to `team_stats`/
    `player_stats`. Returns `{"skipped": True, "reason": ...}` if the
    run_key was already claimed by another container -- zero provider
    calls in that case."""
    try:
        await _claim_run_marker()
    except PlayerStatsDiagnosticSkipped as exc:
        return {"skipped": True, "reason": str(exc), "provider_call_made": False}

    client_and_key = build_msf_player_stats_diagnostic_client()
    if client_and_key is None:
        return {
            "skipped": True,
            "reason": "MYSPORTSFEEDS_API_KEY is not configured",
            "provider_call_made": False,
        }

    client, api_key = client_and_key
    request_params = {"team": _TARGET_TEAM}
    request_timestamp = datetime.now(timezone.utc).isoformat()

    try:
        response = await client.get(
            _PLAYER_STATS_TOTALS_PATH,
            params=request_params,
            headers=_msf_auth_header(api_key),
        )
    finally:
        await client.aclose()

    body: Any
    try:
        body = response.json()
    except ValueError:
        body = response.text

    return {
        "skipped": False,
        "provider_call_made": True,
        "run_key": _RUN_KEY,
        "request_timestamp_utc": request_timestamp,
        "request_path": _PLAYER_STATS_TOTALS_PATH,
        "request_params": request_params,
        "provider_name": "mysportsfeeds",
        "http_status": response.status_code,
        "quota_relevant_headers": _quota_relevant_headers(response.headers),
        "response_body": body,
    }
