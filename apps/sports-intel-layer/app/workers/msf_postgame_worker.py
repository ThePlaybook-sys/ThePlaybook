"""Permanent MySportsFeeds completed-game boxscore ingestion path
(Permanent Box Score Worker Build, 2026-09-11, HQ-authorized "MANSA --
PERMANENT BOX SCORE WORKER BUILD, NO LIVE CALL").

Implements the accepted flow, for one canonical game at a time (matching
this pass's own framing -- a batch caller iterating candidate games is a
separate, later concern, same separation `app.workers.postgame_worker`
already draws between its own detection loop and
`_ingest_final_stats_for_game`):

    ELIGIBLE -> atomic claim -> resolve MSF game_provider_id
    -> perform boxscore request -> preserve raw response
    -> validate response/game identity -> inspect playedStatus
    -> not COMPLETED: schedule next check, no final persistence
    -> COMPLETED: automatic player identity activation/quarantine
       -> persist safe player-game stats -> record partial/full outcome
       -> advance durable ingestion state

**Separate module from `app.workers.postgame_worker` deliberately** --
that worker owns SportsDataIO's own game-final detection/reconciliation
concern (a different provider, a different table implicitly -- it
writes `games.status`/`finalized_at`/`team_stats`/`player_stats` via its
own +10m/+30m/+2h/+24h/+72h schedule). This worker owns
`game_postgame_ingestion_state`'s MSF-only state machine end to end and
never touches SportsDataIO's tables/adapters at all.

**NO live MySportsFeeds call is made anywhere in this pass.**
`_default_fetch_boxscore` below is real, permanent code -- the one place
a live call could ever happen through this path -- but it is never
invoked by anything in this commit: every test (including the Gate B
zero-cost replay) passes its own `fetch_boxscore` callable via this
module's dependency-injection seam, the same convention every other
worker in this codebase already uses for its adapters
(`schedule_adapter`/`team_stats_adapter`/`player_stats_adapter` in
`postgame_worker.py`, etc.).

## Call-control (HQ's already-approved policy, `app.workers.msf_call_control`)

- First eligibility ~kickoff+3h30m, subsequent not-ready follow-ups
  ~1h apart, hard cap 4 scheduled completion checks/game.
- `attempt_count` counts completed check attempts only -- never internal
  processing (identity activation / stat persistence) retries, per HQ's
  explicit rule 3. A bounded number of LOCAL transient retries
  (`MAX_LOCAL_TRANSIENT_RETRIES`) inside `_default_fetch_boxscore` are
  part of making ONE attempt succeed or fail, not additional attempts.
- Auth/invalid-request failures (401/403/400) escalate immediately
  (`capture_failed_permanent`), never locally retried and never left
  eligible for a future automatic check.
- "Already captured/confirmed games never call again": any row already
  at `confirmed_complete`, `partially_confirmed`, `capture_failed_permanent`,
  or `validation_failed` short-circuits at the very top of
  `run_msf_postgame_capture`, before even constructing a fetch attempt.
- "Worker restart/redeploy must not create duplicate provider calls":
  satisfied two ways -- (1) `claim_game_for_capture`'s atomic UPDATE
  means two concurrent/restarted workers can never both fetch for the
  same game at the same tick (proven for this exact shape in the Sunday
  Ingestion Foundation Build's own pgTAP suite); (2) a game already at
  `validated` (raw captured and confirmed COMPLETED, but per-player
  persistence didn't finish) resumes from the ALREADY-PRESERVED raw
  `game_events` row via `raw_capture_id` -- zero new provider calls, see
  `_finish_processing_completed_game` below.

## Partial-failure / recoverable-state semantics (HQ's rule 5)

- All players resolve and persist safely -> `confirmed_complete`.
- Some players quarantine, the rest persist safely -> `partially_confirmed`
  (never silently reported as fully complete).
- The captured response is unusable (wrong game, unparseable, missing
  `playedStatus`) -> `validation_failed`, raw evidence left intact
  (nothing here ever deletes/mutates a `game_events` row).
- A genuine persistence failure AFTER a valid raw capture and successful
  validation (e.g. a transient Supabase write error mid per-player loop)
  -> the row is simply left at `validated`, the exact resting/recoverable
  checkpoint the design's own state chain already provides for this: a
  later retry re-enters `run_msf_postgame_capture`, sees `state='validated'`,
  and resumes straight into `_finish_processing_completed_game` against
  the SAME preserved raw body -- no schema change needed, no new
  "persistence_failed" enum value invented, because `validated` already
  means exactly "raw captured and confirmed COMPLETED, downstream
  processing not yet finalized."
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx

from app.adapters.models import AdapterResponse, PlayerStatLine
from app.adapters.providers.mysportsfeeds_game_boxscore import parse_game_boxscore
from app.master_refresh.production_clients import build_msf_game_boxscore_diagnostic_client
from app.persistence.game_events import PersistenceError as GameEventsPersistenceError
from app.persistence.game_events import read_game_event, write_raw_game_event
from app.persistence.game_postgame_ingestion_state import (
    IngestionStateError,
    claim_game_for_capture,
    ensure_scheduled_row,
    get_ingestion_state,
    promote_due_scheduled_row,
    update_ingestion_state,
)
from app.persistence.games import GamesQueryError, get_game
from app.persistence.player_identity_activation import PlayerIdentityActivationError, activate_msf_player
from app.persistence.player_stats import PersistenceError as PlayerStatsPersistenceError
from app.persistence.player_stats import upsert_player_stat_row_if_changed
from app.persistence.seasons import SeasonResolutionError, fetch_current_season_year
from app.workers.msf_call_control import (
    MAX_LOCAL_TRANSIENT_RETRIES,
    first_check_at,
    hard_cap_reached,
    next_check_at,
)

_PROVIDER_NAME = "mysportsfeeds"

#: CONFIRMED literal, matching every prior MSF module's own
#: `authenticate()` convention (`app.diagnostics.msf_game_boxscore_diagnostic`,
#: `app.adapters.providers.mysportsfeeds`) -- not a real password.
_MSF_PASSWORD = "MYSPORTSFEEDS"

#: Terminal states a game never automatically re-enters capture from.
_ALREADY_FINALIZED_STATES = frozenset(
    {"confirmed_complete", "partially_confirmed", "capture_failed_permanent", "validation_failed"}
)


class MSFPostgameWorkerError(Exception):
    """Raised only for a genuine infra failure this module cannot itself
    classify into one of the named outcomes below (e.g. season
    resolution failing entirely) -- every normal outcome (not ready,
    transient/permanent failure, validation failure, partial/full
    success) is returned as a result object, never raised."""


@dataclass
class BoxscoreFetchResult:
    """Outcome of one bounded attempt to fetch a game's boxscore --
    `status` is one of "success" | "transient_error" | "permanent_error".
    `fetch_boxscore` callables (real or test-injected) return this."""

    status: str
    http_status: int | None = None
    body: Any | None = None
    error: str | None = None


@dataclass
class MSFPostgameCaptureResult:
    """Always returned, never raised for a normal outcome -- mirrors
    every other worker's finite-job result shape in this codebase."""

    game_id: str
    outcome: str
    state: str | None = None
    attempt_count: int | None = None
    resolved_players: int = 0
    quarantined_players: int = 0
    persisted_rows: int = 0
    unchanged_rows: int = 0
    error: str | None = None


