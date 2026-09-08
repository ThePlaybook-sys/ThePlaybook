"""MANSA Phase 8.3C -- Player Stats Diagnostic Retry (2026-09-08,
HQ-authorized).

TEMPORARY, DIAGNOSTIC-ONLY module. Retries Phase 8.3B's single-call
diagnostic (`docs/ops/phase-8.3b-player-stats-single-call-diagnostic-
2026-09-08.md`), which reached MySportsFeeds' real `player_stats_totals`
endpoint but got no HTTP response within a 30.0s client timeout. Two
changes only, both directly responsive to that pass's own real failure,
per HQ's explicit "keep the same target unless code inspection reveals
it was invalid" instruction -- nothing else about scope changed:

1. **Timeout raised 30.0s -> 120.0s** (`build_msf_player_stats_
   diagnostic_client`) -- matches the same fix Phase 8.2's Players
   Identity Diagnostic #1 -> #2 already proved necessary for a different
   MySportsFeeds v2.1 feed after an identical 30.0s timeout failure.
2. **The live call is now exception-safe.** Phase 8.3B's own uncaught
   `httpx.ReadTimeout` crashed the whole FastAPI startup lifespan,
   failed three healthchecks, and forced an unplanned Railway auto-
   redeploy -- a real defect that pass's own report disclosed and this
   pass fixes. `run_msf_player_stats_diagnostic()` below catches every
   `httpx.HTTPError` (which `TimeoutException` subclasses) around the one
   live request and returns a structured, honest `{"http_status": None,
   "error": ...}` result instead of letting the exception propagate --
   a diagnostic failure must never take the service down. The
   `activation_run_markers` claim step is wrapped the same way, as
   defense in depth: nothing in this module's startup-hook path may ever
   raise uncaught.

**Exactly ONE live request, guarded by the same `activation_run_markers`
mechanism Phase 8.3A/8.3B both used** -- reused verbatim again, a NEW
dedicated `run_key` for this pass, the Phase 8.3B marker row untouched.
No retries, no fanout, no pagination follow-up, no second call to
confirm the result -- and if this call also times out, this module's own
job ends there; HQ's directive requires stopping, not scoping-hunting
inside this same pass.

## Request design (unchanged from Phase 8.3B, reasoning carried forward)

- **Feed key / endpoint**: `seasonal_player_stats` -> `player_stats_
  totals.json`, confirmed from the vendored `mysportsfeeds-node` SDK's
  own feed table (`API_v2_0.js`).
- **Base URL / auth**: `https://api.mysportsfeeds.com/v2.1/pull`, HTTP
  Basic (`username=api_key`, `password="MYSPORTSFEEDS"` literal).
- **`team=NE` filter**: sourced from the SDK's own bundled README
  documented usage example for the ancestor v1.x feed in the same
  player-stats-totals family -- disclosed in Phase 8.3B's own report as
  inferred by family analogy, not a v2.x-confirmed example. Nothing
  about Phase 8.3B's actual failure (a timeout, not a 4xx/rejection)
  gives any signal that this filter itself was invalid, so it is kept
  unchanged per HQ's own instruction.
- **Season**: `2025-2026-regular` (the completed prior season) -- chosen
  in Phase 8.3A/8.3B because the current season is genuinely all-zero
  (not started).
- **Target**: `NE` -- deepest existing real cross-check evidence of the
  three already-identity-resolved candidates (17 real players/roster
  rows, 17 real named lineup slots spanning QB/RB/WR/TE/OL/DL/LB/DB/K).
"""
from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.master_refresh.production_clients import build_msf_player_stats_diagnostic_client

_MSF_PASSWORD = "MYSPORTSFEEDS"  # CONFIRMED literal, not a real password -- SDK's own authenticate() example
_PLAYER_STATS_TOTALS_PATH = "/nfl/2025-2026-regular/player_stats_totals.json"
_TARGET_TEAM = "NE"
_TIMEOUT_SECONDS = 120.0

#: This diagnostic's own dedicated run_key -- distinct from Phase 8.3A's
#: (`phase-8.3a-team-season-stats-activation-2026-09-08`) and Phase
#: 8.3B's (`phase-8.3b-player-stats-diagnostic-2026-09-08`), reusing the
#: same `activation_run_markers` table/mechanism verbatim. Neither prior
#: marker row is touched by this pass.
_RUN_KEY = "phase-8.3c-player-stats-diagnostic-retry-2026-09-08"


class PlayerStatsDiagnosticSkipped(Exception):
    """Raised (and caught by the caller) when this pass's run_key is
    already claimed in activation_run_markers -- an overlapping/duplicate
    container boot, not an error. Per HQ's explicit instruction: if the
    guard indicates the run already executed, make zero provider calls,
    across overlapping deployments, container restarts, healthcheck
    restarts, or Railway redeploys alike."""


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
    live by this project."""
    interesting_substrings = ("rate", "limit", "quota", "remaining", "requests", "retry")
    return {
        key: value
        for key, value in headers.items()
        if any(substring in key.lower() for substring in interesting_substrings)
    }


async def run_msf_player_stats_diagnostic() -> dict[str, Any]:
    """Claims this pass's run_key, then makes exactly ONE real
    `player_stats_totals` request (team=NE, season=2025-2026-regular,
    120.0s timeout) if the guard is acquired. Returns a structured
    evidence envelope in every case -- success, timeout, transport
    error, or skip -- and never raises. A diagnostic failure must not
    take down the service (HQ's explicit instruction this pass): every
    step that performs network I/O is wrapped so an unexpected failure
    becomes a logged, honest result rather than an uncaught exception
    propagating into the FastAPI startup lifespan (the exact defect
    Phase 8.3B's own report disclosed and this pass fixes)."""
    try:
        await _claim_run_marker()
    except PlayerStatsDiagnosticSkipped as exc:
        return {"skipped": True, "reason": str(exc), "provider_call_made": False}
    except Exception as exc:  # defense in depth -- a marker-claim failure must not crash startup either
        return {
            "skipped": True,
            "reason": f"failed to claim activation_run_markers row: {exc}",
            "provider_call_made": False,
            "marker_claim_error": True,
        }

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

    async with client:
        start = time.monotonic()
        try:
            response = await client.get(
                _PLAYER_STATS_TOTALS_PATH,
                params=request_params,
                headers=_msf_auth_header(api_key),
            )
        except httpx.TimeoutException as exc:
            return {
                "skipped": False,
                "provider_call_made": True,
                "run_key": _RUN_KEY,
                "request_timestamp_utc": request_timestamp,
                "request_path": _PLAYER_STATS_TOTALS_PATH,
                "request_params": request_params,
                "provider_name": "mysportsfeeds",
                "http_status": None,
                "error": "timeout",
                "error_detail": str(exc),
                "timeout_seconds": _TIMEOUT_SECONDS,
                "elapsed_seconds": round(time.monotonic() - start, 3),
            }
        except httpx.HTTPError as exc:
            return {
                "skipped": False,
                "provider_call_made": True,
                "run_key": _RUN_KEY,
                "request_timestamp_utc": request_timestamp,
                "request_path": _PLAYER_STATS_TOTALS_PATH,
                "request_params": request_params,
                "provider_name": "mysportsfeeds",
                "http_status": None,
                "error": "transport_error",
                "error_detail": str(exc),
                "elapsed_seconds": round(time.monotonic() - start, 3),
            }

        elapsed_seconds = round(time.monotonic() - start, 3)
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
            "elapsed_seconds": elapsed_seconds,
            "response_size_bytes": len(response.content),
            "quota_relevant_headers": _quota_relevant_headers(response.headers),
            "response_body": body,
        }
