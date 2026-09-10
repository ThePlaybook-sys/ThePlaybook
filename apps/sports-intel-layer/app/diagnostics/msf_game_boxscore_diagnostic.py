"""MANSA Gate B -- MSF Game Boxscore Diagnostic (2026-09-10, HQ-authorized
BUILD pass, "GATE B RAILWAY DIAGNOSTIC BUILD").

TEMPORARY, DIAGNOSTIC-ONLY module. Implements Gate B's already-locked,
single-call MSF `game_boxscore` request from inside Railway DEV's own
network (sports-intel-layer), where `MYSPORTSFEEDS_API_KEY` already
exists and never needs to leave Railway or be seen by Claude. Mirrors the
proven Phase 8.3C pattern (`app.diagnostics.msf_player_stats_diagnostic`,
reverted after use, see `docs/ops/phase-8.3c-player-stats-diagnostic-
retry-2026-09-08.md`) -- same `activation_run_markers` idempotency guard,
same exception-safety discipline (a diagnostic failure must never crash
startup), same credential-isolation convention
(`MYSPORTSFEEDS_API_KEY` read only in `app.master_refresh.
production_clients.build_msf_game_boxscore_diagnostic_client`, never in
this module or `app.main`).

**This is a BUILD-ONLY pass per HQ's explicit instruction:
`RUN_MSF_GAME_BOXSCORE_DIAGNOSTIC` is NOT set by this commit, and no MSF
request has been made. Firing the one live call requires a separate,
explicit HQ authorization to flip that flag on Railway DEV.**

## What's different from the 8.3C pattern

1. **Endpoint**: `games/{id}/boxscore.json`, not `player_stats_totals`
   -- a single-game path parameter, no query filters. Season
   `2026-2027-regular` (current season), MSF game id `163541`
   (canonical MANSA game `280e7b05-1215-42c7-9bba-8a3631b86f26` --
   mapping verified real in Gate B's own preflight passes, persisted via
   `game_provider_ids`).
2. **120.0s timeout from the start** -- Phase 8.3B/8.3C's own lesson
   (a 30.0s client timeout was too short for at least one other MSF
   v2.1 feed) applied immediately, not re-learned the hard way here.
3. **Durable raw-evidence persistence, not Railway logs.** Reuses the
   EXISTING, UNMODIFIED `app.persistence.game_events.
   write_raw_game_events` (Volume 3 Section 4.3's raw-capture table --
   `raw_payload jsonb not null`, every typed column left null, exactly
   designed for "preserve a provider's raw payload without guessing its
   shape"). The full evidence envelope built in this module -- HTTP
   status, content type, request/response timestamps, endpoint,
   provider game id, this pass's run_key, response headers, and the raw
   body itself -- is written as ONE `game_events` row, so nothing
   depends on Railway's 80KB single-log-line truncation (the exact gap
   Phase 8.3C's own report flagged after losing part of a real payload
   to it). The Railway log only ever receives a short, explicitly
   redacted summary (`redact_for_logging`) -- never the full body, never
   any response header, never the credential.
4. **No new schema, no new table.** `game_events` and
   `activation_run_markers` both already exist; this module writes to
   both through their existing, unmodified public functions/REST shape.
"""
from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.master_refresh.production_clients import build_msf_game_boxscore_diagnostic_client
from app.persistence.game_events import PersistenceError, write_raw_game_events

#: CONFIRMED literal, not a real password -- the vendored `mysportsfeeds-
#: node` SDK's own `authenticate()` convention, identical provenance to
#: every prior MSF diagnostic in this project.
_MSF_PASSWORD = "MYSPORTSFEEDS"

_SEASON = "2026-2027-regular"
_MSF_GAME_ID = "163541"
_CANONICAL_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"
_BOXSCORE_PATH = f"/nfl/{_SEASON}/games/{_MSF_GAME_ID}/boxscore.json"
_TIMEOUT_SECONDS = 120.0

#: This pass's own dedicated run_key, HQ-specified verbatim. Reuses
#: `activation_run_markers` exactly as every prior MSF diagnostic pass
#: has -- no second idempotency mechanism created.
_RUN_KEY = "gate-b-msf-game-boxscore-163541-2026-09-10"


class GameBoxscoreDiagnosticSkipped(Exception):
    """Raised (and caught by the caller) when this pass's run_key is
    already claimed in `activation_run_markers` -- an overlapping/
    duplicate container boot, not an error. Zero provider calls are made
    in that case, across overlapping deployments, container restarts,
    healthcheck restarts, or Railway redeploys alike -- identical
    guarantee to every prior MSF diagnostic pass in this project."""


