"""Odds Worker orchestration (Phase 3E-4D).

Volume 2 §8's own cadence row for Odds Worker: "Adaptive, game-aware...
Polling frequency ramps up as a game's kickoff approaches... Mirrors the
Player Props Worker's cadence shape below." Implemented entirely through
the single shared `app.workers.windows.classify_window` policy (3E-4F) --
this module computes no cadence numbers of its own, and Player Props
Worker (3E-4E) uses the exact same policy rather than a second copy of it.

**Master Refresh boundary (Decision 1, still in force, Phase 3E-2/3E-4D):**
this worker never calls Master Refresh, and Master Refresh never calls
this worker -- Master Refresh makes zero Odds provider calls, exactly as
its own ownership-boundary documentation states. This worker only *reads*
`games` (via `app.persistence.games.list_games_in_window`, the same
read-only helper Master Refresh itself uses) to determine its candidate
set; it never creates or updates a `games` row.

**Discovery + persistence flow, one bulk call per run:**
1. Query candidate games (see `_CANDIDATE_WINDOW_DAYS` below).
2. Classify each by kickoff proximity; skip anything STOPPED (already
   kicked off) or not yet due per its window's poll interval.
3. If nothing is due, skip the provider call entirely (Mac's "avoid
   duplicate provider calls where caching already satisfies freshness" --
   applied here as "don't even ask if nothing needs it").
4. Otherwise, one discovery-mode `fetch_odds([])` call (Phase 3E-4B/C) --
   the bulk endpoint always returns the full slate regardless of filter,
   so one call covers every due game at once. Wrapped in `CachingAdapter`
   with a dynamic TTL (Phase 3E-4F): the shortest (most urgent) TTL among
   this run's due games' windows, since one bulk response can span games
   in different windows and the cache must never treat a soon-kickoff
   game's data as fresher than its own window says it can be.
5. Link any not-yet-known event to its internal `games.id`
   (`app.persistence.odds_game_linking`, Phase 3E-4C) -- isolated
   per-event, never aborting the run.
6. Persist odds lines only for events that resolved to a game in this
   run's due set (`app.persistence.odds_snapshots`, append-only).

**Failure isolation:** a single game's linking/resolution failure never
blocks another game's -- `odds_game_linking`'s own batch function already
isolates per-event. A persistence failure is collected, not raised,
matching Mac's "provider failure does not crash unrelated game
processing" requirement.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.base import OddsAdapter
from app.adapters.cache import CacheBackend, CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, OddsLine
from app.adapters.providers.the_odds_api import TheOddsApiOddsAdapter
from app.persistence.game_identity import GameIdentityError, resolve_game_ids
from app.persistence.games import GamesQueryError, list_games_in_window, set_unresolved_poll_attempts
from app.persistence.odds_api_credit_ledger import CREDITS_PER_CALL, CreditLedgerError, read_credit_ledger, record_call
from app.persistence.odds_api_daily_call_budget import (
    DailyCallBudgetError,
    read_calls_used,
    utc_budget_date,
)
from app.persistence.odds_api_daily_call_budget import record_call as record_daily_call
from app.persistence.odds_game_linking import ProviderEventIdentity, resolve_and_link_odds_events
from app.persistence.odds_snapshots import PersistenceError, persist_odds_lines
from app.persistence.odds_worker_poll_state import PollState, PollStateError, record_attempt
from app.workers.odds_backoff import (
    OUTCOME_PROVIDER_FAILURE,
    OUTCOME_SUCCESS,
    OUTCOME_UNRESOLVED,
    backoff_elapsed,
    next_failure_count,
)
from app.workers.windows import Window, classify_window, should_poll, ttl_seconds

_PROVIDER_NAME = "the_odds_api"

#: Phase 7 Controlled Real Odds Activation (2026-09-07). Both env vars
#: must be set for the guard to activate at all -- an unset budget/floor
#: is never defaulted to an invented number (Mac's explicit instruction);
#: absence means "guard not configured," not "no limit," but this worker
#: makes that an explicit, disclosed no-op rather than a silent one (see
#: `_check_credit_guard`'s own docstring).
_CREDIT_BUDGET_ENV_VAR = "THE_ODDS_API_MONTHLY_CREDIT_BUDGET"
_CREDIT_FLOOR_ENV_VAR = "THE_ODDS_API_MIN_REMAINING_CREDITS"

#: Odds Worker Cost Hardening (2026-09-16). A HARD per-UTC-day ceiling on
#: provider calls, complementary to the monthly guard above rather than a
#: replacement for it: the monthly ledger stops the PERIOD being overrun,
#: this stops a single legal-but-expensive day consuming the whole
#: allocation before the period guard ever objects. Under the current */15
#: cron a day can legally reach 96 calls / 288 credits.
#:
#: Same explicit-configuration discipline as the monthly guard: an unset
#: value is NEVER defaulted to an invented number. Unset means "no daily
#: ceiling configured", which this worker reports as a disclosed no-op
#: rather than silently enforcing a made-up limit.
_DAILY_CALL_BUDGET_ENV_VAR = "ODDS_API_MAX_CALLS_PER_DAY"

#: How many of the day's calls are held back for games close to kickoff.
#: Once `calls_used` reaches `max_calls - reserve`, the remaining calls are
#: spent ONLY on a cycle where at least one due game has left the FAR tier.
#:
#: This is the whole priority mechanism, and it is shaped by the cost model
#: rather than bolted on: one bulk call serves every due game at once, so
#: there is nothing to rank WITHIN a call -- the only meaningful question is
#: whether THIS cycle is worth a call at all. Reserving the tail of the day's
#: budget for ramp-tier cycles answers exactly that. Unset means zero
#: reserve, i.e. no prioritization, which is today's behaviour.
_DAILY_RESERVE_ENV_VAR = "ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP"

#: Phase 7 Controlled Real Odds Activation safety fix (2026-09-07), after
#: a real incident: 3 manually-seeded games that never linked to a real
#: event triggered a paid call on every single cron tick, indefinitely,
#: since a game that can never accrue odds_snapshots history always reads
#: as "never polled." A `games.manual_seed=true` row is now excluded from
#: `due_games` once its own `unresolved_poll_attempts` reaches this cap --
#: a disclosed, conservative policy default (3 attempts = up to 45
#: minutes of retries at the standard */15 cadence, enough to survive one
#: transient hiccup, never unbounded), same "explicit, disclosed, not
#: empirically derived" discipline as every other policy default this
#: project has introduced (ADAPTIVE_WEIGHT_LEARNING_RATE, THRESHOLD_
#: VERSION). Never applied to a normal Schedule/Master-Refresh-sourced
#: game (manual_seed defaults false) -- those correctly keep retrying a
#: real, temporarily-unresolved team mapping forever, unaffected by this.
MANUAL_SEED_MAX_ATTEMPTS = 3

#: How many days out this worker considers a game a polling candidate at
#: all -- an independent, worker-level scoping decision, NOT a
#: reinterpretation of Master Refresh's own canonical
#: `[today, today + 7 days)` operating horizon (Volume 2 §8 v4.4, which
#: explicitly governs Master Refresh's game-identity/assembly work only
#: and states its own horizon "does not change any specialized worker's
#: cadence"). The same numeric value is used here for the practical
#: reason that Master Refresh itself only creates/maintains games this
#: far out -- there is nothing for this worker to poll beyond it -- not
#: because the two concepts are the same statement.
_CANDIDATE_WINDOW_DAYS = 7


@dataclass
class OddsWorkerResult:
    #: "success" | "partial" | "failed" | "skipped_credit_guard"
    #: | "skipped_daily_budget"
    status: str
    games_considered: int = 0
    games_due: int = 0
    games_skipped_not_due: int = 0
    #: Games that cadence WOULD have polled but which are still inside their
    #: failure backoff window. Reported separately from
    #: `games_skipped_not_due` so a slate being suppressed by repeated
    #: failures can never look like a slate that is simply up to date.
    games_skipped_backoff: int = 0
    lines_persisted: int = 0
    newly_linked: int = 0
    unresolved_events: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    error: str | None = None
    credits_used_this_period: int | None = None
    #: Provider calls spent on the current UTC day, after this cycle.
    daily_calls_used: int | None = None


async def _check_credit_guard(supabase_client: httpx.AsyncClient, headers: dict) -> tuple[bool, int | None]:
    """Returns `(allowed, credits_used_this_period)`. Fails OPEN (allowed
    the call) only when the guard itself isn't configured -- both
    `THE_ODDS_API_MONTHLY_CREDIT_BUDGET` and `THE_ODDS_API_MIN_REMAINING_
    CREDITS` must be set, or nothing is enforced; neither is ever
    defaulted to an invented number. Once both are configured, fails
    CLOSED (blocks the call) the moment `budget - credits_used <= floor`
    -- computed from this worker's own deterministic call-counting
    ledger (`app.persistence.odds_api_credit_ledger`), never from a
    parsed, ASSUMED vendor header."""
    budget_raw = os.environ.get(_CREDIT_BUDGET_ENV_VAR)
    floor_raw = os.environ.get(_CREDIT_FLOOR_ENV_VAR)
    if budget_raw is None or floor_raw is None:
        return True, None
    budget = int(budget_raw)
    floor = int(floor_raw)
    ledger = await read_credit_ledger(supabase_client, headers, provider_name=_PROVIDER_NAME)
    used = ledger["credits_used_this_period"] if ledger else 0
    remaining = budget - used
    return remaining > floor, used


async def _check_daily_call_budget(
    supabase_client: httpx.AsyncClient,
    headers: dict,
    *,
    now: datetime,
    due_windows: list[Window],
) -> tuple[bool, int | None, str | None]:
    """Returns `(allowed, calls_used_today, denial_reason)` for the hard
    per-UTC-day call ceiling.

    Fails OPEN when `ODDS_API_MAX_CALLS_PER_DAY` is unset -- an unconfigured
    ceiling is a disclosed no-op, never an invented number, exactly as
    `_check_credit_guard` treats its own two variables. Fails CLOSED once the
    day's calls are spent.

    **The reserve is the priority mechanism.** One bulk call serves every due
    game at once, so there is nothing to rank within a call; the only
    meaningful decision is whether this cycle deserves one. Once
    `calls_used >= max_calls - reserve`, the tail of the day's budget is
    released only for a cycle with at least one due game out of the FAR tier
    -- i.e. inside two hours of kickoff, where market movement is worth the
    most and a missed poll cannot be made up later.
    """
    budget_raw = os.environ.get(_DAILY_CALL_BUDGET_ENV_VAR)
    if budget_raw is None:
        return True, None, None

    max_calls = int(budget_raw)
    reserve_raw = os.environ.get(_DAILY_RESERVE_ENV_VAR)
    reserve = int(reserve_raw) if reserve_raw is not None else 0

    today = utc_budget_date(now)
    calls_used = await read_calls_used(
        supabase_client, headers, provider_name=_PROVIDER_NAME, budget_date=today
    )

    if calls_used >= max_calls:
        return (
            False,
            calls_used,
            f"daily call budget exhausted: {calls_used}/{max_calls} calls used on {today}",
        )

    discretionary_limit = max_calls - reserve
    if reserve > 0 and calls_used >= discretionary_limit:
        has_ramp_game = any(w is not Window.FAR for w in due_windows)
        if not has_ramp_game:
            return (
                False,
                calls_used,
                (
                    f"daily discretionary budget spent ({calls_used}/{discretionary_limit}); "
                    f"remaining {reserve} call(s) reserved for games inside 2h of kickoff, "
                    f"and no due game has left the FAR tier"
                ),
            )

    return True, calls_used, None


async def _record_attempts(
    supabase_client: httpx.AsyncClient,
    headers: dict,
    *,
    now: datetime,
    due_games: list[dict],
    poll_state: dict[str, PollState],
    captured_game_ids: set,
    outcome: str | None = None,
    failure_reason: str | None = None,
    linked_game_ids: set | None = None,
) -> list[str]:
    """Records one attempt row per due game and returns any write failures.

    Called ONLY after a real provider round-trip -- a cycle that made no call
    attempted nothing, and stamping an attempt for it would push healthy
    games into a backoff they did not earn.

    `outcome`, when given, applies to every due game (the provider-failure
    case, where nothing can be attributed per game). Otherwise the outcome is
    derived per game: captured this round -> success, everything else ->
    unresolved, with a reason that distinguishes "we have no event for this
    game at all" from "we have its event but it returned no lines".

    Write failures are returned rather than raised, matching this worker's
    established per-step isolation: failing to record an attempt must never
    discard odds a successful fetch already returned.
    """
    linked_game_ids = linked_game_ids or set()
    failures: list[str] = []
    for game in due_games:
        game_id = game["id"]
        captured = game_id in captured_game_ids
        if outcome is not None:
            game_outcome = outcome
            reason = failure_reason
        elif captured:
            game_outcome = OUTCOME_SUCCESS
            reason = None
        else:
            game_outcome = OUTCOME_UNRESOLVED
            reason = (
                "linked provider event returned no odds lines this cycle"
                if game_id in linked_game_ids
                else "no resolvable provider event matched this game"
            )

        existing = poll_state.get(game_id)
        current = existing.consecutive_failure_count if existing is not None else 0
        try:
            await record_attempt(
                supabase_client,
                headers,
                game_id=game_id,
                provider_name=_PROVIDER_NAME,
                attempted_at=now,
                outcome=game_outcome,
                consecutive_failure_count=next_failure_count(current=current, outcome=game_outcome),
                failure_reason=reason,
            )
        except PollStateError as exc:
            failures.append(f"poll state update failed for {game_id}: {exc}")
    return failures


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


async def run_odds_worker(
    *,
    supabase_client: httpx.AsyncClient,
    the_odds_api_client: httpx.AsyncClient,
    the_odds_api_key: str,
    cache_backend: CacheBackend | None = None,
    now: datetime | None = None,
    last_polled_at: dict[str, datetime] | None = None,
    target_game_ids: list[str] | None = None,
    odds_adapter: OddsAdapter | None = None,
    poll_state: dict[str, PollState] | None = None,
) -> OddsWorkerResult:
    """Runs one Odds Worker cycle. Always returns an `OddsWorkerResult`,
    never raises -- same finite-job shape as `run_master_refresh`.

    `odds_adapter` (dependency-injection seam, not Demo-specific): when
    supplied, this exact adapter instance is used instead of constructing
    `TheOddsApiOddsAdapter` -- e.g. Demo Mode's `DemoOddsAdapter`, or any
    other `OddsAdapter` implementation. `None` (the default) preserves
    today's real-provider construction and behavior unchanged for every
    existing caller.

    `last_polled_at` (game_id -> last successful poll time) is injected
    rather than read from any persisted state, since this phase does not
    build worker-run history storage (out of 3E-4's scope) -- a real
    scheduling mechanism (Railway Cron or otherwise, explicitly NOT
    decided in this phase per the stop condition) would be the thing that
    tracks and passes this in. Passing `None` (the default) means "treat
    every due game as never-polled," which is always safe -- it can only
    cause an extra poll, never a missed one.

    `target_game_ids` (Phase 3E-8, Decision 3): when provided, restricts
    this run to exactly these candidate games, treated as due
    unconditionally -- bypassing `classify_window`/`should_poll` entirely
    for them. This is Pregame Worker's own coordination hook: it forces
    this existing worker's own fetch/persistence path for one game right
    at T-minus-5-minutes, rather than duplicating any of this worker's
    logic. `None` (the default) preserves this worker's normal
    cadence-driven behavior unchanged for every other caller.
    """
    headers = _auth_headers()
    cache_backend = cache_backend or InMemoryCacheBackend()
    now = now or datetime.now(timezone.utc)
    last_polled_at = last_polled_at or {}
    poll_state = poll_state or {}

    today: date = now.date()
    try:
        games = await list_games_in_window(
            supabase_client, headers, start=today, end=today + timedelta(days=_CANDIDATE_WINDOW_DAYS)
        )
    except GamesQueryError as exc:
        return OddsWorkerResult(status="failed", error=f"failed to list candidate games: {exc}")

    if not games:
        return OddsWorkerResult(status="success", games_considered=0)

    target_set = set(target_game_ids) if target_game_ids is not None else None
    due_games: list[dict] = []
    skipped = 0
    skipped_backoff = 0
    for game in games:
        if target_set is not None:
            if game["id"] in target_set:
                due_games.append(game)
            else:
                skipped += 1
            continue
        kickoff = _parse_datetime(game["scheduled_start"])
        window = classify_window(now=now, kickoff=kickoff)
        if window is Window.STOPPED:
            continue  # already kicked off -- this worker generation never polls post-kickoff
        if game.get("manual_seed") and (game.get("unresolved_poll_attempts") or 0) >= MANUAL_SEED_MAX_ATTEMPTS:
            # Safety fix (2026-09-07): a manually-seeded game that has
            # never linked to a real event after MANUAL_SEED_MAX_ATTEMPTS
            # tries is excluded going forward -- never an unbounded paid-
            # call loop for a bad manual seed. Normal Schedule-sourced
            # games (manual_seed=false) are never affected by this check.
            skipped += 1
            continue

        # Cost + Failure Hardening (2026-09-16). Due-selection now consults
        # BOTH halves of a game's history, because they answer different
        # questions and conflating them is what caused the 2026-09-16 leak:
        #
        #   last SUCCESS  -> "is fresh odds data due for this game?" (cadence)
        #   last ATTEMPT  -> "have we already tried recently and failed?"
        #                    (backoff)
        #
        # Cadence is fed ONLY by a real capture, never by a bare attempt, so
        # an unresolved poll can never masquerade as fresh odds data. Backoff
        # can only ever SUPPRESS a poll cadence would have allowed -- it can
        # never cause one.
        state = poll_state.get(game["id"])
        # Fall back to the snapshot-derived timestamp when this game has no
        # poll-state row yet. Without this, every game that captured before
        # this feature shipped would read as never-successful on the first
        # run afterwards and come due at once, spending a call to rediscover
        # what `odds_snapshots` already knows.
        last_success = (
            state.last_success_at
            if state is not None and state.last_success_at is not None
            else last_polled_at.get(game["id"])
        )
        if not should_poll(now=now, kickoff=kickoff, last_polled_at=last_success):
            skipped += 1
            continue
        if state is not None and not backoff_elapsed(
            now=now,
            last_attempt_at=state.last_attempt_at,
            consecutive_failure_count=state.consecutive_failure_count,
        ):
            skipped_backoff += 1
            continue
        due_games.append(game)

    if not due_games:
        return OddsWorkerResult(
            status="success",
            games_considered=len(games),
            games_skipped_not_due=skipped,
            games_skipped_backoff=skipped_backoff,
        )

    # Phase 7 Controlled Real Odds Activation (2026-09-07): checked AFTER
    # deciding something is due (a guard-skip is a real, named outcome
    # distinct from "nothing was due"), BEFORE the real provider call.
    try:
        guard_allowed, credits_used = await _check_credit_guard(supabase_client, headers)
    except CreditLedgerError as exc:
        return OddsWorkerResult(
            status="failed", games_considered=len(games), games_due=len(due_games), error=f"credit guard read failed: {exc}"
        )
    if not guard_allowed:
        return OddsWorkerResult(
            status="skipped_credit_guard",
            games_considered=len(games),
            games_due=len(due_games),
            games_skipped_not_due=skipped,
            games_skipped_backoff=skipped_backoff,
            credits_used_this_period=credits_used,
        )

    # Dynamic TTL (Phase 3E-4F): the shortest (most urgent) TTL among this
    # run's due games -- one bulk response can span games in different
    # windows, and the cache must never treat a soon-kickoff game's data
    # as fresher than its own window allows.
    due_windows = [classify_window(now=now, kickoff=_parse_datetime(g["scheduled_start"])) for g in due_games]
    dynamic_ttl = min(ttl_seconds(w) for w in due_windows)

    # Cost Hardening (2026-09-16): the per-day ceiling, checked AFTER the
    # monthly guard (a blown month is the more serious condition and should
    # be the reported one) and BEFORE any provider call. A budget stop is a
    # normal, named outcome -- it returns cleanly so the cron exits 0 rather
    # than CRASHING, the same discipline `master_refresh`'s paused status
    # already follows.
    try:
        budget_allowed, daily_calls_used, budget_reason = await _check_daily_call_budget(
            supabase_client, headers, now=now, due_windows=due_windows
        )
    except DailyCallBudgetError as exc:
        return OddsWorkerResult(
            status="failed",
            games_considered=len(games),
            games_due=len(due_games),
            games_skipped_not_due=skipped,
            games_skipped_backoff=skipped_backoff,
            credits_used_this_period=credits_used,
            error=f"daily call budget read failed: {exc}",
        )
    if not budget_allowed:
        # No attempt is recorded for these games: no provider call was made,
        # so nothing was attempted, and recording one would wrongly push
        # healthy games into a backoff they did not earn.
        return OddsWorkerResult(
            status="skipped_daily_budget",
            games_considered=len(games),
            games_due=len(due_games),
            games_skipped_not_due=skipped,
            games_skipped_backoff=skipped_backoff,
            credits_used_this_period=credits_used,
            daily_calls_used=daily_calls_used,
            error=budget_reason,
        )

    odds_adapter = odds_adapter or TheOddsApiOddsAdapter(client=the_odds_api_client, api_key=the_odds_api_key)
    caching = CachingAdapter(odds_adapter, cache_backend, ttl_seconds=dynamic_ttl)
    try:
        response: AdapterResponse[list[OddsLine]] = await caching.call(
            "fetch_odds", [], response_model=AdapterResponse[list[OddsLine]]
        )
    except ProviderError as exc:
        # The call itself failed, so nothing can be attributed to any
        # individual game -- but every due game WAS attempted, and recording
        # that is the whole point of the attempt/success split. Without it a
        # provider outage would leave every game reading as never-polled and
        # hammering the provider on every tick for as long as the outage
        # lasted.
        attempt_failures = await _record_attempts(
            supabase_client,
            headers,
            now=now,
            due_games=due_games,
            poll_state=poll_state,
            captured_game_ids=set(),
            outcome=OUTCOME_PROVIDER_FAILURE,
            failure_reason=f"provider call failed: {exc}",
        )
        return OddsWorkerResult(
            status="failed",
            games_considered=len(games),
            games_due=len(due_games),
            games_skipped_not_due=skipped,
            games_skipped_backoff=skipped_backoff,
            credits_used_this_period=credits_used,
            daily_calls_used=daily_calls_used,
            failures=attempt_failures,
            error=f"Odds fetch failed: {exc}",
        )

    # Record real credit usage -- ONLY for a genuine provider round-trip,
    # never a cache hit (no credits are spent serving one). A ledger-write
    # failure is collected, not raised -- it must never block persisting
    # odds data a real, already-succeeded fetch already returned, matching
    # this worker's own established per-step failure isolation.
    credits_used_this_period = credits_used
    ledger_failures: list[str] = []
    if not response.from_cache:
        try:
            credits_used_this_period = await record_call(supabase_client, headers, provider_name=_PROVIDER_NAME, credits=CREDITS_PER_CALL)
        except CreditLedgerError as exc:
            ledger_failures.append(f"credit ledger write failed: {exc}")
        # Same "real round-trip only" rule as the credit ledger above: a
        # cache hit costs nothing and must not consume the day's ceiling.
        try:
            daily_calls_used = await record_daily_call(
                supabase_client,
                headers,
                provider_name=_PROVIDER_NAME,
                budget_date=utc_budget_date(now),
            )
        except DailyCallBudgetError as exc:
            ledger_failures.append(f"daily call budget write failed: {exc}")

    events_by_provider_id: dict[str, OddsLine] = {}
    for line in response.value:
        events_by_provider_id.setdefault(line.game_external_id, line)

    try:
        already_linked = await resolve_game_ids(
            supabase_client,
            headers,
            provider_name=_PROVIDER_NAME,
            provider_game_ids=list(events_by_provider_id.keys()),
        )
    except GameIdentityError as exc:
        return OddsWorkerResult(
            status="failed",
            games_considered=len(games),
            games_due=len(due_games),
            error=f"game identity lookup failed: {exc}",
        )

    to_link = [
        ProviderEventIdentity(
            provider_game_id=provider_id,
            home_team=line.home_team,
            away_team=line.away_team,
            commence_time=line.commence_time,
        )
        for provider_id, line in events_by_provider_id.items()
        if provider_id not in already_linked
    ]

    unresolved: list[str] = []
    newly_linked = 0
    if to_link:
        linking_result = await resolve_and_link_odds_events(supabase_client, headers, to_link)
        newly_linked = len(linking_result.linked)
        unresolved = [f"{e.provider_game_id}: {e.reason}" for e in linking_result.unresolved]
        for linked in linking_result.linked:
            already_linked[linked.provider_game_id] = linked.game_id

    due_game_ids = {g["id"] for g in due_games}
    lines_to_persist = [line for line in response.value if already_linked.get(line.game_external_id) in due_game_ids]

    # Safety fix (2026-09-07): track consecutive due-but-uncaptured
    # attempts for manual-seed games only -- see MANUAL_SEED_MAX_ATTEMPTS.
    # A capture this round (present in lines_to_persist) resets the
    # counter to 0 (the game has proven it links; ordinary cadence takes
    # over from here). A due manual-seed game with no capture this round
    # has its counter incremented by exactly one attempt.
    captured_game_ids = {already_linked.get(line.game_external_id) for line in lines_to_persist}
    attempt_failures: list[str] = []
    for game in due_games:
        if not game.get("manual_seed"):
            continue
        current_attempts = game.get("unresolved_poll_attempts") or 0
        if game["id"] in captured_game_ids:
            new_attempts = 0
        else:
            new_attempts = current_attempts + 1
        if new_attempts != current_attempts:
            try:
                await set_unresolved_poll_attempts(supabase_client, headers, game_id=game["id"], attempts=new_attempts)
            except GamesQueryError as exc:
                attempt_failures.append(f"unresolved_poll_attempts update failed for {game['id']}: {exc}")

    persisted = 0
    persistence_error: str | None = None
    failures: list[str] = list(ledger_failures) + attempt_failures
    if lines_to_persist:
        try:
            persisted = await persist_odds_lines(AdapterResponse(value=lines_to_persist, source=response.source))
        except PersistenceError as exc:
            persistence_error = str(exc)
            failures.append(f"persistence failed: {exc}")

    # Cost + Failure Hardening (2026-09-16): stamp every due game's attempt,
    # success or not. This is what stops an unresolvable game coming due on
    # every single tick forever. A game that captured resets to zero
    # failures and returns to ordinary cadence immediately; a game that did
    # not backs off deterministically.
    #
    # Deliberately keyed off `captured_game_ids` -- what actually persisted
    # -- rather than off the absence of an `unresolved_events` entry. Those
    # entries are keyed by the PROVIDER's event id, which by definition
    # could not be resolved to a game_id, so they can never be attributed
    # back to a specific canonical game.
    #
    # A persistence failure is NOT a success for any game, however many
    # lines the provider returned: nothing landed. It is recorded as a
    # uniform non-success for the whole due set, with the persistence error
    # itself as the reason, so the failure is preserved rather than dropped
    # AND a repeating persistence fault backs off instead of paying for a
    # provider call every tick to throw the results away.
    failures.extend(
        await _record_attempts(
            supabase_client,
            headers,
            now=now,
            due_games=due_games,
            poll_state=poll_state,
            captured_game_ids=set() if persistence_error else captured_game_ids,
            outcome=OUTCOME_UNRESOLVED if persistence_error else None,
            failure_reason=(
                f"odds lines fetched but persistence failed: {persistence_error}"
                if persistence_error
                else None
            ),
            linked_game_ids=set(already_linked.values()),
        )
    )

    status = "partial" if (failures or unresolved) else "success"

    return OddsWorkerResult(
        status=status,
        games_considered=len(games),
        games_due=len(due_games),
        games_skipped_not_due=skipped,
        games_skipped_backoff=skipped_backoff,
        lines_persisted=persisted,
        newly_linked=newly_linked,
        credits_used_this_period=credits_used_this_period,
        daily_calls_used=daily_calls_used,
        unresolved_events=unresolved,
        failures=failures,
    )
