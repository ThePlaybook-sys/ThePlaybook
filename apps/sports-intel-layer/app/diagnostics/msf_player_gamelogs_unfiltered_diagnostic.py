"""MANSA Phase 8.4D -- Unfiltered Player Gamelogs Diagnostic (2026-09-08,
HQ-authorized).

TEMPORARY, DIAGNOSTIC-ONLY module. Makes exactly ONE real MySportsFeeds
request -- `GET /nfl/2025-2026-regular/player_gamelogs.json`, **zero
query parameters** -- to determine whether Phase 8.4B's HTTP 400 was
caused by the `player=9999` filter specifically, or whether the
`seasonal_player_gamelogs` feed rejects requests regardless of filter
(matching the original `team_gamelogs` feed's own real, unfiltered
Run-1 400). **No player stats are persisted by this module.**

## Request design (per Phase 8.4C's own forensic audit)

- **Feed key / endpoint**: `seasonal_player_gamelogs` -> `player_
  gamelogs.json`, identical derivation to Phase 8.4B's request --
  confirmed mechanically correct by the vendored SDK's own feed table,
  not the suspected cause of that pass's 400.
- **Season**: `2025-2026-regular` -- unchanged, matching every
  successful/attempted MSF v2.1 NFL request this project has made.
- **No query parameters of any kind** -- this is the entire point of
  this pass: isolate whether the feed itself works before any filter is
  added, the one variable Phase 8.4B's own request could not isolate on
  its own.

## Execution safety

Reuses `activation_run_markers` verbatim with a new, dedicated run_key
-- the marker, not the `RUN_MSF_PLAYER_GAMELOGS_UNFILTERED_DIAGNOSTIC`
env var, is the authoritative once-only guard (proven live across
overlapping Railway deployments in every Phase 8.3/8.4B pass so far).
120.0s timeout. Every network call in this module (the marker claim and
the live MSF request) is wrapped so a timeout or provider error returns
a structured result rather than raising -- matching Phase 8.3C/8.4B's
own proven exception-safe design, applied here from the start.

## Raw capture policy

Identical to Phase 8.4B's own proven design: the full response is
logged in fixed-size chunks well under Railway's observed 80KB
single-log-line truncation limit, each chunk tagged with an explicit
sequence marker for exact reassembly from the deploy log. Only the
response body is chunked/logged; request headers (which carry the
Basic-auth credential) are never logged, in whole or in part.
"""
from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.master_refresh.production_clients import (
    build_msf_player_gamelogs_unfiltered_diagnostic_client,
)

_MSF_PASSWORD = "MYSPORTSFEEDS"  # CONFIRMED literal, not a real password -- SDK's own authenticate() example
_PLAYER_GAMELOGS_PATH = "/nfl/2025-2026-regular/player_gamelogs.json"
_TIMEOUT_SECONDS = 120.0

#: This diagnostic's own dedicated run_key -- distinct from every prior
#: Phase 8.3/8.4 marker, reusing the same activation_run_markers table
#: verbatim. No other marker row is touched by this pass.
_RUN_KEY = "phase-8.4d-player-gamelogs-unfiltered-diagnostic-2026-09-08"

#: Comfortably under Railway's observed 80KB (81,920-char) single-log-
#: line truncation limit, leaving headroom for the log-line prefix and
#: sequence marker text itself.
_LOG_CHUNK_SIZE = 60000


class PlayerGamelogsUnfilteredDiagnosticSkipped(Exception):
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
        raise PlayerGamelogsUnfilteredDiagnosticSkipped(
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


async def run_msf_player_gamelogs_unfiltered_diagnostic() -> dict[str, Any]:
    """Claims this pass's run_key, then makes exactly ONE real
    `player_gamelogs` request -- no query parameters -- if the guard is
    acquired. Returns a structured evidence envelope in every case --
    success, timeout, transport error, or skip -- and never raises.
    Never logs anything itself; the caller (the `main.py` startup hook)
    owns chunked logging of the returned envelope's `response_body_text`
    field via `chunk_for_logging`."""
    try:
        await _claim_run_marker()
    except PlayerGamelogsUnfilteredDiagnosticSkipped as exc:
        return {"skipped": True, "reason": str(exc), "provider_call_made": False}
    except Exception as exc:  # defense in depth -- a marker-claim failure must not crash startup either
        return {
            "skipped": True,
            "reason": f"failed to claim activation_run_markers row: {exc}",
            "provider_call_made": False,
            "marker_claim_error": True,
        }

    client_and_key = build_msf_player_gamelogs_unfiltered_diagnostic_client()
    if client_and_key is None:
        return {
            "skipped": True,
            "reason": "MYSPORTSFEEDS_API_KEY is not configured",
            "provider_call_made": False,
        }

    client, api_key = client_and_key
    request_timestamp = datetime.now(timezone.utc).isoformat()

    async with client:
        start = time.monotonic()
        try:
            response = await client.get(
                _PLAYER_GAMELOGS_PATH,
                headers=_msf_auth_header(api_key),
            )
        except httpx.TimeoutException as exc:
            return {
                "skipped": False,
                "provider_call_made": True,
                "run_key": _RUN_KEY,
                "request_timestamp_utc": request_timestamp,
                "request_path": _PLAYER_GAMELOGS_PATH,
                "request_params": {},
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
                "request_params": {},
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
            "request_params": {},
            "provider_name": "mysportsfeeds",
            "http_status": response.status_code,
            "elapsed_seconds": elapsed_seconds,
            "response_size_bytes": len(response.content),
            "quota_relevant_headers": _quota_relevant_headers(response.headers),
            "response_body_text": response_text,
        }