@dataclass
class _ValidationResult:
    ok: bool
    played_status: str | None = None
    reason: str | None = None


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


def _msf_auth_header(api_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{api_key}:{_MSF_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _msf_season_string(year: int) -> str:
    """MySportsFeeds' own season-string format -- confirmed real
    (`app.diagnostics.msf_game_boxscore_diagnostic`'s own `_SEASON =
    "2026-2027-regular"`), distinct from SportsDataIO's `"{year}REG"`."""
    return f"{year}-{year + 1}-regular"


async def _reverse_resolve_msf_game_id(
    client: httpx.AsyncClient, headers: dict, *, game_id: str
) -> str | None:
    """Maps games.id -> mysportsfeeds provider_game_id. Mirrors
    `app.workers.postgame_worker._reverse_resolve_sportsdataio_ids`'s own
    established pattern, single-game rather than batch (this worker's own
    "one eligible canonical game" framing)."""
    response = await client.get(
        "/rest/v1/game_provider_ids",
        params={
            "provider_name": f"eq.{_PROVIDER_NAME}",
            "game_id": f"eq.{game_id}",
            "select": "provider_game_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise MSFPostgameWorkerError(
            f"failed to reverse-resolve mysportsfeeds game id for {game_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0]["provider_game_id"] if rows else None


def _validate_boxscore_payload(body: Any, *, expected_msf_game_id: str) -> _ValidationResult:
    """Validates the minimum this worker needs to trust a captured
    payload before ever touching player identity/stats: it's an object,
    it reports the SAME game we asked for (defense against a provider-side
    mismatch), and it carries a usable `playedStatus`. Raw evidence has
    ALREADY been preserved by the time this runs -- a failure here only
    ever moves the durable ingestion-state row to `validation_failed`, it
    never touches (and cannot touch) the already-written `game_events`
    row."""
    if not isinstance(body, dict):
        return _ValidationResult(ok=False, reason="boxscore response body was not a JSON object")
    game = body.get("game")
    if not isinstance(game, dict):
        return _ValidationResult(ok=False, reason="boxscore response missing a 'game' object")
    reported_game_id = game.get("id")
    if reported_game_id is None or str(reported_game_id) != str(expected_msf_game_id):
        return _ValidationResult(
            ok=False,
            reason=(
                f"boxscore response reported game id {reported_game_id!r}, "
                f"expected {expected_msf_game_id!r}"
            ),
        )
    played_status = game.get("playedStatus")
    if not isinstance(played_status, str) or not played_status:
        return _ValidationResult(ok=False, reason="boxscore response missing a usable playedStatus")
    return _ValidationResult(ok=True, played_status=played_status)


async def _default_fetch_boxscore(*, season: str, msf_game_id: str) -> BoxscoreFetchResult:
    """The ONE place a real MySportsFeeds boxscore call could ever be
    made through this path. NOT invoked anywhere in this pass -- every
    caller (including every test) supplies its own `fetch_boxscore` via
    dependency injection instead. Bounded local transient retries
    (`MAX_LOCAL_TRANSIENT_RETRIES`, immediate -- no artificial backoff
    sleep, see `app.workers.msf_call_control`'s own docstring) on
    transport errors or 429/5xx; 401/403/400 escalate immediately as
    permanent, never retried locally."""
    client_and_key = build_msf_game_boxscore_diagnostic_client()
    if client_and_key is None:
        return BoxscoreFetchResult(status="permanent_error", error="MYSPORTSFEEDS_API_KEY is not configured")

    client, api_key = client_and_key
    path = f"/nfl/{season}/games/{msf_game_id}/boxscore.json"

    async with client:
        last_error: str | None = None
        last_http_status: int | None = None
        for attempt in range(MAX_LOCAL_TRANSIENT_RETRIES + 1):
            try:
                response = await client.get(path, headers=_msf_auth_header(api_key))
            except httpx.HTTPError as exc:
                last_error = str(exc)
                continue

            last_http_status = response.status_code
            if response.status_code in (401, 403):
                return BoxscoreFetchResult(
                    status="permanent_error", http_status=response.status_code,
                    error=f"authentication failed ({response.status_code})",
                )
            if response.status_code == 400:
                return BoxscoreFetchResult(
                    status="permanent_error", http_status=response.status_code,
                    error=f"invalid request ({response.status_code}): {response.text}",
                )
            if response.status_code == 429 or response.status_code >= 500:
                last_error = f"provider returned {response.status_code}"
                continue
            if response.status_code != 200:
                return BoxscoreFetchResult(
                    status="permanent_error", http_status=response.status_code,
                    error=f"unexpected status {response.status_code}: {response.text}",
                )

            try:
                body = response.json()
            except ValueError as exc:
                return BoxscoreFetchResult(
                    status="permanent_error", http_status=response.status_code,
                    error=f"response body was not valid JSON: {exc}",
                )
            return BoxscoreFetchResult(status="success", http_status=response.status_code, body=body)

        return BoxscoreFetchResult(
            status="transient_error", http_status=last_http_status,
            error=last_error or "exhausted local transient retries",
        )


async def _finish_processing_completed_game(
    supabase_client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    raw_capture_id: str,
    body: Any,
    attempt_count: int | None,
) -> MSFPostgameCaptureResult:
    """Parses an already-captured, already-validated-COMPLETED boxscore
    body into player-game stats, running each real player through
    automatic identity activation (Rule I: one quarantined player never
    blocks a peer) and persisting safe rows idempotently. Re-entrant by
    construction: calling this again with the SAME `body` after a partial
    failure re-runs every player through the same reuse-or-create/
    insert-if-changed primitives, which are themselves idempotent -- no
    special "resume from player N" bookkeeping is needed."""
    adapter_response: AdapterResponse[list[PlayerStatLine]] = parse_game_boxscore(body)

    resolved = quarantined = persisted = unchanged = 0
    try:
        for line in adapter_response.value:
            activation = await activate_msf_player(
                supabase_client,
                headers,
                game_id=game_id,
                provider_player_id=line.player_external_id,
                provider_team_id=line.team,
                raw_player_name=line.player_name,
                raw_position=line.position,
                raw_capture_id=raw_capture_id,
            )
            if activation.outcome == "quarantined":
                quarantined += 1
                continue
            resolved += 1
            inserted = await upsert_player_stat_row_if_changed(
                supabase_client, headers, game_id=game_id, player_id=activation.player_id, stats=line.stats
            )
            if inserted:
                persisted += 1
            else:
                unchanged += 1
    except (PlayerIdentityActivationError, PlayerStatsPersistenceError) as exc:
        # Recoverable: raw evidence + validation already stand, the row
        # is already at 'validated' from the caller -- leave it there,
        # do NOT advance to any terminal state. A future retry resumes
        # from here with zero new provider calls.
        return MSFPostgameCaptureResult(
            game_id=game_id, outcome="persistence_failed", state="validated", attempt_count=attempt_count,
            resolved_players=resolved, quarantined_players=quarantined, persisted_rows=persisted,
            unchanged_rows=unchanged, error=str(exc),
        )

    final_state = "confirmed_complete" if quarantined == 0 else "partially_confirmed"
    await update_ingestion_state(
        supabase_client,
        headers,
        game_id=game_id,
        state=final_state,
        quarantine_reason=(f"{quarantined} player(s) quarantined, {resolved} resolved" if quarantined else None),
    )
    return MSFPostgameCaptureResult(
        game_id=game_id, outcome=final_state, state=final_state, attempt_count=attempt_count,
        resolved_players=resolved, quarantined_players=quarantined, persisted_rows=persisted,
        unchanged_rows=unchanged,
    )


async def run_msf_postgame_capture(
    *,
    supabase_client: httpx.AsyncClient,
    game_id: str,
    now: datetime | None = None,
    fetch_boxscore: Callable[..., Awaitable[BoxscoreFetchResult]] | None = None,
) -> MSFPostgameCaptureResult:
    """Runs one MSF postgame-capture tick for one canonical game. Always
    returns an `MSFPostgameCaptureResult`, never raises for a normal
    outcome -- same finite-job shape as every other worker in this
    codebase. `now` must be timezone-aware UTC (or convertible); defaults
    to the real current time.

    `fetch_boxscore` (dependency-injection seam, matching every other
    worker's adapter-injection convention): `None` (the default)
    constructs and calls the real `_default_fetch_boxscore` -- the one
    path that would make a live provider call. Every test in this pass
    supplies its own fake instead, so no live call is ever made here.
    """
    now = now or datetime.now(timezone.utc)
    headers = _auth_headers()
    fetch_boxscore = fetch_boxscore or _default_fetch_boxscore

    try:
        row = await get_ingestion_state(supabase_client, headers, game_id=game_id)

        # "Already captured/confirmed games never call again" -- checked
        # before anything else, including before any DI/network setup.
        if row is not None and row["state"] in _ALREADY_FINALIZED_STATES:
            return MSFPostgameCaptureResult(
                game_id=game_id, outcome="already_finalized", state=row["state"],
                attempt_count=row.get("attempt_count"),
            )

        # Resume path: raw already captured and confirmed COMPLETED, only
        # per-player processing remained. Zero new provider call.
        if row is not None and row["state"] == "validated":
            raw_capture_id = row.get("raw_capture_id")
            raw_row = await read_game_event(event_id=raw_capture_id) if raw_capture_id else None
            if raw_row is None:
                return MSFPostgameCaptureResult(
                    game_id=game_id, outcome="skipped_missing_evidence", state=row["state"],
                    attempt_count=row.get("attempt_count"),
                )
            body = raw_row["raw_payload"]["body"]
            return await _finish_processing_completed_game(
                supabase_client, headers, game_id=game_id, raw_capture_id=raw_capture_id, body=body,
                attempt_count=row.get("attempt_count"),
            )

        if row is None:
            game = await get_game(supabase_client, headers, game_id=game_id)
            if game is None:
                return MSFPostgameCaptureResult(game_id=game_id, outcome="skipped_unknown_game")
            kickoff = _parse_datetime(game["scheduled_start"])
            await ensure_scheduled_row(
                supabase_client, headers, game_id=game_id, first_eligible_at=first_check_at(kickoff)
            )

        await promote_due_scheduled_row(supabase_client, headers, game_id=game_id, now=now)

        claimed = await claim_game_for_capture(supabase_client, headers, game_id=game_id, now=now)
        if claimed is None:
            current = await get_ingestion_state(supabase_client, headers, game_id=game_id)
            return MSFPostgameCaptureResult(
                game_id=game_id, outcome="skipped_not_eligible",
                state=current["state"] if current else None,
                attempt_count=current.get("attempt_count") if current else None,
            )

        attempt_count = claimed.get("attempt_count") or 0

        msf_game_id = await _reverse_resolve_msf_game_id(supabase_client, headers, game_id=game_id)
        if msf_game_id is None:
            new_attempt_count = attempt_count + 1
            await update_ingestion_state(
                supabase_client, headers, game_id=game_id, state="capture_failed_permanent",
                error_classification="permanent", attempt_count=new_attempt_count,
                last_error="no mysportsfeeds game_provider_ids mapping for this game",
            )
            return MSFPostgameCaptureResult(
                game_id=game_id, outcome="capture_failed_permanent", state="capture_failed_permanent",
                attempt_count=new_attempt_count, error="no mysportsfeeds game id mapping",
            )

        year = await fetch_current_season_year(supabase_client, headers, league_code="nfl", today=now.date())
        season = _msf_season_string(year)

        fetch_result = await fetch_boxscore(season=season, msf_game_id=msf_game_id)
        new_attempt_count = attempt_count + 1

        if fetch_result.status == "transient_error":
            if hard_cap_reached(new_attempt_count):
                await update_ingestion_state(
                    supabase_client, headers, game_id=game_id, state="capture_failed_permanent",
                    error_classification="permanent", attempt_count=new_attempt_count,
                    last_http_status=fetch_result.http_status,
                    last_error=f"hard cap reached without a usable response: {fetch_result.error}",
                )
                return MSFPostgameCaptureResult(
                    game_id=game_id, outcome="capture_failed_permanent", state="capture_failed_permanent",
                    attempt_count=new_attempt_count, error=fetch_result.error,
                )
            await update_ingestion_state(
                supabase_client, headers, game_id=game_id, state="eligible_for_postgame_check",
                error_classification="transient", attempt_count=new_attempt_count,
                last_http_status=fetch_result.http_status, last_error=fetch_result.error,
                next_eligible_attempt_at=next_check_at(now).isoformat(),
            )
            return MSFPostgameCaptureResult(
                game_id=game_id, outcome="capture_failed_transient", state="eligible_for_postgame_check",
                attempt_count=new_attempt_count, error=fetch_result.error,
            )

        if fetch_result.status == "permanent_error":
            await update_ingestion_state(
                supabase_client, headers, game_id=game_id, state="capture_failed_permanent",
                error_classification="permanent", attempt_count=new_attempt_count,
                last_http_status=fetch_result.http_status, last_error=fetch_result.error,
            )
            return MSFPostgameCaptureResult(
                game_id=game_id, outcome="capture_failed_permanent", state="capture_failed_permanent",
                attempt_count=new_attempt_count, error=fetch_result.error,
            )

        # Success: preserve raw evidence BEFORE any parsing/mutation.
        evidence_envelope = {
            "provider_game_id": msf_game_id,
            "canonical_game_id": game_id,
            "season_param": season,
            "http_status": fetch_result.http_status,
            "captured_at": now.isoformat(),
            "body": fetch_result.body,
        }
        raw_capture_id = await write_raw_game_event(
            game_id=game_id, provider_name=_PROVIDER_NAME, raw_response=evidence_envelope, now=now
        )
        await update_ingestion_state(
            supabase_client, headers, game_id=game_id, state="captured", attempt_count=new_attempt_count,
            last_http_status=fetch_result.http_status, last_error=None, error_classification=None,
            captured_at=now.isoformat(), raw_capture_id=raw_capture_id,
        )

        validation = _validate_boxscore_payload(fetch_result.body, expected_msf_game_id=msf_game_id)
        if not validation.ok:
            await update_ingestion_state(
                supabase_client, headers, game_id=game_id, state="validation_failed",
                quarantine_reason=validation.reason,
            )
            return MSFPostgameCaptureResult(
                game_id=game_id, outcome="validation_failed", state="validation_failed",
                attempt_count=new_attempt_count, error=validation.reason,
            )

        if validation.played_status != "COMPLETED":
            if hard_cap_reached(new_attempt_count):
                await update_ingestion_state(
                    supabase_client, headers, game_id=game_id, state="capture_failed_permanent",
                    error_classification="permanent",
                    last_error=(
                        f"hard cap reached, playedStatus={validation.played_status!r}, "
                        "never confirmed COMPLETED"
                    ),
                )
                return MSFPostgameCaptureResult(
                    game_id=game_id, outcome="capture_failed_permanent", state="capture_failed_permanent",
                    attempt_count=new_attempt_count,
                    error=f"not completed after {new_attempt_count} checks",
                )
            await update_ingestion_state(
                supabase_client, headers, game_id=game_id, state="eligible_for_postgame_check",
                next_eligible_attempt_at=next_check_at(now).isoformat(),
            )
            return MSFPostgameCaptureResult(
                game_id=game_id, outcome="not_ready", state="eligible_for_postgame_check",
                attempt_count=new_attempt_count,
            )

        # COMPLETED: advance to the recoverable 'validated' checkpoint,
        # then finish processing in the same tick.
        await update_ingestion_state(supabase_client, headers, game_id=game_id, state="validated")
        return await _finish_processing_completed_game(
            supabase_client, headers, game_id=game_id, raw_capture_id=raw_capture_id, body=fetch_result.body,
            attempt_count=new_attempt_count,
        )
    except (IngestionStateError, GamesQueryError, GameEventsPersistenceError, SeasonResolutionError) as exc:
        raise MSFPostgameWorkerError(f"MSF postgame capture failed for game {game_id}: {exc}") from exc


__all__ = [
    "BoxscoreFetchResult",
    "MSFPostgameCaptureResult",
    "MSFPostgameWorkerError",
    "run_msf_postgame_capture",
]
