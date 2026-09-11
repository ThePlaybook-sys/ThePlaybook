"""MANSA -- MSF Week 1 Identity Recovery (2026-09-11, HQ-authorized
"MSF WEEK 1 IDENTITY RECOVERY").

TEMPORARY, DIAGNOSTIC-ONLY module. Makes the ONE real MySportsFeeds
schedule-level call HQ authorized to recover MSF's real game/team
identity for Week 1 -- this is IDENTITY RECOVERY, not postgame
ingestion: no boxscore call, no player creation, no player-game
persistence.

**Endpoint provenance, not guessed.** `week/{N}/games.json` (and the
whole-season `games.json`) are the exact, already-exercised MSF
schedule-listing request shapes from the 2026-09-03 NFL provider
bake-off (`docs/ops/nfl-provider-gap-test-mysportsfeeds-2026-09-03.md`,
"Cross-cutting findings") -- real, MSF-recognized paths (confirmed via
real HTTP responses on two independent call variants, not a URL-
formation guess). That bake-off's own calls used a **prior** season
(2025) and got a real, reproducible `403` -- a disclosed, plan-specific
restriction on **historical** game listings (the same plan's
`standings.json` for that exact same prior season succeeded, ruling out
a blanket season gate). The **current** 2026-2027 season's own
`week/{N}/games.json` has never been called before -- this pass is that
first real call, using the exact same proven path shape and the exact
same `{season}` string (`"2026-2027-regular"`) every other real MSF call
in this project already uses (Gate B's `game_boxscore`, the 8.2 players/
lineup diagnostics). The shape is proven; the outcome for the current
season is not assumed either way.

Reuses the existing, standing `build_msf_game_boxscore_diagnostic_client`
(despite its name, a general MSF-client builder -- `MYSPORTSFEEDS_API_KEY`
bound, 120.0s timeout, credential never read outside that one function)
rather than adding a second credential-isolated builder for the same
credential. Same `activation_run_markers` idempotency guard, same
exception-safety discipline, same durable-raw-preservation-before-
normalization convention (`write_raw_game_events`, existing, unmodified)
as every prior diagnostic pass.

**`game_id` anchor, disclosed rather than glossed over**: this response
covers the whole Week 1 schedule, not one game. Anchored to the SEA/NE
opener's canonical `game_id` (`280e7b05-1215-42c7-9bba-8a3631b86f26`),
the same disclosed modeling choice already used for the BALLDONTLIE
Week 1 schedule recovery pass -- `raw_payload` is un-normalized jsonb and
this affects no other game's data.

Reconciliation against canonical `games` (matching MSF's returned games
to the 16-game Week 1 universe by team pair + kickoff, the same
deterministic method already proven for BALLDONTLIE) and any resulting
`game_provider_ids`/report of coverage is a **separate, later, read-then-
report step against this persisted row** -- this diagnostic makes the
one authorized live call and preserves evidence; it does not itself
reconcile or mutate anything.
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
_WEEK = "1"
_SCHEDULE_PATH = f"/nfl/{_SEASON}/week/{_WEEK}/games.json"
_TIMEOUT_SECONDS = 120.0

#: The one canonical game already known to exist and already part of
#: this exact Week 1 schedule -- used only as the required FK anchor for
#: this schedule-level raw capture (see module docstring).
_ANCHOR_CANONICAL_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"

#: HQ-specified scope, verbatim: this pass recovers Week 1 MSF identity,
#: once. Reuses `activation_run_markers` exactly as every prior
#: diagnostic pass -- no second idempotency mechanism created.
_RUN_KEY = "msf-week1-schedule-recovery-2026-09-11"


class MsfScheduleRecoveryDiagnosticSkipped(Exception):
    """Raised (and caught by the caller) when this pass's run_key is
    already claimed in `activation_run_markers` -- an overlapping/
    duplicate container boot, not an error. Zero provider calls are made
    in that case, identical guarantee to every prior diagnostic pass in
    this project."""


def _msf_auth_header(api_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{api_key}:{_MSF_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


async def _claim_run_marker() -> None:
    """Claims this pass's dedicated `activation_run_markers` row. A 409
    means another container already claimed it -- raises
    `MsfScheduleRecoveryDiagnosticSkipped`, the caller's signal to make
    zero provider calls."""
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
        raise MsfScheduleRecoveryDiagnosticSkipped(
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


async def run_msf_week1_schedule_recovery() -> dict[str, Any]:
    """Claims this pass's run_key, then makes exactly ONE real MSF
    `week/{N}/games.json` request (season `2026-2027-regular`, week `1`)
    if the guard is acquired. On any actual HTTP response, durably
    persists a full evidence envelope to `game_events`. Returns a
    structured result in every case and never raises -- a diagnostic
    failure must never crash application startup."""
    try:
        await _claim_run_marker()
    except MsfScheduleRecoveryDiagnosticSkipped as exc:
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
            response = await client.get(_SCHEDULE_PATH, headers=_msf_auth_header(api_key))
        except httpx.TimeoutException as exc:
            return {
                "skipped": False,
                "provider_call_made": True,
                "run_key": _RUN_KEY,
                "request_timestamp_utc": request_timestamp,
                "request_path": _SCHEDULE_PATH,
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
                "request_path": _SCHEDULE_PATH,
                "provider_name": "mysportsfeeds",
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
        if isinstance(body, dict) and isinstance(body.get("games"), list):
            games_found = len(body["games"])

        evidence_envelope = {
            "recovery_run_key": _RUN_KEY,
            "purpose": "msf-week-1-identity-recovery",
            "anchor_canonical_game_id": _ANCHOR_CANONICAL_GAME_ID,
            "endpoint": str(client.base_url) + _SCHEDULE_PATH,
            "request_path": _SCHEDULE_PATH,
            "season_param": _SEASON,
            "week_param": _WEEK,
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
            "provider_name": "mysportsfeeds",
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "games_found": games_found,
            "elapsed_seconds": elapsed_seconds,
            "actual_body_byte_count": len(response.content),
        }

        try:
            rows_written = await write_raw_game_events(
                game_id=_ANCHOR_CANONICAL_GAME_ID,
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
    "MsfScheduleRecoveryDiagnosticSkipped",
    "redact_for_logging",
    "run_msf_week1_schedule_recovery",
]
