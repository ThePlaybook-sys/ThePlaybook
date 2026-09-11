"""MANSA -- Week 1 Canonical Schedule Recovery (2026-09-11, HQ-authorized
"WEEK 1 CANONICAL SCHEDULE RECOVERY").

TEMPORARY, DIAGNOSTIC-ONLY module. Makes the ONE real BALLDONTLIE
`nfl/v1/games` call HQ authorized to recover the real provider game ids
for the 11 canonical Week 1 games the 2026-09-07 calibration pass
intentionally left unseeded (`docs/ops/phase-8-sunday-canonical-game-
coverage-audit-2026-09-11.md`). Same request shape as that pass's own
probe (`seasons=[2026]`, `weeks=[1]`, `per_page=25`) -- not a new
endpoint, not a new parameter set, exactly the proven call repeated once.

**What's different from the 2026-09-07 pass, by explicit HQ instruction
this time**: the full raw response is persisted durably via the existing,
unmodified `app.persistence.game_events.write_raw_game_events` -- Railway
logs are never the source of truth. The 2026-09-07 probe only logged its
raw payload (`_logger.warning(...)`), which this project's own audit
confirmed left the 11 missing games' real provider ids unrecoverable from
anything persisted. This pass closes that gap the same way Gate B's own
MSF diagnostic already does for MSF: one durable `game_events` row,
`raw_payload` carrying the complete evidence envelope (request/response
metadata, headers, and the full parsed body), never truncated by
Railway's log line limits.

**`game_id` anchor, disclosed rather than glossed over**: `write_raw_game_events`
requires a single canonical `game_id` (Volume 3 Section 4.3's own
per-game raw-capture design) -- this response covers all 16 real Week 1
games, not one. Anchored to the already-existing SEA/NE opener's
canonical `game_id` (`280e7b05-1215-42c7-9bba-8a3631b86f26`), since it is
the one canonical game already guaranteed to exist and is itself part of
this exact Week 1 schedule -- a deliberate, disclosed modeling choice,
not a data-integrity concern (`raw_payload` is jsonb and un-normalized;
nothing about this choice affects any other game's own data). Reconciling
the response's 16 games against canonical `games`, and creating the 11
missing games, is a **separate, later, read-then-activate step against
this persisted row** -- this diagnostic makes the one authorized live
call and preserves evidence; it does not itself mutate `games` or
`game_provider_ids`.

Same `activation_run_markers` idempotency guard, same exception-safety
discipline, same credential-isolation convention (`BALLDONTLIE_API_KEY`
read only in `app.master_refresh.production_clients.
build_real_balldontlie_client`, already the standing, permanent builder
this project uses elsewhere -- not recreated here) as every prior
diagnostic pass.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.master_refresh.production_clients import MissingCredentialError, build_real_balldontlie_client
from app.persistence.game_events import PersistenceError, write_raw_game_events

_SCHEDULE_PATH = "/nfl/v1/games"
_SEASON_PARAM = "2026"
_WEEK_PARAM = "1"
_PER_PAGE = "25"
_TIMEOUT_SECONDS = 60.0

#: The one canonical game already known to exist and already part of this
#: exact Week 1 schedule -- used only as the required FK anchor for this
#: schedule-level raw capture (see module docstring).
_ANCHOR_CANONICAL_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"

#: HQ-specified scope, verbatim: this pass recovers Week 1 schedule
#: identity, once. Reuses `activation_run_markers` exactly as every prior
#: diagnostic pass -- no second idempotency mechanism created.
_RUN_KEY = "balldontlie-week1-schedule-recovery-2026-09-11"


class ScheduleRecoveryDiagnosticSkipped(Exception):
    """Raised (and caught by the caller) when this pass's run_key is
    already claimed in `activation_run_markers` -- an overlapping/
    duplicate container boot, not an error. Zero provider calls are made
    in that case, identical guarantee to every prior diagnostic pass in
    this project."""


async def _claim_run_marker() -> None:
    """Claims this pass's dedicated `activation_run_markers` row. A 409
    means another container already claimed it -- raises
    `ScheduleRecoveryDiagnosticSkipped`, the caller's signal to make zero
    provider calls."""
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
        raise ScheduleRecoveryDiagnosticSkipped(
            f"run_key {_RUN_KEY!r} already claimed -- skipping duplicate diagnostic call"
        )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"failed to claim activation_run_markers row for {_RUN_KEY!r}: "
            f"{response.status_code} {response.text}"
        )


def redact_for_logging(result: dict[str, Any]) -> dict[str, Any]:
    """Safe-to-log summary: never the response body, never any response
    header value, never the credential -- only small provenance fields.
    The full body and headers live only in the `game_events` row this
    module writes, never in a Railway log line."""
    allowed_keys = (
        "skipped",
        "reason",
        "provider_call_made",
        "run_key",
        "request_timestamp_utc",
        "response_timestamp_utc",
        "request_path",
        "provider_name",
        "http_status",
        "content_type",
        "actual_body_byte_count",
        "games_found",
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


async def run_balldontlie_week1_schedule_recovery() -> dict[str, Any]:
    """Claims this pass's run_key, then makes exactly ONE real BALLDONTLIE
    `nfl/v1/games` request (`seasons=[2026]`, `weeks=[1]`) if the guard is
    acquired. On any actual HTTP response, durably persists a full
    evidence envelope to `game_events`. Returns a structured result in
    every case and never raises -- a diagnostic failure must never crash
    application startup."""
    try:
        await _claim_run_marker()
    except ScheduleRecoveryDiagnosticSkipped as exc:
        return {"skipped": True, "reason": str(exc), "provider_call_made": False}
    except Exception as exc:  # defense in depth -- a marker-claim failure must not crash startup either
        return {
            "skipped": True,
            "reason": f"failed to claim activation_run_markers row: {exc}",
            "provider_call_made": False,
            "marker_claim_error": True,
        }

    try:
        client, api_key = build_real_balldontlie_client()
    except MissingCredentialError as exc:
        return {
            "skipped": True,
            "reason": str(exc),
            "provider_call_made": False,
        }

    request_params = {"seasons[]": _SEASON_PARAM, "weeks[]": _WEEK_PARAM, "per_page": _PER_PAGE}
    request_timestamp = datetime.now(timezone.utc).isoformat()

    async with client:
        start = time.monotonic()
        try:
            response = await client.get(
                _SCHEDULE_PATH,
                params=request_params,
                headers={"Authorization": api_key},
                timeout=_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as exc:
            return {
                "skipped": False,
                "provider_call_made": True,
                "run_key": _RUN_KEY,
                "request_timestamp_utc": request_timestamp,
                "request_path": _SCHEDULE_PATH,
                "provider_name": "balldontlie",
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
                "request_path": _SCHEDULE_PATH,
                "provider_name": "balldontlie",
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

        games_found = None
        if isinstance(body, dict) and isinstance(body.get("data"), list):
            games_found = len(body["data"])

        evidence_envelope = {
            "recovery_run_key": _RUN_KEY,
            "purpose": "week-1-canonical-schedule-recovery",
            "anchor_canonical_game_id": _ANCHOR_CANONICAL_GAME_ID,
            "endpoint": str(client.base_url) + _SCHEDULE_PATH,
            "request_path": _SCHEDULE_PATH,
            "request_params": request_params,
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "content_length_header": response.headers.get("content-length"),
            "actual_body_byte_count": len(response.content),
            "request_timestamp_utc": request_timestamp,
            "response_timestamp_utc": response_timestamp,
            "elapsed_seconds": elapsed_seconds,
            "response_headers": dict(response.headers),
            "games_found": games_found,
            "body": body,
        }

        result: dict[str, Any] = {
            "skipped": False,
            "provider_call_made": True,
            "run_key": _RUN_KEY,
            "request_timestamp_utc": request_timestamp,
            "response_timestamp_utc": response_timestamp,
            "request_path": _SCHEDULE_PATH,
            "provider_name": "balldontlie",
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "games_found": games_found,
            "elapsed_seconds": elapsed_seconds,
            "actual_body_byte_count": len(response.content),
        }

        try:
            rows_written = await write_raw_game_events(
                game_id=_ANCHOR_CANONICAL_GAME_ID,
                provider_name="balldontlie",
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
    "ScheduleRecoveryDiagnosticSkipped",
    "redact_for_logging",
    "run_balldontlie_week1_schedule_recovery",
]