def _msf_auth_header(api_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{api_key}:{_MSF_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


async def _claim_run_marker() -> None:
    """Claims this pass's dedicated `activation_run_markers` row. A 409
    means another container already claimed it -- raises
    `GameBoxscoreDiagnosticSkipped`, the caller's signal to make zero
    provider calls. Any other non-2xx is a real failure, raised as-is so
    the caller's own defense-in-depth `except Exception` still converts
    it into a structured, non-fatal result rather than letting it
    propagate."""
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
        raise GameBoxscoreDiagnosticSkipped(
            f"run_key {_RUN_KEY!r} already claimed -- skipping duplicate diagnostic call"
        )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"failed to claim activation_run_markers row for {_RUN_KEY!r}: "
            f"{response.status_code} {response.text}"
        )


def redact_for_logging(result: dict[str, Any]) -> dict[str, Any]:
    """Safe-to-log summary of a diagnostic result: never the response
    body, never any response header value, never a credential -- only
    the small set of fields Gate B's own directive named as required
    provenance (HTTP status, content type, byte count, timestamps,
    run_key, endpoint identifier, whether durable evidence was
    persisted). The full body and headers live only in the `game_events`
    row this module writes, never in a Railway log line -- this is the
    one function that draws that line, so it is the one place to check
    when auditing "does this ever log the raw payload or the
    credential"."""
    allowed_keys = (
        "skipped",
        "reason",
        "provider_call_made",
        "run_key",
        "request_timestamp_utc",
        "response_timestamp_utc",
        "request_path",
        "provider_name",
        "provider_game_id",
        "http_status",
        "content_type",
        "actual_body_byte_count",
        "elapsed_seconds",
        "timeout_seconds",
        "error",
        "error_detail",
        "evidence_persisted",
        "evidence_rows_written",
        "persistence_error",
        "marker_claim_error",
    )
    return {key: result[key] for key in allowed_keys if key in result}


async def run_msf_game_boxscore_diagnostic() -> dict[str, Any]:
    """Claims this pass's run_key, then makes exactly ONE real MSF
    `game_boxscore` request (game 163541, 120.0s timeout) if the guard is
    acquired. On any actual HTTP response (any status code -- success or
    a provider-side error), durably persists a full evidence envelope to
    `game_events` via the existing, unmodified `write_raw_game_events`.
    Returns a structured result in every case -- success, skip, timeout,
    or transport error -- and never raises: a diagnostic failure must
    never crash application startup (the exact defect Phase 8.3B's own
    report disclosed and every diagnostic since has guarded against)."""
    try:
        await _claim_run_marker()
    except GameBoxscoreDiagnosticSkipped as exc:
        return {"skipped": True, "reason": str(exc), "provider_call_made": False}
    except Exception as exc:  # defense in depth -- a marker-claim failure must not crash startup either
        return {
            "skipped": True,
            "reason": f"failed to claim activation_run_markers row: {exc}",
            "provider_call_made": False,
            "marker_claim_error": True,
        }

    client_and_key = build_msf_game_boxscore_diagnostic_client()
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
            response = await client.get(_BOXSCORE_PATH, headers=_msf_auth_header(api_key))
        except httpx.TimeoutException as exc:
            return {
                "skipped": False,
                "provider_call_made": True,
                "run_key": _RUN_KEY,
                "request_timestamp_utc": request_timestamp,
                "request_path": _BOXSCORE_PATH,
                "provider_name": "mysportsfeeds",
                "provider_game_id": _MSF_GAME_ID,
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
                "request_path": _BOXSCORE_PATH,
                "provider_name": "mysportsfeeds",
                "provider_game_id": _MSF_GAME_ID,
                "http_status": None,
                "error": "transport_error",
                "error_detail": str(exc),
                "elapsed_seconds": round(time.monotonic() - start, 3),
            }

        response_timestamp = datetime.now(timezone.utc).isoformat()
        elapsed_seconds = round(time.monotonic() - start, 3)

        body: Any
        try:
            body = response.json()
        except ValueError:
            body = response.text

        evidence_envelope = {
            "gate_b_run_key": _RUN_KEY,
            "provider_game_id": _MSF_GAME_ID,
            "canonical_game_id": _CANONICAL_GAME_ID,
            "endpoint": str(client.base_url) + _BOXSCORE_PATH,
            "request_path": _BOXSCORE_PATH,
            "season_param": _SEASON,
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "content_length_header": response.headers.get("content-length"),
            "actual_body_byte_count": len(response.content),
            "request_timestamp_utc": request_timestamp,
            "response_timestamp_utc": response_timestamp,
            "elapsed_seconds": elapsed_seconds,
            "response_headers": dict(response.headers),
            "body": body,
        }

        result: dict[str, Any] = {
            "skipped": False,
            "provider_call_made": True,
            "run_key": _RUN_KEY,
            "request_timestamp_utc": request_timestamp,
            "response_timestamp_utc": response_timestamp,
            "request_path": _BOXSCORE_PATH,
            "provider_name": "mysportsfeeds",
            "provider_game_id": _MSF_GAME_ID,
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "elapsed_seconds": elapsed_seconds,
            "actual_body_byte_count": len(response.content),
        }

        try:
            rows_written = await write_raw_game_events(
                game_id=_CANONICAL_GAME_ID,
                provider_name="mysportsfeeds",
                raw_response=evidence_envelope,
            )
            result["evidence_persisted"] = rows_written == 1
            result["evidence_rows_written"] = rows_written
        except PersistenceError as exc:
            result["evidence_persisted"] = False
            result["persistence_error"] = str(exc)
        except Exception as exc:  # defense in depth, same discipline as the marker claim above
            result["evidence_persisted"] = False
            result["persistence_error"] = f"unexpected persistence failure: {exc}"

        return result


__all__ = [
    "GameBoxscoreDiagnosticSkipped",
    "redact_for_logging",
    "run_msf_game_boxscore_diagnostic",
]
