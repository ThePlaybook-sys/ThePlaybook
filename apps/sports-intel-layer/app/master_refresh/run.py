"""Master Refresh orchestration (Phase 3E-2).

Runs as a finite job -- `run_master_refresh()` always returns a
`MasterRefreshResult`, never raises, so a future thin entry point (CLI
script, Railway Cron Job -- neither built here per the stop condition)
can decide exit-code/alerting behavior from `result.status` without
needing its own try/except around this function. This is Decision 6's
"start -> execute -> report success/failure -> exit" shape.

**Failure isolation (Decision 5 + the approved failure-isolation table):**
  BLOCKING (aborts the whole run, `status="failed"`): season resolution
    failure, Schedule provider fetch failure, Schedule normalization
    failure (a malformed row -- `SportsDataIOScheduleAdapter.fetch_schedule`
    already raises on this, no new code needed), Schedule persistence
    failure. Nothing past this point runs; nothing already-persisted is
    touched, modified, or deleted.
  NON-BLOCKING (isolated, collected, run continues): a single team's
    roster fetch failure, a single game's rest/assembly/upsert failure.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.cache import CacheBackend, CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, RosterEntry, ScheduleEntry
from app.adapters.providers.sportsdataio import SportsDataIORosterAdapter, SportsDataIOScheduleAdapter
from app.master_refresh.rest import compute_rest
from app.master_refresh.slate import filter_slate_window
from app.persistence.daily_game_intelligence import (
    DailyGameIntelligenceError,
    build_payload,
    read_existing_news,
    upsert_daily_game_intelligence,
)
from app.persistence.games import GamesQueryError, find_previous_final_game, list_games_in_window
from app.persistence.schedule import PersistenceError, persist_schedule_entries
from app.persistence.seasons import SeasonResolutionError, fetch_current_season_string
from app.persistence.snapshots import latest_injury_report, latest_odds_line, latest_prop_line, latest_weather_snapshot

_SCHEDULE_TTL_SECONDS = 86400
_ROSTER_TTL_SECONDS = 86400


@dataclass
class MasterRefreshResult:
    status: str  # "success" | "partial" | "failed"
    season_string: str | None = None
    games_in_slate: int = 0
    games_created: int = 0
    games_updated: int = 0
    roster_failures: list[str] = field(default_factory=list)
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


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


async def run_master_refresh(
    *,
    supabase_client: httpx.AsyncClient,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    cache_backend: CacheBackend | None = None,
    today: date | None = None,
    league_code: str = "nfl",
) -> MasterRefreshResult:
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

    schedule_adapter = SportsDataIOScheduleAdapter(client=sportsdataio_client, api_key=sportsdataio_api_key)
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
    roster_adapter = SportsDataIORosterAdapter(
        client=sportsdataio_client, api_key=sportsdataio_api_key, cache_backend=cache_backend
    )
    roster_caching = CachingAdapter(roster_adapter, cache_backend, ttl_seconds=_ROSTER_TTL_SECONDS)
    rosters: dict[str, list[RosterEntry] | None] = {}
    roster_failures: list[str] = []
    for team in teams_in_slate:
        try:
            roster_response: AdapterResponse[list[RosterEntry]] = await roster_caching.call(
                "fetch_roster", team, response_model=AdapterResponse[list[RosterEntry]]
            )
            rosters[team] = roster_response.value
        except ProviderError:
            roster_failures.append(team)
            rosters[team] = None

    # Steps 6-8: per-game rest computation, currently-available
    # intelligence read, and daily_game_intelligence assembly/upsert --
    # each isolated so one game's failure never blocks another's.
    dgi_written = 0
    dgi_failures: list[str] = []
    for game in games:
        game_id = game["id"]
        try:
            scheduled_start = _parse_datetime(game["scheduled_start"])

            home_previous = await find_previous_final_game(
                supabase_client, headers, team=game["home_team"], before=scheduled_start
            )
            away_previous = await find_previous_final_game(
                supabase_client, headers, team=game["away_team"], before=scheduled_start
            )
            rest = {
                "home": compute_rest(current_scheduled_start=scheduled_start, previous_game=home_previous),
                "away": compute_rest(current_scheduled_start=scheduled_start, previous_game=away_previous),
            }

            odds_row = await latest_odds_line(supabase_client, headers, game_id=game_id)
            props_row = await latest_prop_line(supabase_client, headers, game_id=game_id)
            injury_row = await latest_injury_report(supabase_client, headers, game_id=game_id)
            weather_row = await latest_weather_snapshot(supabase_client, headers, game_id=game_id)
            existing_news = await read_existing_news(supabase_client, headers, game_id=game_id)

            home_roster = rosters.get(game["home_team"])
            away_roster = rosters.get(game["away_team"])
            players = None
            if home_roster is not None or away_roster is not None:
                players = {
                    "home": [r.model_dump(mode="json") for r in home_roster] if home_roster is not None else None,
                    "away": [r.model_dump(mode="json") for r in away_roster] if away_roster is not None else None,
                }

            payload = build_payload(
                game_id=game_id,
                teams={"home": game["home_team"], "away": game["away_team"]},
                players=players,
                odds_row=odds_row,
                props_row=props_row,
                injury_row=injury_row,
                weather_row=weather_row,
                existing_news=existing_news,
                rest=rest,
                stadium={"name": game["stadium"]} if game.get("stadium") else None,
            )
            await upsert_daily_game_intelligence(supabase_client, headers, payload)
            dgi_written += 1
        except (GamesQueryError, DailyGameIntelligenceError) as exc:
            dgi_failures.append(f"{game_id}: {exc}")

    status = "partial" if (roster_failures or dgi_failures) else "success"

    return MasterRefreshResult(
        status=status,
        season_string=season_string,
        games_in_slate=len(slate_entries),
        games_created=games_created,
        games_updated=games_updated,
        roster_failures=roster_failures,
        daily_game_intelligence_written=dgi_written,
        daily_game_intelligence_failures=dgi_failures,
    )
