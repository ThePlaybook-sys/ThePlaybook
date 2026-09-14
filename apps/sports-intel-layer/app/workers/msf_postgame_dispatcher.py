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
undecided numbers). Any games left over past the cap are picked up
automatically by the next scheduled tick -- no state is lost or orphaned
between ticks, since nothing about eligibility depends on this module's
own memory (`next_eligible_attempt_at`/`state` are the only source of
truth, both owned entirely by the worker/persistence layer).

**Timeout Hardening (2026-09-14, HQ-authorized "MANSA -- POSTGAME
DISPATCH TIMEOUT HARDENING", following the 502 investigation the same
day).** The original cap of 4 was sized off a single data point (SF@LAR,
~2 minutes/game) and, against real Sunday-scale data, a 4-game batch's
real aggregate duration (observed live: as long as ~15 minutes for some
batches, well past the single-game ~2 minute estimate) exceeded an
intermediate HTTP/proxy request-duration boundary on the path between
`cron-msf-postgame`'s client and `sports-intel-layer`'s public domain
(~5 minutes, most consistent with Railway's own edge/gateway in front of
the public `*.up.railway.app` domain -- not the origin itself, which the
502 investigation proved kept working to completion regardless of the
severed client connection; not a data-safety issue, a purely client-
visible/reporting one). Lowered to **2** so a tick's own real duration
stays comfortably under that boundary even at the slower end of observed
per-game timing (2 games x up to ~7-8 minutes each, worst case observed,
still lands with real margin below ~5 minutes for the common case, and
even a slow tick no longer risks the aggregate crossing so far past the
boundary that Railway's own cron health reporting goes stale/misleading).
This is a pacing-constant change only -- no per-game worker logic, retry
budget, or ingestion-state semantics changed alongside it.

**Automatic Enrollment (2026-09-14, HQ-authorized "MANSA -- AUTOMATIC
POSTGAME ENROLLMENT").** Root cause: `select_due_msf_postgame_games`
above only ever reads rows that already exist -- nothing anywhere
automatically created the *first* `scheduled` row for a newly-relevant
game (every row that existed before this pass came from a one-time,
manually-authorized SQL initialization). `select_unenrolled_eligible_
games` closes that gap with a second, equally read-only discovery query
(canonical `games` + `game_provider_ids`, never `game_postgame_
ingestion_state` mutated by the query itself), run every tick alongside
selection. **Enrollment eligibility (the deterministic rule, using only
already-persisted data, no provider call):** a canonical game qualifies
once (1) it has a real `game_provider_ids` row for `mysportsfeeds`, (2)
`games.scheduled_start <= now` -- kickoff has occurred, the literal
reading of "eligible for the postgame pipeline" (before kickoff there is
no completed game to check yet), and (3) no `game_postgame_ingestion_
state` row exists for it yet. A qualifying game gets exactly one row
created via the **existing, unmodified** `ensure_scheduled_row` --
enrollment does not invent a new mutation primitive; it only discovers
which `game_id`s should be handed to a function that already knew how to
enroll one. This is why enrollment is idempotent/duplicate-safe/
concurrency-safe/restart-safe with zero new code for any of those
properties: `ensure_scheduled_row`'s own check-then-insert (never an
upsert) plus its existing `(game_id, provider_name)` unique-constraint
409-recovery path (Sunday Ingestion Foundation Build) already guarantee
exactly one row ever exists per game, however many times or however
concurrently enrollment runs. Bounded separately from the main per-game
loop (`MAX_ENROLLMENTS_PER_DISPATCH_TICK`) since enrollment itself never
makes a provider call (cheap discovery + insert only) and must not share
budget with `MAX_GAMES_PER_DISPATCH_TICK`'s real-work cap -- a tick that
discovers many new games in one pass must not starve already-due games of
their own slots, and vice versa. A freshly-enrolled game is never claimed
or fetched in the same tick that enrolls it (its own `next_eligible_
attempt_at`, computed via the existing, unmodified `first_check_at`, is
always in the future relative to its own just-passed kickoff) -- it
becomes a normal candidate for `select_due_msf_postgame_games` on a later
tick, through the exact same unmodified claim/worker path every other
game already goes through. No per-game worker logic, claim protection,
retry limit, terminal-state exclusion, raw-preservation, or quarantine
behavior changed by this feature.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from app.persistence.game_postgame_ingestion_state import ensure_scheduled_row
from app.workers.msf_call_control import HARD_CAP_ATTEMPTS, first_check_at
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
#: one dispatcher tick's real wall-clock time well inside the intermediate
#: HTTP/proxy request-duration boundary the 502 investigation found
#: (~5 minutes) and avoids a same-tick burst against the provider. Not a
#: HARD_CAP_ATTEMPTS-style approved number; a dispatcher-level pacing
#: choice this module alone owns. Lowered from 4 to 2 (Postgame Dispatch
#: Timeout Hardening, 2026-09-14) after real Sunday-scale batches showed
#: 4-game aggregate duration reaching the boundary.
MAX_GAMES_PER_DISPATCH_TICK = 2

#: Disclosed-conservative policy default, separate from `MAX_GAMES_PER_
#: DISPATCH_TICK` on purpose (see module docstring's Automatic Enrollment
#: note) -- enrollment never makes a provider call (one discovery read
#: plus one lightweight insert per game via the already-idempotent
#: `ensure_scheduled_row`), so it can safely afford a higher per-tick
#: bound than real per-game work while still keeping a mass-mapping event
#: (e.g. a full week's schedule gaining MSF ids at once) from creating an
#: unbounded burst of inserts in one request -- the same §1.1 principle
#: #11 "bounded workload" discipline applied at a cheaper tier.
MAX_ENROLLMENTS_PER_DISPATCH_TICK = 20


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
    enrolled_game_ids: list[str] = field(default_factory=list)


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def select_unenrolled_eligible_games(
    client: httpx.AsyncClient, headers: dict, *, now: datetime
) -> list[dict]:
    """Pure, read-only discovery -- no row is created, no `game_postgame_
    ingestion_state` row is even inspected for its own fields beyond
    `game_id` (mirrors `select_due_msf_postgame_games`'s own read-only
    safety, extended to a second, complementary query). Three simple
    reads composed in Python (this module's own established convention --
    see `select_due_msf_postgame_games` above), not a PostgREST embedded
    join:

    1. Every `game_id` with a real `mysportsfeeds` `game_provider_ids`
       mapping.
    2. Every `game_id` that already has a `mysportsfeeds` `game_postgame_
       ingestion_state` row (any state, including terminal -- already-
       enrolled means already-enrolled regardless of what happened since).
    3. The real `scheduled_start` for whatever's left after (1) minus (2)
       -- a game not yet returned by MSF-mapping is never queried by id
       here at all, so an unmapped game can never appear even transiently.

    A candidate is eligible when its own real `scheduled_start <= now`
    (module docstring's enrollment-eligibility rule) -- a future game
    stays correctly unenrolled, discovered again next tick once its own
    kickoff has actually passed. Returns `[{"game_id", "scheduled_start"},
    ...]` ordered oldest-kickoff-first."""
    mapped_response = await client.get(
        "/rest/v1/game_provider_ids",
        params={"provider_name": f"eq.{_PROVIDER_NAME}", "select": "game_id"},
        headers=headers,
    )
    if mapped_response.status_code != 200:
        raise MSFPostgameDispatcherError(
            f"failed to read mysportsfeeds game_provider_ids for enrollment discovery: "
            f"{mapped_response.status_code} {mapped_response.text}"
        )
    mapped_ids = {row["game_id"] for row in mapped_response.json()}
    if not mapped_ids:
        return []

    enrolled_response = await client.get(
        "/rest/v1/game_postgame_ingestion_state",
        params={"provider_name": f"eq.{_PROVIDER_NAME}", "select": "game_id"},
        headers=headers,
    )
    if enrolled_response.status_code != 200:
        raise MSFPostgameDispatcherError(
            f"failed to read enrolled game ids for enrollment discovery: "
            f"{enrolled_response.status_code} {enrolled_response.text}"
        )
    enrolled_ids = {row["game_id"] for row in enrolled_response.json()}

    candidate_ids = sorted(mapped_ids - enrolled_ids)
    if not candidate_ids:
        return []

    games_response = await client.get(
        "/rest/v1/games",
        params={"id": f"in.({','.join(candidate_ids)})", "select": "id,scheduled_start"},
        headers=headers,
    )
    if games_response.status_code != 200:
        raise MSFPostgameDispatcherError(
            f"failed to read candidate games for enrollment discovery: "
            f"{games_response.status_code} {games_response.text}"
        )

    eligible = [
        {"game_id": row["id"], "scheduled_start": row["scheduled_start"]}
        for row in games_response.json()
        if _parse_ts(row["scheduled_start"]) <= now
    ]
    eligible.sort(key=lambda r: r["scheduled_start"])
    return eligible


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
    max_enrollments: int = MAX_ENROLLMENTS_PER_DISPATCH_TICK,
) -> DispatchResult:
    """One dispatcher tick, two independent phases:

    **Phase 1 -- enrollment (module docstring's Automatic Enrollment
    note).** `select_unenrolled_eligible_games` discovers up to
    `max_enrollments` real, past-kickoff, MSF-mapped canonical games with
    no `game_postgame_ingestion_state` row yet, then calls the existing,
    unmodified `ensure_scheduled_row` once per game. Zero provider calls;
    zero claims; a freshly-enrolled game is never invoked in this same
    tick (see module docstring for why its own `next_eligible_attempt_at`
    is always still in the future).

    **Phase 2 -- dispatch (unchanged from Postgame Dispatch Timeout
    Hardening).** Selects due rows (read-only), then invokes the
    existing, unmodified `run_msf_postgame_capture` for up to `max_games`
    of them, strictly sequentially (never concurrent -- see module
    docstring). `fetch_boxscore` is forwarded verbatim to every
    `run_msf_postgame_capture` call, the same dependency-injection seam
    that worker already exposes -- `None` (the default) means a real call
    constructs and uses the real `_default_fetch_boxscore`, exactly as a
    real cron tick would; the zero-call proof pass supplies its own
    non-network fake here instead, same convention as every other test in
    this codebase.

    Every selected-but-not-yet-invoked game (beyond `max_games`) and every
    discovered-but-not-yet-enrolled game (beyond `max_enrollments`) is
    left completely untouched. The next tick (this same function, called
    again later, by the same recurring cron schedule) picks both up from
    scratch via fresh discovery/selection calls; nothing about either cap
    requires this module to remember anything between ticks."""
    now = now or datetime.now(timezone.utc)
    headers = _auth_headers()

    unenrolled = await select_unenrolled_eligible_games(supabase_client, headers, now=now)
    to_enroll = unenrolled[:max_enrollments]
    enrolled_game_ids: list[str] = []
    for candidate in to_enroll:
        kickoff = _parse_ts(candidate["scheduled_start"])
        await ensure_scheduled_row(
            supabase_client, headers, game_id=candidate["game_id"], first_eligible_at=first_check_at(kickoff)
        )
        enrolled_game_ids.append(candidate["game_id"])

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
        enrolled_game_ids=enrolled_game_ids,
    )


__all__ = [
    "MAX_GAMES_PER_DISPATCH_TICK",
    "MAX_ENROLLMENTS_PER_DISPATCH_TICK",
    "MSFPostgameDispatcherError",
    "DispatchResult",
    "select_due_msf_postgame_games",
    "select_unenrolled_eligible_games",
    "dispatch_due_msf_postgame_games",
]
