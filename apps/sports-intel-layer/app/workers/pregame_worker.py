"""Pregame Worker orchestration (Phase 3E-8).

Volume 2 §8's own cadence row: "Triggered, T-minus kickoff | Final refresh
of all critical data immediately before a game starts -- catches
last-minute inactive lists and line moves the scheduled cadences might
miss by a few minutes." No numeric T-minus value is stated anywhere in
this row -- Mac's Decision 3 (3E-8, 2026-08-18) resolved this explicitly:
reuse the already-CONFIRMED 5-minute pre-kickoff boundary from Odds/Player
Props' own window architecture (`Window.RAMP_5M`'s lower boundary,
`app.workers.windows`) rather than inventing a new timing concept.

**A coordination/orchestration worker, not a new provider category (Mac's
explicit instruction).** This module fetches nothing itself and owns no
adapter. It forces one more, unconditional pass of the four already-
existing per-game/bulk workers -- Odds, Player Props, Injury, Weather --
for exactly the one game entering its final 5-minute window, via each
worker's own `target_game_ids` parameter (Phase 3E-8 widening, see each
worker's own docstring). This is "force the existing relevant data
refresh paths rather than duplicate them," applied literally: zero new
adapter code, zero new persistence code for odds/props/injuries/weather.

**News Worker is deliberately excluded, not overlooked.** `app.workers.
news_worker`'s own module docstring already establishes that a team's
news relevance doesn't expire at that team's own kickoff, and the worker
deliberately never stops polling a team at kickoff the way Weather/Odds/
Player Props do -- there is no "last-minute value" specific to the
T-minus-5 moment for News the way there is for line moves and inactive
lists. An extra News fetch at T-minus-5 would not serve this row's stated
purpose ("catches last-minute... line moves... inactive lists"); evaluated
and excluded, not missed (Decision 3's explicit instruction: "News Worker
where still relevant").

**Trigger, once per game.** Fires when a game's kickoff-proximity
classification (`app.workers.windows.classify_window`) is `Window.
RAMP_5M` -- the same tier Odds/Player Props already ramp into at T-minus-5
-- and this game is not already in `triggered_game_ids`. That set is
caller-supplied (mirroring every other worker's `last_polled_at`
convention: ephemeral, since no worker-run-history persistence layer
exists yet in this codebase for any worker); omitting a game from it means
"not yet triggered," which is always safe -- it can only cause an extra
pregame pass, never a missed one, the same safety property every other
worker's default already relies on.

**Immediately followed by a targeted daily_game_intelligence refresh
(Decision 4).** After the four coordinated workers return, this worker
calls `app.master_refresh.game_refresh.
refresh_daily_game_intelligence_for_game` for the triggering game only --
reusing Master Refresh's own per-game assembly function unchanged
(extracted from `run_master_refresh` for exactly this reuse), never
waiting for the next 6 AM Master Refresh run. This never touches
`players`/`rest`/`stadium` beyond what that function already does (reads
existing `players` back rather than refetching rosters -- see that
function's own docstring for why Roster fetching is out of scope here).

**Failure isolation.** One coordinated category's failure (e.g. Injury
Worker's provider call failing) never blocks another's -- each of the
four calls is isolated and collected, matching every other worker's
per-item isolation convention. The daily_game_intelligence refresh runs
regardless of upstream category failures (using whatever each category's
own already-persisted data currently holds, per that function's existing
read-back behavior), and is itself isolated too. One game's failures never
block another due game's own pregame pass.

**Master Refresh boundary:** identical in spirit to every other
specialized worker's -- this module is never called by Master Refresh.
Unlike the others, it *does* call `app.master_refresh.game_refresh`
directly (Decision 4's explicit instruction), but only the extracted,
already-existing per-game assembly function, never `run_master_refresh`
itself and never Master Refresh's own Schedule/roster-fetch steps.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.base import InjuryAdapter, OddsAdapter, PlayerPropsAdapter, WeatherAdapter
from app.adapters.cache import CacheBackend, InMemoryCacheBackend
from app.master_refresh.game_refresh import refresh_daily_game_intelligence_for_game
from app.persistence.daily_game_intelligence import DailyGameIntelligenceError
from app.persistence.games import GamesQueryError, list_games_in_window
from app.workers.injury_worker import run_injury_worker
from app.workers.odds_worker import run_odds_worker
from app.workers.player_props_worker import run_player_props_worker
from app.workers.weather_worker import run_weather_worker
from app.workers.windows import Window, classify_window

#: Same candidate-window convention as every other specialized worker.
_CANDIDATE_WINDOW_DAYS = 7


@dataclass
class PregameWorkerResult:
    status: str  # "success" | "partial" | "failed"
    games_considered: int = 0
    games_triggered: list[str] = field(default_factory=list)
    category_failures: list[str] = field(default_factory=list)
    daily_game_intelligence_refreshed: int = 0
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


def _collect(result, *, label: str, game_id: str, out: list[str]) -> None:
    if result.status == "failed":
        out.append(f"{game_id}: {label} failed: {result.error}")
    elif result.status == "partial":
        out.append(f"{game_id}: {label} partial: {result.failures}")


async def run_pregame_worker(
    *,
    supabase_client: httpx.AsyncClient,
    the_odds_api_client: httpx.AsyncClient,
    the_odds_api_key: str,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    weatherapi_client: httpx.AsyncClient,
    weatherapi_key: str,
    cache_backend: CacheBackend | None = None,
    now: datetime | None = None,
    triggered_game_ids: set[str] | None = None,
    odds_adapter: OddsAdapter | None = None,
    player_props_adapter: PlayerPropsAdapter | None = None,
    injury_adapter: InjuryAdapter | None = None,
    weather_adapter: WeatherAdapter | None = None,
) -> PregameWorkerResult:
    """Runs one Pregame Worker cycle. Always returns a
    `PregameWorkerResult`, never raises -- same finite-job shape as every
    other specialized worker.

    `odds_adapter`/`player_props_adapter`/`injury_adapter`/`weather_adapter`
    (dependency-injection seam, not Demo-specific): passed straight through
    to the four delegated worker calls below, unchanged otherwise. `None`
    (the default, for all four) preserves today's real-provider
    construction and behavior unchanged -- this worker itself never
    constructs an adapter, so there is nothing else to inject here."""
    headers = _auth_headers()
    cache_backend = cache_backend or InMemoryCacheBackend()
    now = now or datetime.now(timezone.utc)
    triggered_game_ids = triggered_game_ids or set()

    today: date = now.date()
    try:
        games = await list_games_in_window(
            supabase_client, headers, start=today, end=today + timedelta(days=_CANDIDATE_WINDOW_DAYS)
        )
    except GamesQueryError as exc:
        return PregameWorkerResult(status="failed", error=f"failed to list candidate games: {exc}")

    if not games:
        return PregameWorkerResult(status="success", games_considered=0)

    due_games = [
        game
        for game in games
        if game["id"] not in triggered_game_ids
        and classify_window(now=now, kickoff=_parse_datetime(game["scheduled_start"])) is Window.RAMP_5M
    ]

    if not due_games:
        return PregameWorkerResult(status="success", games_considered=len(games))

    category_failures: list[str] = []
    triggered: list[str] = []
    dgi_refreshed = 0
    dgi_failures: list[str] = []

    for game in due_games:
        game_id = game["id"]
        target = [game_id]

        odds_result = await run_odds_worker(
            supabase_client=supabase_client, the_odds_api_client=the_odds_api_client,
            the_odds_api_key=the_odds_api_key, cache_backend=cache_backend, now=now, target_game_ids=target,
            odds_adapter=odds_adapter,
        )
        _collect(odds_result, label="odds", game_id=game_id, out=category_failures)

        props_result = await run_player_props_worker(
            supabase_client=supabase_client, the_odds_api_client=the_odds_api_client,
            the_odds_api_key=the_odds_api_key, cache_backend=cache_backend, now=now, target_game_ids=target,
            player_props_adapter=player_props_adapter,
        )
        _collect(props_result, label="player_props", game_id=game_id, out=category_failures)

        injury_result = await run_injury_worker(
            supabase_client=supabase_client, sportsdataio_client=sportsdataio_client,
            sportsdataio_api_key=sportsdataio_api_key, cache_backend=cache_backend, now=now, target_game_ids=target,
            injury_adapter=injury_adapter,
        )
        _collect(injury_result, label="injury", game_id=game_id, out=category_failures)

        weather_result = await run_weather_worker(
            supabase_client=supabase_client, weatherapi_client=weatherapi_client,
            weatherapi_key=weatherapi_key, cache_backend=cache_backend, now=now, target_game_ids=target,
            weather_adapter=weather_adapter,
        )
        _collect(weather_result, label="weather", game_id=game_id, out=category_failures)

        triggered.append(game_id)

        try:
            await refresh_daily_game_intelligence_for_game(supabase_client, headers, game)
            dgi_refreshed += 1
        except (GamesQueryError, DailyGameIntelligenceError) as exc:
            dgi_failures.append(f"{game_id}: {exc}")

    status = "partial" if (category_failures or dgi_failures) else "success"
    return PregameWorkerResult(
        status=status,
        games_considered=len(games),
        games_triggered=triggered,
        category_failures=category_failures,
        daily_game_intelligence_refreshed=dgi_refreshed,
        daily_game_intelligence_failures=dgi_failures,
    )
