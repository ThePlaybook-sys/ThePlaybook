"""Injury Worker orchestration (Phase 3E-5).

**Cadence:** driven entirely by `app.workers.windows.classify_injury_window`/
`should_poll_injuries` -- see that module's own docstring for the full
day-of-week-plus-kickoff-proximity design and its CONFIRMED/ASSUMED
provenance breakdown. This worker never computes a cadence tier itself.

**Structurally different from Odds/Player Props Worker, not a design
preference:** `SportsDataIOInjuryAdapter.fetch_injuries` is one bulk call
per (season, week) returning every team's injuries at once -- there is no
per-game endpoint to call, unlike Odds/Player Props. Consequently:

- There is exactly **one** "last polled" moment per worker cycle, not one
  per game -- `should_poll_injuries`' `last_polled_at` parameter is a
  single `datetime | None`, not a dict keyed by game id.
- The polling decision is driven by the single soonest-kickoff active
  (non-STOPPED) game in the 7-day candidate window (the "driver game") --
  the most time-sensitive game governs both whether this cycle polls at
  all and which cache TTL applies to that poll.
- Once a poll happens, every resolvable row in the response is persisted,
  not only rows belonging to the driver game -- Mac's explicit Decision 2
  (append-only, no dedup) makes this safe: writing an extra snapshot for a
  game that technically wasn't "due" on its own individual cadence is
  never wrong, only a slightly earlier-than-strictly-needed historical
  data point, which the append-only design treats as acceptable rather
  than harmful.

**Identity resolution -- the adapter's synchronous resolver-injection
contract, not a new pattern.** `SportsDataIOInjuryAdapter.fetch_injuries`
takes an injected `game_key_for(team, opponent, season, week) -> str |
None` callable that must be plain/synchronous (the same established
pattern as `WeatherAPIWeatherAdapter.location_for_game` -- confirmed by
direct inspection of the adapter's own type hint and existing tests, never
`async`). This means the worker must pre-resolve every in-scope game's own
SportsDataIO GameKey *before* calling `fetch_injuries`, from data already
in hand: every candidate game sharing the driver game's `week` is
reverse-resolved (game_provider_ids, provider_name="sportsdataio") in one
batched query, then indexed into a plain dict `game_key_for` closes over.
No second per-row DB round trip during the fetch itself, and no fuzzy
matching anywhere -- a (team, opponent, season, week) tuple either has a
resolved GameKey or it doesn't; the adapter already treats "doesn't" as an
expected skip (bye week, or the row's own malformed-ness), not a guess.

**Master Refresh boundary:** identical to Odds/Player Props Worker's --
this module is never called by Master Refresh and never calls it.
`daily_game_intelligence`'s `injuries` field already reads from
`injury_reports` via `app.persistence.snapshots.latest_injury_report`
(built in 3E-2, ahead of this worker existing) -- nothing here changes
that integration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.base import InjuryAdapter
from app.adapters.cache import CacheBackend, CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, InjuryReport
from app.adapters.providers.sportsdataio import SportsDataIOInjuryAdapter
from app.persistence.game_identity import GameIdentityError
from app.persistence.games import GamesQueryError, list_games_in_window
from app.persistence.injury_reports import PersistenceError, persist_injury_reports
from app.persistence.seasons import SeasonResolutionError, fetch_current_season_string
from app.workers.windows import (
    InjuryWindow,
    classify_injury_window,
    injury_ttl_seconds,
    should_poll_injuries,
)

_PROVIDER_NAME = "sportsdataio"

#: Same candidate-window convention as Odds/Player Props Worker -- an
#: independent worker-level scoping decision, not a reinterpretation of
#: Master Refresh's own canonical 7-day operating horizon.
_CANDIDATE_WINDOW_DAYS = 7


@dataclass
class InjuryWorkerResult:
    status: str  # "success" | "partial" | "failed"
    games_considered: int = 0
    active_games: int = 0
    polled: bool = False
    reports_persisted: int = 0
    failures: list[str] = field(default_factory=list)
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


async def _reverse_resolve_sportsdataio_ids(
    client: httpx.AsyncClient, headers: dict, *, game_ids: list[str]
) -> dict[str, str]:
    """Maps games.id -> sportsdataio provider_game_id (GameKey), for the
    given game_ids -- the reverse direction of
    `app.persistence.game_identity.resolve_game_ids`. A game with no
    sportsdataio mapping is simply absent from the result. Mirrors
    `app.workers.player_props_worker._reverse_resolve_the_odds_api_ids`
    exactly, scoped to the other provider -- same established pattern,
    not a new one.
    """
    if not game_ids:
        return {}
    response = await client.get(
        "/rest/v1/game_provider_ids",
        params={
            "provider_name": f"eq.{_PROVIDER_NAME}",
            "game_id": f"in.({','.join(game_ids)})",
            "select": "game_id,provider_game_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GameIdentityError(
            f"failed to reverse-resolve sportsdataio ids: {response.status_code} {response.text}"
        )
    return {row["game_id"]: row["provider_game_id"] for row in response.json()}


async def run_injury_worker(
    *,
    supabase_client: httpx.AsyncClient,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    cache_backend: CacheBackend | None = None,
    now: datetime | None = None,
    last_polled_at: datetime | None = None,
    target_game_ids: list[str] | None = None,
    injury_adapter: InjuryAdapter | None = None,
) -> InjuryWorkerResult:
    """Runs one Injury Worker cycle. Always returns an `InjuryWorkerResult`,
    never raises -- same finite-job shape as `run_master_refresh`/
    `run_odds_worker`/`run_player_props_worker`. `last_polled_at` is a
    single timestamp, not per-game -- see module docstring for why.

    `injury_adapter` (dependency-injection seam, not Demo-specific): when
    supplied, used instead of constructing `SportsDataIOInjuryAdapter` --
    the upstream `game_key_for`/season/week identity resolution below still
    runs (it's pure Supabase reads, not a provider call), it's simply
    unused by an injected adapter that doesn't need it. `None` (the
    default) preserves today's real-provider construction and behavior
    unchanged.

    `target_game_ids` (Phase 3E-8, Decision 3): when provided and one of
    the listed games is active (not yet kicked off), that game is forced
    to be this cycle's driver game, bypassing `should_poll_injuries`'s own
    cadence gating -- Pregame Worker's coordination hook, same spirit as
    the identically-named parameter on the per-game workers. Every
    resolvable row in the response is still persisted regardless (Decision
    2's existing append-only/no-dedup design already makes this safe), not
    only rows for the targeted game. `None` (the default) preserves normal
    driver-selection/cadence behavior unchanged.
    """
    headers = _auth_headers()
    cache_backend = cache_backend or InMemoryCacheBackend()
    now = now or datetime.now(timezone.utc)

    today: date = now.date()
    try:
        games = await list_games_in_window(
            supabase_client, headers, start=today, end=today + timedelta(days=_CANDIDATE_WINDOW_DAYS)
        )
    except GamesQueryError as exc:
        return InjuryWorkerResult(status="failed", error=f"failed to list candidate games: {exc}")

    if not games:
        return InjuryWorkerResult(status="success", games_considered=0)

    active_games = [
        g
        for g in games
        if classify_injury_window(now=now, kickoff=_parse_datetime(g["scheduled_start"]))
        is not InjuryWindow.STOPPED
    ]
    if not active_games:
        return InjuryWorkerResult(status="success", games_considered=len(games), active_games=0)

    target_set = set(target_game_ids) if target_game_ids is not None else None
    forced_driver = next((g for g in active_games if g["id"] in target_set), None) if target_set else None

    driver_game = forced_driver or min(active_games, key=lambda g: _parse_datetime(g["scheduled_start"]))
    driver_kickoff = _parse_datetime(driver_game["scheduled_start"])

    if forced_driver is None and not should_poll_injuries(
        now=now, kickoff=driver_kickoff, last_polled_at=last_polled_at
    ):
        return InjuryWorkerResult(
            status="success", games_considered=len(games), active_games=len(active_games), polled=False
        )

    week = driver_game["week"]
    if week is None:
        return InjuryWorkerResult(
            status="failed",
            games_considered=len(games),
            active_games=len(active_games),
            error=f"driver game {driver_game['id']} has no week set -- cannot resolve Injuries endpoint",
        )

    try:
        season = await fetch_current_season_string(supabase_client, headers, league_code="nfl", today=today)
    except SeasonResolutionError as exc:
        return InjuryWorkerResult(
            status="failed",
            games_considered=len(games),
            active_games=len(active_games),
            error=f"season resolution failed: {exc}",
        )

    # Every game sharing the driver game's own week -- the universe
    # game_key_for can resolve against without a second DB round trip
    # during the fetch itself. See module docstring.
    same_week_games = [g for g in games if g["week"] == week]
    try:
        provider_ids_by_game_id = await _reverse_resolve_sportsdataio_ids(
            supabase_client, headers, game_ids=[g["id"] for g in same_week_games]
        )
    except GameIdentityError as exc:
        return InjuryWorkerResult(
            status="failed",
            games_considered=len(games),
            active_games=len(active_games),
            error=f"game identity lookup failed: {exc}",
        )

    matchup_to_provider_id: dict[tuple[str, str, str, int], str] = {}
    for g in same_week_games:
        provider_id = provider_ids_by_game_id.get(g["id"])
        if provider_id is None:
            continue
        matchup_to_provider_id[(g["home_team"], g["away_team"], season, week)] = provider_id
        matchup_to_provider_id[(g["away_team"], g["home_team"], season, week)] = provider_id

    def game_key_for(team: str, opponent: str, season_arg: str, week_arg: int) -> str | None:
        return matchup_to_provider_id.get((team, opponent, season_arg, week_arg))

    injury_adapter = injury_adapter or SportsDataIOInjuryAdapter(
        client=sportsdataio_client,
        api_key=sportsdataio_api_key,
        current_season_week=lambda: (season, week),
        game_key_for=game_key_for,
    )
    window = classify_injury_window(now=now, kickoff=driver_kickoff)
    caching = CachingAdapter(injury_adapter, cache_backend, ttl_seconds=injury_ttl_seconds(window))

    try:
        response: AdapterResponse[list[InjuryReport]] = await caching.call(
            "fetch_injuries", response_model=AdapterResponse[list[InjuryReport]]
        )
    except ProviderError as exc:
        return InjuryWorkerResult(
            status="failed",
            games_considered=len(games),
            active_games=len(active_games),
            polled=True,
            error=f"injuries fetch failed: {exc}",
        )

    persisted = 0
    failures: list[str] = []
    if response.value:
        try:
            persisted = await persist_injury_reports(response)
        except PersistenceError as exc:
            failures.append(f"persistence failed: {exc}")

    status = "partial" if failures else "success"
    return InjuryWorkerResult(
        status=status,
        games_considered=len(games),
        active_games=len(active_games),
        polled=True,
        reports_persisted=persisted,
        failures=failures,
    )
