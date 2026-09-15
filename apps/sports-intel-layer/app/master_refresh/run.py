"""Master Refresh orchestration (Phase 3E-2).

Runs as a finite job -- `run_master_refresh()` always returns a
`MasterRefreshResult`, never raises, so a future thin entry point (CLI
script, Railway Cron Job -- neither built here per the stop condition)
can decide exit-code/alerting behavior from `result.status` without
needing its own try/except around this function. This is Decision 6's
"start -> execute -> report success/failure -> exit" shape.

**Failure isolation (Decision 5 + the approved failure-isolation table):**
  BLOCKING (aborts the whole run, `status="failed"`): season resolution
    failure, Schedule provider fetch failure (HTTP/auth/rate-limit/
    outage, or a non-array top-level payload), Schedule persistence
    failure. Nothing past this point runs; nothing already-persisted is
    touched, modified, or deleted.
  NON-BLOCKING (isolated, collected, run continues): a single team's
    roster fetch failure, a single team's `persist_roster` failure --
    including the identity-layer `PlayerIdentityError`/`TeamIdentityError`
    it can raise via `player_identity`/`team_identity`, not just its own
    `RosterIngestionError` (Phase 3F-5 fix; confirmed by test to have
    previously crashed the whole run instead of isolating per-team) --
    a single game's rest/assembly/upsert failure,
    and -- since the 2026-08-18 row-isolation fix -- a single malformed
    or unrecognized-status Schedule row. `SportsDataIOScheduleAdapter.
    fetch_schedule` itself now logs and skips a bad row rather than
    raising for the whole batch (see that adapter's own docstring), so
    this worker never even sees the isolation happen -- it just receives
    a slate with that one game absent, exactly as if that row were never
    in the response at all. Also non-blocking (Phase 3F-4): the single
    batched internal-player_id resolution query -- a failure there never
    drops the fresh roster/depth-chart data already fetched for
    `daily_game_intelligence.players`, it only means no entry resolves
    an internal `player_id` this cycle (`player_id_resolution_failed`).

---

**MASTER REFRESH V2 (2026-09-15, HQ-authorized "CANONICAL SCHEDULE +
FINALIZATION HARDENING").** Three changes, all driven by the Week 2 gap
audit:

1. **Full-season persistence.** `filter_slate_window` used to run BEFORE
   `persist_schedule_entries`, so a run persisted only `[today, today + 7)`
   and silently discarded the rest of the already-fetched season. That is
   the exact mechanism that produced the Week 2 gap: the games were in the
   response and were thrown away before they could be written. V2 persists
   every entry the provider returned, and the window now governs only
   roster/DGI work. This costs no extra provider calls -- the Schedule
   endpoint always returned the full season -- and makes the schedule
   robust to missed runs, since any single successful run restores
   complete coverage.

2. **The 7-day window becomes an assertion, not a persistence boundary.**
   See `app.master_refresh.coverage`: after persistence, coverage across
   `[today, today + 7)` is checked and any shortfall is reported as a
   `partial` run. A gap is never repaired by inventing a game.

3. **Schedule and roster refresh are separable.** `run_schedule_refresh`
   (1 provider call, blocking, schedule integrity) and
   `run_roster_refresh` (up to 32 calls, entirely non-blocking) are now
   distinct entry points with distinct provider budgets.
   `run_master_refresh` still runs both in order, so no existing caller
   changes behavior -- but the daily path no longer has to carry the
   roster-call explosion. There was never a real dependency between them:
   schedule persistence already completed before any roster call, and a
   roster failure already never blocked canonical game identity.

**Pause gate (`MASTER_REFRESH_ENABLED`).** Checked as the first statement
of every entry point below, before any provider OR Supabase call. Per the
authorizing directive this gate is **explicit-opt-in**: only a
case-insensitive `"true"` enables the refresh, so both `false` AND unset
mean paused. That is deliberately INVERTED from `MSF_POSTGAME_ENABLED`'s
unset-means-enabled default, because the two flags fail safe in opposite
directions -- an accidentally removed `MSF_POSTGAME_ENABLED` should keep
ingestion running, whereas an accidentally removed
`MASTER_REFRESH_ENABLED` must never be able to start spending
SportsDataIO calls on its own. A paused run makes zero calls of any kind,
logs one clearly-labelled line, and returns `status="paused"` so its
caller exits 0 -- a clean no-op deployment, replacing today's daily
CRASHED deployment from the invalid-`CRON_DISPATCH_TARGET` sentinel.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.base import RosterAdapter, ScheduleAdapter
from app.adapters.cache import CacheBackend, CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, RosterEntry, ScheduleEntry
from app.adapters.providers.sportsdataio import SportsDataIORosterAdapter, SportsDataIOScheduleAdapter
from app.master_refresh.coverage import CoverageAssertion, assert_rolling_coverage
from app.master_refresh.game_refresh import refresh_daily_game_intelligence_for_game
from app.master_refresh.slate import WINDOW_DAYS, filter_slate_window
from app.persistence.daily_game_intelligence import DailyGameIntelligenceError
from app.persistence.games import GamesQueryError, list_games_in_window
from app.persistence.master_refresh_runs import complete_master_refresh_run, start_master_refresh_run
from app.persistence.player_identity import PlayerIdentityError, resolve_player_ids
from app.persistence.roster_ingestion import RosterIngestionError, persist_roster
from app.persistence.schedule import PersistenceError, persist_schedule_entries
from app.persistence.seasons import SeasonResolutionError, fetch_current_season_string
from app.persistence.team_identity import TeamIdentityError

_logger = logging.getLogger(__name__)

_SCHEDULE_TTL_SECONDS = 86400
_ROSTER_TTL_SECONDS = 86400
_ROSTER_PROVIDER_NAME = "sportsdataio"

#: Explicit-opt-in pause gate -- see the module docstring for why this is
#: inverted relative to `MSF_POSTGAME_ENABLED`.
MASTER_REFRESH_ENABLED_ENV = "MASTER_REFRESH_ENABLED"


def master_refresh_enabled() -> bool:
    """`True` only when `MASTER_REFRESH_ENABLED` is a case-insensitive
    `"true"`. Unset, empty, `"false"`, or any other value means paused.

    Deliberately strict rather than "anything that isn't false": this gate
    guards paid SportsDataIO calls, so the only state that may authorize spend
    is an explicit, unambiguous opt-in. A typo, a half-applied config change, or
    a deleted variable all fail closed."""
    return os.environ.get(MASTER_REFRESH_ENABLED_ENV, "").strip().lower() == "true"


def _paused_result() -> MasterRefreshResult:
    _logger.warning(
        "master_refresh PAUSED: %s is not 'true' -- zero provider calls, zero Supabase "
        "calls, clean no-op exit. This is an intentional cost pause, not a failure.",
        MASTER_REFRESH_ENABLED_ENV,
    )
    return MasterRefreshResult(status="paused", paused=True)


@dataclass
class MasterRefreshResult:
    status: str  # "success" | "partial" | "failed" | "paused"
    season_string: str | None = None
    #: Games in the rolling 7-day window -- unchanged meaning. V2 persists the
    #: full season, so this is no longer the same as what was written; see
    #: `schedule_entries_persisted` for that.
    games_in_slate: int = 0
    games_created: int = 0
    games_updated: int = 0
    #: V2: every entry the provider returned, i.e. what persistence actually
    #: covered -- the full season, not the 7-day slice.
    schedule_entries_persisted: int = 0
    #: V2: rolling 7-day coverage assertion (zero extra calls). `None` when the
    #: run never got far enough to assert anything -- never silently "passed".
    coverage: CoverageAssertion | None = None
    coverage_gaps: list[str] = field(default_factory=list)
    #: True only for an intentional `MASTER_REFRESH_ENABLED` pause.
    paused: bool = False
    roster_failures: list[str] = field(default_factory=list)
    roster_ingestion_failures: list[str] = field(default_factory=list)
    player_id_resolution_failed: bool = False
    daily_game_intelligence_written: int = 0
    daily_game_intelligence_failures: list[str] = field(default_factory=list)
    error: str | None = None
    #: Milestone 4.9 -- the `master_refresh_runs.id` this execution wrote
    #: to. `None` only if the run couldn't even be started (a
    #: `MasterRefreshRunsError` at the very first step, before any other
    #: work begins) -- every other exit path, including every existing
    #: "failed" branch above, still has a real run_id to finalize.
    run_id: str | None = None


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def run_master_refresh(
    *,
    supabase_client: httpx.AsyncClient,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    cache_backend: CacheBackend | None = None,
    today: date | None = None,
    now: datetime | None = None,
    league_code: str = "nfl",
    schedule_adapter: ScheduleAdapter | None = None,
    roster_adapter: RosterAdapter | None = None,
) -> MasterRefreshResult:
    """Milestone 4.9: creates a durable `master_refresh_runs` row BEFORE
    any crash-prone work begins, delegates to `_execute_master_refresh`
    (the unchanged Phase 3E-2/3F body -- every existing failure-isolation
    behavior, return path, and status derivation is untouched), then
    finalizes that same row with the actual outcome exactly once. A
    `MasterRefreshRunsError` starting the run is NOT caught here -- a
    refresh that can't even establish its own durable marker should fail
    loudly at the entry point, not proceed and silently produce
    unattributable work.

    `now` (injectable, defaults to real wall-clock only when omitted)
    stamps `completed_at` -- mirrors every worker's own established
    `now = now or datetime.now(timezone.utc)` seam (Odds/Injury/Weather/
    News/Player Props/Postgame/Pregame Workers all already follow this
    pattern) so Demo Mode's virtual clock can drive this timestamp too,
    exactly as it already drives `today`.

    **V2 (2026-09-15):** gated on `MASTER_REFRESH_ENABLED` as the very first
    statement -- before `start_master_refresh_run`, so a paused run does not
    even create a `master_refresh_runs` row for work it will never do. Still
    runs schedule then roster in one call, exactly as before; the two are now
    separately invocable (`run_schedule_refresh`/`run_roster_refresh`) for
    callers that want the 1-call daily path without the 32-call roster path."""
    if not master_refresh_enabled():
        return _paused_result()

    headers = _auth_headers()
    now = now or datetime.now(timezone.utc)
    run_id = await start_master_refresh_run(supabase_client, headers)
    result = await _execute_master_refresh(
        supabase_client=supabase_client,
        sportsdataio_client=sportsdataio_client,
        sportsdataio_api_key=sportsdataio_api_key,
        cache_backend=cache_backend,
        today=today,
        league_code=league_code,
        schedule_adapter=schedule_adapter,
        roster_adapter=roster_adapter,
    )
    result.run_id = run_id
    await complete_master_refresh_run(
        supabase_client,
        headers,
        run_id=run_id,
        status=result.status,
        season_string=result.season_string,
        games_in_slate=result.games_in_slate,
        completed_at_iso=now.isoformat(),
    )
    return result


async def _execute_master_refresh(
    *,
    supabase_client: httpx.AsyncClient,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    cache_backend: CacheBackend | None = None,
    today: date | None = None,
    league_code: str = "nfl",
    schedule_adapter: ScheduleAdapter | None = None,
    roster_adapter: RosterAdapter | None = None,
    skip_rosters: bool = False,
) -> MasterRefreshResult:
    """`schedule_adapter`/`roster_adapter` (dependency-injection seam, not
    Demo-specific): when supplied, used instead of constructing
    `SportsDataIOScheduleAdapter`/`SportsDataIORosterAdapter`. `None` (the
    default, for both) preserves today's real-provider construction and
    behavior unchanged for every existing caller.

    `skip_rosters` (V2, 2026-09-15) returns after the schedule phase and its
    coverage assertion, without making a single roster call. Defaults to
    `False`, so `run_master_refresh` behaves exactly as it always has."""
    headers = _auth_headers()
    cache_backend = cache_backend or InMemoryCacheBackend()
    today = today or datetime.now(timezone.utc).date()

    # Steps 1-2: resolve season, fetch Schedule -- BLOCKING.
    try:
        season_string = await fetch_current_season_string(
            supabase_client, headers, league_code=league_code, today=today
        )
    except SeasonResolutionError as exc:
        return MasterRefreshResult(status="failed", error=f"season resolution failed: {exc}")

    schedule_adapter = schedule_adapter or SportsDataIOScheduleAdapter(
        client=sportsdataio_client, api_key=sportsdataio_api_key
    )
    schedule_caching = CachingAdapter(schedule_adapter, cache_backend, ttl_seconds=_SCHEDULE_TTL_SECONDS)
    try:
        schedule_response: AdapterResponse[list[ScheduleEntry]] = await schedule_caching.call(
            "fetch_schedule", season_string, response_model=AdapterResponse[list[ScheduleEntry]]
        )
    except ProviderError as exc:
        return MasterRefreshResult(
            status="failed", season_string=season_string, error=f"Schedule fetch failed: {exc}"
        )

    # Step 3 (V2, 2026-09-15): the window no longer filters what gets
    # PERSISTED -- every entry the provider returned is written. The window
    # still defines the slate that roster/DGI work operates on, and is now
    # additionally asserted for completeness after persistence. See this
    # module's V2 note and app.master_refresh.coverage.
    season_entries = schedule_response.value
    slate_entries = filter_slate_window(season_entries, today=today)

    if not season_entries:
        return MasterRefreshResult(
            status="success", season_string=season_string, games_in_slate=0, games_created=0, games_updated=0
        )

    # Step 4: persist Schedule -- BLOCKING (strict: a persistence failure
    # fails the whole batch, per Decision 5 -- nothing already-persisted
    # is deleted or modified on this path, so prior data is untouched).
    # V2: the FULL season, so one successful run restores complete coverage
    # and a missed run can no longer permanently lose a week.
    try:
        games_created, games_updated = await persist_schedule_entries(
            AdapterResponse(value=season_entries, source=schedule_response.source)
        )
    except PersistenceError as exc:
        return MasterRefreshResult(
            status="failed",
            season_string=season_string,
            games_in_slate=len(slate_entries),
            schedule_entries_persisted=0,
            error=f"Schedule persistence failed: {exc}",
        )

    # Read back the rolling window -- gives us internal game_id plus whatever
    # season_type/week/status the persistence step just wrote, and doubles as
    # the "actual" side of the coverage assertion. Bounded by the window rather
    # than the season: roster/DGI work is windowed, and reading back 300+ rows
    # to assemble intelligence for games weeks away would be wasted work.
    try:
        games = await list_games_in_window(
            supabase_client, headers, start=today, end=today + timedelta(days=WINDOW_DAYS)
        )
    except GamesQueryError as exc:
        return MasterRefreshResult(
            status="failed",
            season_string=season_string,
            games_in_slate=len(slate_entries),
            schedule_entries_persisted=len(season_entries),
            games_created=games_created,
            games_updated=games_updated,
            error=f"failed to read back persisted slate: {exc}",
        )

    # Step 4b (V2): rolling 7-day coverage assertion. Zero additional calls --
    # both inputs are already in hand. Reported, never repaired.
    coverage = assert_rolling_coverage(season_entries, games, today=today)
    coverage_gaps = [gap.describe() for gap in coverage.gaps]
    if coverage_gaps:
        _logger.warning(
            "master_refresh coverage gap across [%s, +%dd): %s",
            today.isoformat(),
            WINDOW_DAYS,
            "; ".join(coverage_gaps),
        )

    if skip_rosters:
        # V2: the schedule-only daily path. Everything above costs exactly ONE
        # SportsDataIO call; everything below costs up to 32. Stopping here is
        # the whole point of the split -- see this module's V2 note 3.
        return MasterRefreshResult(
            status="partial" if coverage_gaps else "success",
            season_string=season_string,
            games_in_slate=len(slate_entries),
            schedule_entries_persisted=len(season_entries),
            coverage=coverage,
            coverage_gaps=coverage_gaps,
            games_created=games_created,
            games_updated=games_updated,
        )

    roster_phase = await _execute_roster_phase(
        supabase_client=supabase_client,
        sportsdataio_client=sportsdataio_client,
        sportsdataio_api_key=sportsdataio_api_key,
        cache_backend=cache_backend,
        games=games,
        roster_adapter=roster_adapter,
    )

    status = "partial" if (
        roster_phase.roster_failures
        or roster_phase.roster_ingestion_failures
        or roster_phase.player_id_resolution_failed
        or roster_phase.daily_game_intelligence_failures
        # V2: a coverage shortfall is a loud condition, not a silent one --
        # the run did real work, but the week is not fully reconciled.
        or coverage_gaps
    ) else "success"

    return MasterRefreshResult(
        status=status,
        season_string=season_string,
        games_in_slate=len(slate_entries),
        schedule_entries_persisted=len(season_entries),
        coverage=coverage,
        coverage_gaps=coverage_gaps,
        games_created=games_created,
        games_updated=games_updated,
        roster_failures=roster_phase.roster_failures,
        roster_ingestion_failures=roster_phase.roster_ingestion_failures,
        player_id_resolution_failed=roster_phase.player_id_resolution_failed,
        daily_game_intelligence_written=roster_phase.daily_game_intelligence_written,
        daily_game_intelligence_failures=roster_phase.daily_game_intelligence_failures,
    )


@dataclass
class _RosterPhaseOutcome:
    """Steps 5-8's own results, so `_execute_roster_phase` can be reused by both
    the combined refresh and the standalone `run_roster_refresh` without either
    one re-implementing the per-team failure isolation."""

    roster_failures: list[str] = field(default_factory=list)
    roster_ingestion_failures: list[str] = field(default_factory=list)
    player_id_resolution_failed: bool = False
    daily_game_intelligence_written: int = 0
    daily_game_intelligence_failures: list[str] = field(default_factory=list)


async def _execute_roster_phase(
    *,
    supabase_client: httpx.AsyncClient,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    cache_backend: CacheBackend,
    games: list[dict],
    roster_adapter: RosterAdapter | None = None,
) -> _RosterPhaseOutcome:
    """Steps 5-8, extracted verbatim in V2 (2026-09-15) so the expensive
    roster path can be scheduled independently of the 1-call schedule path.

    Behavior is unchanged from the inline version: every failure here is
    NON-BLOCKING and isolated exactly as before (per-team fetch, per-team
    ingestion, batched player-id resolution, per-game DGI assembly)."""
    headers = _auth_headers()

    # Step 5: roster fetch, per-team isolated -- NON-BLOCKING.
    teams_in_slate = sorted({g["home_team"] for g in games} | {g["away_team"] for g in games})
    roster_adapter = roster_adapter or SportsDataIORosterAdapter(
        client=sportsdataio_client, api_key=sportsdataio_api_key, cache_backend=cache_backend
    )
    roster_caching = CachingAdapter(roster_adapter, cache_backend, ttl_seconds=_ROSTER_TTL_SECONDS)
    rosters: dict[str, list[RosterEntry] | None] = {}
    roster_failures: list[str] = []
    roster_ingestion_failures: list[str] = []
    for team in teams_in_slate:
        try:
            roster_response: AdapterResponse[list[RosterEntry]] = await roster_caching.call(
                "fetch_roster", team, response_model=AdapterResponse[list[RosterEntry]]
            )
            rosters[team] = roster_response.value
        except ProviderError:
            roster_failures.append(team)
            rosters[team] = None
            continue

        # Phase 3F-1: durable roster ingestion (players/player_provider_ids/
        # roster_memberships/depth_chart_snapshots), isolated per team like
        # the fetch above -- one team's persistence failure never blocks
        # another's, and never blocks daily_game_intelligence assembly
        # below (which still reads `rosters` as fetched, unchanged).
        #
        # Phase 3F-5 fix: `persist_roster` calls into `player_identity`/
        # `team_identity`, which can raise `PlayerIdentityError`/
        # `TeamIdentityError` -- distinct exception types from
        # `RosterIngestionError`, previously NOT caught here (a real,
        # confirmed-by-test gap found during 3F-4 and reported, not fixed,
        # at the time). Both are the expected identity-layer failure
        # classes for this exact call, caught at this exact per-team
        # boundary, same as RosterIngestionError always was -- no generic
        # `except Exception`, so a genuine programming error still
        # propagates and fails loudly rather than being silently isolated.
        try:
            await persist_roster(roster_response)
        except (RosterIngestionError, PlayerIdentityError, TeamIdentityError) as exc:
            roster_ingestion_failures.append(f"{team}: {exc}")

    # Phase 3F-4: batched internal player_id resolution -- one query for
    # the whole slate (not per-team, not per-player -- avoids N+1), run
    # after every team's persist_roster attempt above so a brand-new
    # player's just-created mapping resolves this same cycle. Reads
    # whatever player_provider_ids mappings actually exist at this
    # moment: a player never durably ingested, or whose team's
    # persist_roster call above failed before reaching them, is simply
    # absent -- daily_game_intelligence.players still shows their fresh
    # roster data (below), just with player_id left null, never
    # fabricated. A failure of this lookup itself is NON-BLOCKING and
    # isolated the same way -- it never drops the fresh roster/depth-chart
    # data already fetched, it only means no entry resolves this cycle.
    all_provider_player_ids = sorted(
        {entry.player_external_id for roster in rosters.values() if roster is not None for entry in roster}
    )
    player_id_resolution_failed = False
    try:
        player_ids = await resolve_player_ids(
            supabase_client, headers, provider_name=_ROSTER_PROVIDER_NAME, provider_player_ids=all_provider_player_ids
        )
    except PlayerIdentityError:
        player_ids = {}
        player_id_resolution_failed = True

    # Steps 6-8: per-game daily_game_intelligence refresh, each isolated so
    # one game's failure never blocks another's. Delegates to
    # app.master_refresh.game_refresh (extracted Phase 3E-8 so Pregame
    # Worker can reuse the identical assembly behavior for a single
    # targeted game -- see that module's docstring).
    dgi_written = 0
    dgi_failures: list[str] = []
    for game in games:
        game_id = game["id"]
        try:
            await refresh_daily_game_intelligence_for_game(
                supabase_client, headers, game, rosters=rosters, player_ids=player_ids
            )
            dgi_written += 1
        except (GamesQueryError, DailyGameIntelligenceError) as exc:
            dgi_failures.append(f"{game_id}: {exc}")

    return _RosterPhaseOutcome(
        roster_failures=roster_failures,
        roster_ingestion_failures=roster_ingestion_failures,
        player_id_resolution_failed=player_id_resolution_failed,
        daily_game_intelligence_written=dgi_written,
        daily_game_intelligence_failures=dgi_failures,
    )


async def run_schedule_refresh(
    *,
    supabase_client: httpx.AsyncClient,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    cache_backend: CacheBackend | None = None,
    today: date | None = None,
    now: datetime | None = None,
    league_code: str = "nfl",
    schedule_adapter: ScheduleAdapter | None = None,
) -> MasterRefreshResult:
    """V2's cheap daily path: canonical schedule integrity only.

    **Provider cost: exactly ONE SportsDataIO Schedule call** (24h-cached),
    which returns the full season -- so this both persists every game and
    asserts rolling 7-day coverage for the price of the single call the old
    combined refresh already spent on schedule alone. No roster call is made
    from this path at any point.

    Same pause gate, same durable `master_refresh_runs` row, same blocking/
    non-blocking semantics as `run_master_refresh` -- this is that function
    with steps 5-8 not run, not a second implementation of steps 1-4."""
    if not master_refresh_enabled():
        return _paused_result()

    headers = _auth_headers()
    now = now or datetime.now(timezone.utc)
    run_id = await start_master_refresh_run(supabase_client, headers)
    result = await _execute_master_refresh(
        supabase_client=supabase_client,
        sportsdataio_client=sportsdataio_client,
        sportsdataio_api_key=sportsdataio_api_key,
        cache_backend=cache_backend,
        today=today,
        league_code=league_code,
        schedule_adapter=schedule_adapter,
        skip_rosters=True,
    )
    result.run_id = run_id
    await complete_master_refresh_run(
        supabase_client,
        headers,
        run_id=run_id,
        status=result.status,
        season_string=result.season_string,
        games_in_slate=result.games_in_slate,
        completed_at_iso=now.isoformat(),
    )
    return result


async def run_roster_refresh(
    *,
    supabase_client: httpx.AsyncClient,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    cache_backend: CacheBackend | None = None,
    today: date | None = None,
    roster_adapter: RosterAdapter | None = None,
) -> MasterRefreshResult:
    """V2's expensive path: rosters, depth charts, and `daily_game_intelligence`
    player data for the teams in the rolling window.

    **Provider cost: up to 32 SportsDataIO roster calls** -- one per team in the
    slate -- which is exactly why it is separable and belongs on a slower
    cadence than the daily schedule refresh.

    Makes **zero Schedule calls**: it reads the canonical slate back from the
    database rather than re-fetching it, so running it never re-spends the
    schedule call and never re-persists a game. Every failure here stays
    non-blocking and isolated, unchanged from the combined refresh.

    A read failure on the slate is the one blocking condition -- without a slate
    there is nothing to fetch rosters *for*, and proceeding would mean guessing
    which teams are playing."""
    if not master_refresh_enabled():
        return _paused_result()

    headers = _auth_headers()
    cache_backend = cache_backend or InMemoryCacheBackend()
    today = today or datetime.now(timezone.utc).date()

    try:
        games = await list_games_in_window(
            supabase_client, headers, start=today, end=today + timedelta(days=WINDOW_DAYS)
        )
    except GamesQueryError as exc:
        return MasterRefreshResult(status="failed", error=f"failed to read canonical slate: {exc}")

    if not games:
        return MasterRefreshResult(status="success", games_in_slate=0)

    outcome = await _execute_roster_phase(
        supabase_client=supabase_client,
        sportsdataio_client=sportsdataio_client,
        sportsdataio_api_key=sportsdataio_api_key,
        cache_backend=cache_backend,
        games=games,
        roster_adapter=roster_adapter,
    )

    status = "partial" if (
        outcome.roster_failures
        or outcome.roster_ingestion_failures
        or outcome.player_id_resolution_failed
        or outcome.daily_game_intelligence_failures
    ) else "success"

    return MasterRefreshResult(
        status=status,
        games_in_slate=len(games),
        roster_failures=outcome.roster_failures,
        roster_ingestion_failures=outcome.roster_ingestion_failures,
        player_id_resolution_failed=outcome.player_id_resolution_failed,
        daily_game_intelligence_written=outcome.daily_game_intelligence_written,
        daily_game_intelligence_failures=outcome.daily_game_intelligence_failures,
    )
