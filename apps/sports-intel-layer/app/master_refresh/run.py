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
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.base import RosterAdapter, ScheduleAdapter
from app.adapters.cache import CacheBackend, CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, RosterEntry, ScheduleEntry
from app.adapters.providers.sportsdataio import SportsDataIORosterAdapter, SportsDataIOScheduleAdapter
from app.master_refresh.game_refresh import refresh_daily_game_intelligence_for_game
from app.master_refresh.slate import filter_slate_window
from app.persistence.daily_game_intelligence import DailyGameIntelligenceError
from app.persistence.games import GamesQueryError, list_games_in_window
from app.persistence.player_identity import PlayerIdentityError, resolve_player_ids
from app.persistence.roster_ingestion import RosterIngestionError, persist_roster
from app.persistence.schedule import PersistenceError, persist_schedule_entries
from app.persistence.seasons import SeasonResolutionError, fetch_current_season_string
from app.persistence.team_identity import TeamIdentityError

_SCHEDULE_TTL_SECONDS = 86400
_ROSTER_TTL_SECONDS = 86400
_ROSTER_PROVIDER_NAME = "sportsdataio"


@dataclass
class MasterRefreshResult:
    status: str  # "success" | "partial" | "failed"
    season_string: str | None = None
    games_in_slate: int = 0
    games_created: int = 0
    games_updated: int = 0
    roster_failures: list[str] = field(default_factory=list)
    roster_ingestion_failures: list[str] = field(default_factory=list)
    player_id_resolution_failed: bool = False
    daily_game_intelligence_written: int = 0
    daily_game_intelligence_failures: list[str] = field(default_factory=list)
    error: str | None = None


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
    league_code: str = "nfl",
    schedule_adapter: ScheduleAdapter | None = None,
    roster_adapter: RosterAdapter | None = None,
) -> MasterRefreshResult:
    """`schedule_adapter`/`roster_adapter` (dependency-injection seam, not
    Demo-specific): when supplied, used instead of constructing
    `SportsDataIOScheduleAdapter`/`SportsDataIORosterAdapter`. `None` (the
    default, for both) preserves today's real-provider construction and
    behavior unchanged for every existing caller."""
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

    # Step 3 (numbering per Mac's approved scope): filter to the refresh
    # window before persisting -- see app.master_refresh.slate for why
    # this is a rolling window, not a literal single day.
    slate_entries = filter_slate_window(schedule_response.value, today=today)

    if not slate_entries:
        return MasterRefreshResult(
            status="success", season_string=season_string, games_in_slate=0, games_created=0, games_updated=0
        )

    # Step 4: persist Schedule -- BLOCKING (strict: a persistence failure
    # fails the whole batch, per Decision 5 -- nothing already-persisted
    # is deleted or modified on this path, so prior data is untouched).
    try:
        games_created, games_updated = await persist_schedule_entries(
            AdapterResponse(value=slate_entries, source=schedule_response.source)
        )
    except PersistenceError as exc:
        return MasterRefreshResult(
            status="failed",
            season_string=season_string,
            games_in_slate=len(slate_entries),
            error=f"Schedule persistence failed: {exc}",
        )

    # Read back the persisted slate -- gives us internal game_id plus
    # whatever season_type/week/status the persistence step just wrote.
    window_end = max(e.scheduled_start.date() for e in slate_entries)
    try:
        games = await list_games_in_window(supabase_client, headers, start=today, end=window_end + timedelta(days=1))
    except GamesQueryError as exc:
        return MasterRefreshResult(
            status="failed",
            season_string=season_string,
            games_in_slate=len(slate_entries),
            games_created=games_created,
            games_updated=games_updated,
            error=f"failed to read back persisted slate: {exc}",
        )

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

    status = "partial" if (
        roster_failures or roster_ingestion_failures or player_id_resolution_failed or dgi_failures
    ) else "success"

    return MasterRefreshResult(
        status=status,
        season_string=season_string,
        games_in_slate=len(slate_entries),
        games_created=games_created,
        games_updated=games_updated,
        roster_failures=roster_failures,
        roster_ingestion_failures=roster_ingestion_failures,
        player_id_resolution_failed=player_id_resolution_failed,
        daily_game_intelligence_written=dgi_written,
        daily_game_intelligence_failures=dgi_failures,
    )
