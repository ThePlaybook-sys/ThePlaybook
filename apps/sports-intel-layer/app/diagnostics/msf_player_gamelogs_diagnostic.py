"""MANSA Phase 8.4B -- Player Gamelogs Live Diagnostic (2026-09-08,
HQ-authorized).

TEMPORARY, DIAGNOSTIC-ONLY module. Makes exactly ONE real MySportsFeeds
request to determine the real `player_gamelogs` response shape (Phase
8.4's own audit-only design pass could not observe this -- no live call
was authorized there). **No player stats are persisted by this module.**

## Request design (per Phase 8.4's own audit)

- **Feed key / endpoint**: `seasonal_player_gamelogs` -> `player_
  gamelogs.json`, confirmed from the vendored `mysportsfeeds-node` SDK's
  own feed table (`API_v2_0.js`): `{season: true, endpoint:
  'player_gamelogs'}` -- no mandatory path segment.
- **Base URL / auth**: `https://api.mysportsfeeds.com/v2.1/pull`, HTTP
  Basic (`username=api_key`, `password="MYSPORTSFEEDS"` literal) --
  identical provenance to every real MySportsFeeds call this project has
  made.
- **`player=9999` filter**: the SDK README's own documented v2.0 usage
  example is for this EXACT feed key (`seasonal_player_gamelogs`,
  `{player: 'stephen-curry'}`) -- stronger provenance than Phase 8.3C's
  own `team` filter (which was only an ancestor-family analogy). `9999`
  is Hunter Henry's real MySportsFeeds numeric player id, cross-verified
  identical across three separate real feeds in this project's own
  history (`players.json`, `lineup.json`, `player_stats_totals.json`) --
  the single most-verified real identity available. The exact value
  FORMAT this feed expects (numeric id vs. a name-slug, per the NBA
  example) is the one open question this call answers -- the numeric id
  is used first because it's this project's own established real
  MySportsFeeds identifier convention, not the documented NBA slug.
- **Season**: `2025-2026-regular` -- the same completed prior season
  Phase 8.3C already used successfully, per HQ's explicit instruction.
- **No additional/invented parameters** -- exactly `{player: "9999"}`,
  nothing else.

## Execution safety

Reuses `activation_run_markers` verbatim (Phase 8.3A/B/C's own proven
mechanism, twice actually raced across overlapping Railway deployments
in production and held both times) with a new, dedicated run_key. The
marker -- not the `RUN_MSF_PLAYER_GAMELOGS_DIAGNOSTIC` env var -- is the
authoritative once-only guard; the env var only decides whether this
hook runs at all. 120.0s timeout (`build_msf_player_gamelogs_diagnostic_
client`), proactively applied this time rather than rediscovered after
a 30s failure. Every network call in this module (the marker claim and
the live MSF request) is wrapped so a timeout or provider error returns
a structured result rather than raising -- the exact defect Phase 8.3B
disclosed and Phase 8.3C fixed, applied here from the start.

## Raw capture policy (Phase 8.4's own recommendation, applied)

The full response is logged in fixed-size chunks well under Railway's
observed 80KB (81,920-character) single-log-line truncation limit, each
chunk tagged with an explicit sequence marker
(`MSF_PLAYER_GAMELOGS_RAW_CHUNK i/N`) for exact reassembly from the
deploy log -- fixes Phase 8.3C's own disclosed truncation with zero new
infrastructure. Only the response body is chunked/logged; request
headers (which carry the Basic-auth credential) are never logged, in
whole or in part, anywhere in this module.
"""
from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.master_refresh.production_clients import build_msf_player_gamelogs_diagnostic_client

_MSF_PASSWORD = "MYSPORTSFEEDS"  # CONFIRMED literal, not a real password -- SDK's own authenticate() example
_PLAYER_GAMELOGS_PATH = "/nfl/2025-2026-regular/player_gamelogs.json"
_TARGET_PLAYER = "9999"  # Hunter Henry -- the most cross-verified real identity in this project
_TIMEOUT_SECONDS = 120.0

#: This diagnostic's own dedicated run_key -- distinct from every prior
#: Phase 8.3 marker, reusing the same activation_run_markers table
#: verbatim. No other marker row is touched by this pass.
_RUN_KEY = "phase-8.4b-player-gamelogs-diagnostic-2026-09-08"

