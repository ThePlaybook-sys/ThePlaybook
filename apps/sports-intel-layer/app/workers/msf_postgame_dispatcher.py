"""Permanent execution layer for `app.workers.msf_postgame_worker`
(Postgame Dispatcher + Sunday Recovery, 2026-09-14, HQ-authorized
"MANSA -- POSTGAME DISPATCHER + SUNDAY RECOVERY").

Root cause this module fixes (Sunday Postgame Ingestion Audit,
2026-09-14): the permanent worker (`run_msf_postgame_capture`) and its
permanent HTTP boundary (`POST /v1/internal/msf-postgame/run`) both
already existed and were both already correct -- nothing had ever called
either one automatically. This module is the smallest thing that closes
that gap: it finds due rows and calls the existing worker, once per row,
in order. It is deliberately NOT a second implementation of anything the
worker or its persistence layer already do:

- **Never bypasses worker validation.** Selection here is a plain `SELECT`
  against `game_postgame_ingestion_state` -- no state is read, claimed, or
  mutated by this module. The actual atomic claim
  (`claim_game_for_capture`'s `UPDATE ... WHERE state='eligible_for_
  postgame_check' AND next_eligible_attempt_at <= now()`) still happens
  exactly once, inside `run_msf_postgame_capture` itself, for every game
  this module invokes it for -- including the `scheduled -> eligible`
  promotion, which `run_msf_postgame_capture` also already does internally
  (`promote_due_scheduled_row`). A game this module selects because it
  looked due can still be legitimately skipped by the worker itself (e.g.
  claimed by a concurrent caller between selection and invocation) --
  that is the atomic claim working exactly as designed, not a dispatcher
  bug.
- **Never directly persists player stats.** This module never imports or
  calls anything from `app.persistence.player_stats`/
  `app.persistence.player_identity_activation` -- only
  `run_msf_postgame_capture` (and the modules it already calls) ever
  touches those.
- **Never duplicates business logic.** The state-machine semantics
  (terminal states, hard cap, cache/rate-limit-aware rescheduling,
  playedStatus authority, quarantine handling) all remain exactly where
  they already lived -- `app.workers.msf_postgame_worker`/
  `app.workers.msf_call_control`. This module's own selection query
  mirrors those rules defensively (see `_TERMINAL_STATES`/`hard_cap`
  filtering in `select_due_msf_postgame_games`) but never re-implements
  what happens once a game is invoked.

**Bounded, sequential, never a burst.** `dispatch_due_msf_postgame_games`
processes selected games strictly one at a time (no `asyncio.gather`, no
concurrency at all) and caps how many it invokes per call
(`MAX_GAMES_PER_DISPATCH_TICK`) -- a disclosed-conservative policy default
(not empirically derived, matching this codebase's own convention for
undecided numbers), chosen so one dispatcher tick's own real end-to-end
processing time (observed live in the SF@LAR Live Proof pass: ~2 minutes
for one game's full fetch + ~95-player resolve/persist cycle) stays safely
inside the cron caller's own request timeout, and so a real Sunday-scale
recovery spreads its real provider calls across several cron ticks rather
than firing 13 requests at once. Any games left over past the cap are
picked up automatically by the next scheduled tick -- no state is lost or
orphaned between ticks, since nothing about eligibility depends on this
module's own memory (`next_eligible_attempt_at`/`state` are the only
source of truth, both owned entirely by the worker/persistence layer).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from app.workers.msf_call_control import HARD_CAP_ATTEMPTS
from app.workers.msf_postgame_worker import MSFPostgameCaptureResult, run_msf_postgame_capture

_PROVIDER_NAME = "mysportsfeeds"

#: States a game can still be legitimately dispatched from. Excludes every
#: terminal state (`confirmed_complete`/`partially_confirmed`/
#: `capture_failed_permanent`/`validation_failed` -- `run_msf_postgame_
#: worker`'s own `_ALREADY_FINALIZED_STATES`) and `capture_in_progress`
#: (already claimed by a concurrent/in-flight invocation -- selecting it
#: again would just be a harmless no-op once `claim_game_for_capture`
#: rejects it, but excluding it here means the dispatcher never even
#: tries, which is honest about what it expects to happen).
_DISPATCHABLE_STATES = ("scheduled", "eligible_for_postgame_check", "validated")

#: Disclosed-conservative policy default (see module docstring) -- keeps
#: one dispatcher tick's real wall-clock time well inside the cron
#: caller's own request timeout and avoids a same-tick burst against the
#: provider. Not a HARD_CAP_ATTEMPTS-style approved number; a dispatcher-
#: level pacing choice this module alone owns.
MAX_GAMES_PER_DISPATCH_TICK = 4


class MSFPostgameDispatcherError(Exception):
    """Raised only for a genuine infra failure selecting due games (e.g.
    Supabase read failure) -- never for a normal per-game outcome, which
    is always represented in `DispatchResult.results` instead, mirroring
    `run_msf_postgame_capture`'s own never-raise-for-a-normal-outcome
    convention."""


@dataclass
class DispatchResult:
    """Always returned, never raised for a normal tick -- same finite-job
    shape as every other worker/dispatcher result in this codebase."""

    considered: int
    selected_game_ids: list[str] = field(default_factory=list)
    invoked_game_ids: list[str] = field(default_factory=list)
    results: list[MSFPostgameCaptureResult] = field(default_factory=list)


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def select_due_msf_postgame_games(
    client: httpx.AsyncClient, headers: dict, *, now: datetime
) -> list[dict]:
    """Pure, read-only `SELECT` -- no claim, no mutation, safe to call any
    number of times with zero side effects (the property the "zero-call
    dispatcher proof" pass exercises directly against real Sunday rows).

    A row is selected when:
    - `provider_name = 'mysportsfeeds'` (this dispatcher's only concern --
      SportsDataIO's separate postgame pipeline is untouched, unaffected,
      and not queried here at all);
    - `state` is one of `_DISPATCHABLE_STATES` (excludes every terminal
      state and the in-flight `capture_in_progress` state);
    - `attempt_count < HARD_CAP_ATTEMPTS` (defensive -- by construction,
      `run_msf_postgame_capture` itself already never leaves a row at
      `eligible_for_postgame_check` once its own `attempt_count` reaches
      the cap, moving it to `capture_failed_permanent` instead -- but this
      filter costs nothing and means this module never even offers such a
      row to the worker, rather than relying solely on that invariant);
    - EITHER `state = 'validated'` (always immediately due -- resuming
      costs zero new provider calls, see `run_msf_postgame_worker`'s own
      resume path) OR `next_eligible_attempt_at <= now`.

    Ordered oldest-overdue-eligibility-first (`next_eligible_attempt_at`
    ascending, nulls -- i.e. `validated` rows -- sorted first, since a
    zero-cost resume is always the most valuable thing to do first)."""
    response = await client.get(
        "/rest/v1/game_postgame_ingestion_state",
        params={
            "provider_name": f"eq.{_PROVIDER_NAME}",
            "state": f"in.({','.join(_DISPATCHABLE_STATES)})",
            "attempt_count": f"lt.{HARD_CAP_ATTEMPTS}",
            "or": f"(state.eq.validated,next_eligible_attempt_at.lte.{now.isoformat()})",
            "select": "game_id,state,attempt_count,next_eligible_attempt_at",
            "order": "next_eligible_attempt_at.asc.nullsfirst",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise MSFPostgameDispatcherError(
            f"failed to select due game_postgame_ingestion_state rows: "
            f"{response.status_code} {response.text}"
        )
    return response.json()


async def dispatch_due_msf_postgame_games(
    supabase_client: httpx.AsyncClient,
    *,
    now: datetime | None = None,
    fetch_boxscore=None,
    max_games: int = MAX_GAMES_PER_DISPATCH_TICK,
) -> DispatchResult:
    """One dispatcher tick: selects due rows (read-only), then invokes the
    existing, unmodified `run_msf_postgame_capture` for up to `max_games`
    of them, strictly sequentially (never concurrent -- see module
    docstring). `fetch_boxscore` is forwarded verbatim to every
    `run_msf_postgame_capture` call, the same dependency-injection seam
    that worker already exposes -- `None` (the default) means a real call
    constructs and uses the real `_default_fetch_boxscore`, exactly as a
    real cron tick would; the zero-call proof pass supplies its own
    non-network fake here instead, same convention as every other test in
    this codebase.

    Every selected-but-not-yet-invoked game (beyond `max_games`) is left
    completely untouched -- its row is unread, unclaimed, unmodified. The
    next tick (this same function, called again later, by the same
    recurring cron schedule) picks it up from scratch via a fresh
    `select_due_msf_postgame_games` call; nothing about the cap requires
    this module to remember anything between ticks."""
    now = now or datetime.now(timezone.utc)
    headers = _auth_headers()

    due_rows = await select_due_msf_postgame_games(supabase_client, headers, now=now)
    selected_game_ids = [row["game_id"] for row in due_rows]
    to_invoke = selected_game_ids[:max_games]

    results: list[MSFPostgameCaptureResult] = []
    for game_id in to_invoke:
        result = await run_msf_postgame_capture(
            supabase_client=supabase_client, game_id=game_id, now=now, fetch_boxscore=fetch_boxscore
        )
        results.append(result)

    return DispatchResult(
        considered=len(due_rows),
        selected_game_ids=selected_game_ids,
        invoked_game_ids=to_invoke,
        results=results,
    )


__all__ = [
    "MAX_GAMES_PER_DISPATCH_TICK",
    "MSFPostgameDispatcherError",
    "DispatchResult",
    "select_due_msf_postgame_games",
    "dispatch_due_msf_postgame_games",
]