#: Comfortably under Railway's observed 80KB (81,920-char) single-log-
#: line truncation limit, leaving headroom for the log-line prefix and
#: sequence marker text itself.
_LOG_CHUNK_SIZE = 60000


class PlayerGamelogsDiagnosticSkipped(Exception):
    """Raised (and caught by the caller) when this pass's run_key is
    already claimed in activation_run_markers -- an overlapping/duplicate
    container boot, not an error."""


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
        raise PlayerGamelogsDiagnosticSkipped(
            f"run_key {_RUN_KEY!r} already claimed -- skipping duplicate diagnostic call"
        )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"failed to claim activation_run_markers row for {_RUN_KEY!r}: "
            f"{response.status_code} {response.text}"
        )


def _quota_relevant_headers(headers: httpx.Headers) -> dict[str, str]:
    interesting_substrings = ("rate", "limit", "quota", "remaining", "requests", "retry")
    return {
        key: value
        for key, value in headers.items()
        if any(substring in key.lower() for substring in interesting_substrings)
    }


def chunk_for_logging(text: str, *, chunk_size: int = _LOG_CHUNK_SIZE) -> list[str]:
    """Splits `text` into `chunk_size`-character pieces for safe,
    truncation-proof logging -- pure function, no I/O, unit-testable
    without a live call."""
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


async def run_msf_player_gamelogs_diagnostic() -> dict[str, Any]:
    """Claims this pass's run_key, then makes exactly ONE real
    `player_gamelogs` request (player=9999, season=2025-2026-regular,
    120.0s timeout) if the guard is acquired. Returns a structured
    evidence envelope in every case -- success, timeout, transport
    error, or skip -- and never raises. Never logs anything itself; the
    caller (the `main.py` startup hook) owns chunked logging of the
    returned envelope's `response_body_json` field via
    `chunk_for_logging`."""
    try:
        await _claim_run_marker()
    except PlayerGamelogsDiagnosticSkipped as exc:
        return {"skipped": True, "reason": str(exc), "provider_call_made": False}
    except Exception as exc:  # defense in depth -- a marker-claim failure must not crash startup either
        return {
            "skipped": True,
            "reason": f"failed to claim activation_run_markers row: {exc}",
            "provider_call_made": False,
            "marker_claim_error": True,
        }

    client_and_key = build_msf_player_gamelogs_diagnostic_client()
    if client_and_key is None:
        return {
            "skipped": True,
            "reason": "MYSPORTSFEEDS_API_KEY is not configured",
            "provider_call_made": False,
        }

    client, api_key = client_and_key
    request_params = {"player": _TARGET_PLAYER}
    request_timestamp = datetime.now(timezone.utc).isoformat()

    async with client:
        start = time.monotonic()
        try:
            response = await client.get(
                _PLAYER_GAMELOGS_PATH,
                params=request_params,
                headers=_msf_auth_header(api_key),
            )
        except httpx.TimeoutException as exc:
            return {
                "skipped": False,
                "provider_call_made": True,
                "run_key": _RUN_KEY,
                "request_timestamp_utc": request_timestamp,
                "request_path": _PLAYER_GAMELOGS_PATH,
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
                "request_path": _PLAYER_GAMELOGS_PATH,
                "request_params": request_params,
                "provider_name": "mysportsfeeds",
                "http_status": None,
                "error": "transport_error",
                "error_detail": str(exc),
                "elapsed_seconds": round(time.monotonic() - start, 3),
            }

        elapsed_seconds = round(time.monotonic() - start, 3)
        response_text = response.text

        return {
            "skipped": False,
            "provider_call_made": True,
            "run_key": _RUN_KEY,
            "request_timestamp_utc": request_timestamp,
            "request_path": _PLAYER_GAMELOGS_PATH,
            "request_params": request_params,
            "provider_name": "mysportsfeeds",
            "http_status": response.status_code,
            "elapsed_seconds": elapsed_seconds,
            "response_size_bytes": len(response.content),
            "quota_relevant_headers": _quota_relevant_headers(response.headers),
            "response_body_text": response_text,
        }
