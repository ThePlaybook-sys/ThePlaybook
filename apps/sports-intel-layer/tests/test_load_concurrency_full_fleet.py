"""Full-fleet Sunday-slate load/concurrency extension (Phase 3 acceptance
closure, 2026-08-19).

`tests/test_load_concurrency.py` (Phase 3B, 2026-08-11) proved this for
Odds/Player Props only, before the SportsDataIO adapter categories
(Injury/Weather/Roster/TeamStats/PlayerStats) and the Pregame/Postgame
Workers existed (3E-5 through 3E-8). This file closes that gap: the same
~13-game Sunday-slate scale (2026-08-10 credit projection, unchanged from
the original test) exercised against every worker/category built since,
proving the acceptance goals Mac's 2026-08-19 checkpoint asked for:

- one full slate processed without accidental N+1 provider patterns
- bulk endpoints remain bulk (Odds discovery, Injury, TeamStats/
  PlayerStats weekly bulk) regardless of slate size
- per-game/per-team endpoints remain bounded (one call per distinct
  game/team, never more)
- one malformed row/game/team does not take down the slate
- caching reduces repeated provider work as designed
- adaptive workers do not explode call counts

**INTERNAL PIPELINE LOAD PROVEN, not PRODUCTION PROVIDER LOAD PROVEN** --
fixtures/fakes only throughout, exactly like the original 3B test. This
proves OUR code's call-count/isolation/caching behavior at realistic
scale; it says nothing about a real provider's actual throughput or
rate-limit behavior under that volume (that stays on the DEFERRED —
FINANCIAL/EXTERNAL DEPENDENCY checklist, see PROGRESS.md). No live
provider calls anywhere in this file.

Reuses each worker's own already-approved test-module mock helpers where
they're already correct and complete (imported, not re-derived) --
this file's job is to prove those mechanisms hold at slate scale, not to
re-invent per-worker mocking from scratch.
"""
from __future__ import annotations

import json as _json
from datetime import date, datetime, timezone

import httpx
import pytest
import respx

from app.adapters.cache import InMemoryCacheBackend
from app.master_refresh.run import run_master_refresh
from app.workers.injury_worker import run_injury_worker
from app.workers.news_worker import run_news_worker
from app.workers.odds_worker import run_odds_worker
from app.workers.player_props_worker import run_player_props_worker
from app.workers.postgame_worker import run_postgame_worker
from app.workers.pregame_worker import run_pregame_worker
from app.workers.weather_worker import run_weather_worker
from tests.adapters.the_odds_api_fixtures import load as load_odds
from tests.adapters.sportsdataio_fixtures import load as load_sdio
from tests.test_postgame_worker import (
    GAME_KEY as PG_GAME_KEY,
    GAME_ID as PG_GAME_ID,
    SEASON as PG_SEASON,
    WEEK as PG_WEEK,
    _GamesStore,
    _game_row as _pg_game_row,
    _mock_player_provider_ids,
    _mock_player_stats_table,
    _mock_season as _mock_pg_season,
    _mock_schedule_final,
    _mock_team_provider_ids,
    _mock_team_stats_table,
    _team_stats_row,
)

SUPABASE_URL = "https://test-project.supabase.co"
ODDS_API_URL = "https://api.the-odds-api.com"
SPORTSDATAIO_URL = "https://api.sportsdata.io"
WEATHERAPI_URL = "https://api.weatherapi.com"
NEWSAPI_URL = "https://newsapi.org"

SLATE_SIZE = 13  # same approved Sunday-slate peak as tests/test_load_concurrency.py


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _slate_teams() -> list[tuple[str, str]]:
    """13 games, 26 distinct teams (no team plays twice) -- generated, not
    hand-fixtured, so the slate size is a single number to change."""
    return [(f"H{i:02d}", f"A{i:02d}") for i in range(1, SLATE_SIZE + 1)]


def _slate_game_ids() -> list[str]:
    return [f"g-{i:02d}" for i in range(1, SLATE_SIZE + 1)]


# ============================================================
# Odds Worker -- bulk discovery stays bulk regardless of slate size
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_odds_worker_full_slate_one_bulk_call_not_thirteen(monkeypatch):
    _headers_env(monkeypatch)
    game_rows = [
        {
            "id": gid, "external_provider_id": None, "home_team": h, "away_team": a,
            "scheduled_start": "2026-09-14T17:00:00Z", "stadium": "X", "status": "scheduled",
            "season_type": "regular", "week": 2,
        }
        for gid, (h, a) in zip(_slate_game_ids(), _slate_teams())
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=game_rows))
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    # No team_provider_ids mappings for the synthetic H##/A## abbreviations
    # used here -- every event in the bulk fixture is simply unresolved
    # (isolated, reported, never fatal), which is fine: this test's own
    # purpose is the bulk-call-count proof, not linking correctness
    # (already covered elsewhere at unit scale).
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    odds_route = respx.get(f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/odds").mock(
        return_value=httpx.Response(200, json=load_odds("bulk_odds_multi_game.json"))
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))

    cache = InMemoryCacheBackend()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as sb, httpx.AsyncClient(base_url=ODDS_API_URL) as odds:
        result1 = await run_odds_worker(
            supabase_client=sb, the_odds_api_client=odds, the_odds_api_key="k",
            cache_backend=cache, now=datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc),
        )
        result2 = await run_odds_worker(  # rerun immediately -- cache should serve it
            supabase_client=sb, the_odds_api_client=odds, the_odds_api_key="k",
            cache_backend=cache, now=datetime(2026, 9, 14, 16, 0, 1, tzinfo=timezone.utc),
        )

    assert result1.status in ("success", "partial")
    # Bulk endpoint: ONE call covers all 13 due games, not 13 -- and the
    # immediate rerun makes zero additional calls (cache satisfies it).
    assert odds_route.call_count == 1


# ============================================================
# Player Props Worker -- per-game endpoint stays bounded, one bad game
# does not block the other 12
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_player_props_worker_full_slate_bounded_calls_and_isolation(monkeypatch):
    _headers_env(monkeypatch)
    game_ids = _slate_game_ids()
    teams = _slate_teams()
    game_rows = [
        {
            "id": gid, "external_provider_id": None, "home_team": h, "away_team": a,
            "scheduled_start": "2026-09-14T17:00:00Z", "stadium": "X", "status": "scheduled",
            "season_type": "regular", "week": 2,
        }
        for gid, (h, a) in zip(game_ids, teams)
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=game_rows))
    # Every game already linked to a the_odds_api event id (1:1 with its
    # own db game id, for simplicity) -- Player Props Worker only fetches
    # already-linked due games (see module docstring: it cannot
    # self-discover event ids), so linkage is required for this test's own
    # purpose (proving per-game call-count bounding), not the separate
    # unlinked-game path (already covered at unit scale elsewhere).
    def _game_provider_respond(request: httpx.Request) -> httpx.Response:
        game_id_param = request.url.params.get("game_id", "")
        rows = [{"game_id": gid, "provider_game_id": gid} for gid in game_ids if gid in game_id_param]
        return httpx.Response(200, json=rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_game_provider_respond)
    respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(201))
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))

    call_count = {"n": 0}
    bad_game = game_ids[3]

    def _per_game_respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if bad_game in str(request.url):
            return httpx.Response(200, json={"id": bad_game})  # malformed -- missing home_team etc.
        return httpx.Response(200, json=load_odds("player_props_event.json"))

    for gid in game_ids:
        respx.get(f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/events/{gid}/odds").mock(
            side_effect=_per_game_respond
        )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as sb, httpx.AsyncClient(base_url=ODDS_API_URL) as odds:
        result = await run_player_props_worker(
            supabase_client=sb, the_odds_api_client=odds, the_odds_api_key="k",
            now=datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc),  # 30 min before kickoff, RAMP_60M
        )

    # Bounded: exactly one HTTP call per distinct game, never more (no N+1
    # against the same game, no re-fetch of an already-covered one).
    assert call_count["n"] == SLATE_SIZE
    # One malformed game's response never blocks the other 12.
    assert result.status in ("success", "partial")


# ============================================================
# Injury Worker -- bulk endpoint, ONE call regardless of how many games/
# teams are in the candidate slate
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_injury_worker_full_slate_stays_one_bulk_call(monkeypatch):
    _headers_env(monkeypatch)
    game_ids = _slate_game_ids()
    teams = _slate_teams()
    game_rows = [
        {
            "id": gid, "external_provider_id": None, "home_team": h, "away_team": a,
            "scheduled_start": "2026-09-20T17:00:00Z", "stadium": "X", "status": "scheduled",
            "season_type": "regular", "week": 1,
        }
        for gid, (h, a) in zip(game_ids, teams)
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=game_rows))
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(return_value=httpx.Response(200, json=[{"id": "l"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(200, json=[{"year": 2026, "start_date": "2026-09-04", "end_date": "2027-02-14"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(201))
    injury_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/stats/json/Injuries/2026REG/1").mock(
        return_value=httpx.Response(200, json=load_sdio("injuries_normal.json"))
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as sb, httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio:
        result = await run_injury_worker(
            supabase_client=sb, sportsdataio_client=sdio, sportsdataio_api_key="k",
            now=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),  # Wednesday, active-week cadence, 4 days out
        )

    assert result.status in ("success", "partial")
    assert injury_route.call_count == 1  # bulk endpoint stays bulk at 13-game scale


# ============================================================
# Weather Worker -- per-game endpoint stays bounded, provider failure on
# one game never blocks the other 12
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_weather_worker_full_slate_bounded_calls_and_isolation(monkeypatch):
    _headers_env(monkeypatch)
    game_ids = _slate_game_ids()
    game_rows = [
        {
            "id": gid, "external_provider_id": None, "home_team": "KC", "away_team": "BAL",
            "scheduled_start": "2026-09-14T17:00:00Z", "stadium": "X", "status": "scheduled",
            "season_type": "regular", "week": 2,
            "venue_lat": 39.05, "venue_long": -94.48, "venue_type": "outdoor",
        }
        for gid in game_ids
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=game_rows))
    respx.post(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(201))

    from tests.adapters.weatherapi_fixtures import load as load_weather

    call_count = {"n": 0}

    def _forecast_respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        # Games are polled in order; fail exactly the 8th call (one game
        # among the 13) -- proves a single provider failure part-way
        # through the slate never blocks the games polled before or after
        # it, without needing the game's own id to appear in the request
        # URL (WeatherAPI's endpoint is lat/long-keyed, not game-keyed).
        if call_count["n"] == 8:
            return httpx.Response(503)
        return httpx.Response(200, json=load_weather("forecast_normal.json"))

    respx.get(f"{WEATHERAPI_URL}/v1/forecast.json").mock(side_effect=_forecast_respond)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as sb, httpx.AsyncClient(base_url=WEATHERAPI_URL) as wx:
        result = await run_weather_worker(
            supabase_client=sb, weatherapi_client=wx, weatherapi_key="k",
            now=datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc),
        )

    assert call_count["n"] == SLATE_SIZE  # one call per game, bounded
    assert result.status == "partial"  # one game's provider failure isolated, not fatal
    assert len(result.failures) == 1


# ============================================================
# News Worker -- per-team endpoint, calls scale with distinct teams,
# never with games (a 13-game/26-team slate must not produce 26+ calls
# beyond the 26 distinct teams, and never a per-game duplicate)
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_news_worker_full_slate_calls_scale_with_distinct_teams(monkeypatch):
    _headers_env(monkeypatch)
    game_ids = _slate_game_ids()
    teams = _slate_teams()
    game_rows = [
        {
            "id": gid, "external_provider_id": None, "home_team": h, "away_team": a,
            "scheduled_start": "2026-09-14T17:00:00Z", "stadium": "X", "status": "scheduled",
            "season_type": "regular", "week": 2,
            "venue_lat": 39.05, "venue_long": -94.48, "venue_type": "outdoor",
        }
        for gid, (h, a) in zip(game_ids, teams)
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=game_rows))
    distinct_teams = sorted({t for pair in teams for t in pair})
    assert len(distinct_teams) == SLATE_SIZE * 2  # 26 distinct teams, confirms no accidental overlap
    team_provider_rows = [{"provider_team_id": abbrev, "team_id": f"team-{abbrev}"} for abbrev in distinct_teams]
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=team_provider_rows))
    teams_rows = [{"id": f"team-{abbrev}", "name": f"Team {abbrev}"} for abbrev in distinct_teams]
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(return_value=httpx.Response(200, json=teams_rows))
    respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))

    call_count = {"n": 0}

    def _news_respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"status": "ok", "totalResults": 0, "articles": []})

    respx.get(f"{NEWSAPI_URL}/v2/everything").mock(side_effect=_news_respond)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as sb, httpx.AsyncClient(base_url=NEWSAPI_URL) as news:
        result = await run_news_worker(
            supabase_client=sb, newsapi_client=news, newsapi_key="k",
            now=datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc),
        )

    # Exactly one call per distinct team -- 26, not 13 (games) and not 52
    # (games x 2 without dedup) -- proves team-level, not game-level,
    # request granularity holds at slate scale.
    assert call_count["n"] == len(distinct_teams) == SLATE_SIZE * 2
    assert result.status in ("success", "partial")


# ============================================================
# Master Refresh -- full slate + full-league roster ingestion: Schedule
# stays one bulk call, Roster stays bounded to distinct teams, one team's
# ingestion failure never blocks the other 25
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_master_refresh_full_slate_and_full_league_roster(monkeypatch):
    _headers_env(monkeypatch)
    game_ids = _slate_game_ids()
    teams = _slate_teams()
    distinct_teams = sorted({t for pair in teams for t in pair})

    respx.post(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(201, json=[{"id": "mrr-1"}]))
    respx.patch(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(204))
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(return_value=httpx.Response(200, json=[{"id": "l"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(200, json=[{"year": 2026, "start_date": "2026-09-04", "end_date": "2027-02-14"}])
    )
    schedule_rows = [
        {
            "GameKey": gid, "SeasonType": 1, "Season": 2026, "Week": 2,
            "HomeTeam": h, "AwayTeam": a, "DateTimeUTC": "2026-09-14T17:00:00",
            "Status": "Scheduled", "StadiumDetails": {"Name": "X"},
        }
        for gid, (h, a) in zip(game_ids, teams)
    ]
    schedule_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=schedule_rows)
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(201))
    created_ids = iter([f"db-{gid}" for gid in game_ids])
    respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": next(created_ids)}])
    )
    slate_rows = [
        {"id": f"db-{gid}", "home_team": h, "away_team": a, "scheduled_start": "2026-09-14T17:00:00+00:00", "stadium": "X", "status": "scheduled"}
        for gid, (h, a) in zip(game_ids, teams)
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=slate_rows))

    depth_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/DepthCharts").mock(
        return_value=httpx.Response(200, json=[])
    )
    roster_call_count = {"n": 0}
    bad_team = distinct_teams[5]

    def _roster_respond(request: httpx.Request) -> httpx.Response:
        roster_call_count["n"] += 1
        team = str(request.url).rsplit("/", 1)[-1]
        return httpx.Response(200, json=[{"PlayerID": hash(team) % 100000, "Team": team, "Name": f"{team} Player", "Position": "QB"}])

    for team in distinct_teams:
        respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/{team}").mock(side_effect=_roster_respond)

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": f"team-{t}", "provider_team_id": t} for t in distinct_teams])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))

    def _players_respond(request: httpx.Request) -> httpx.Response:
        body = _json.loads(request.content)
        if body.get("team_id") == f"team-{bad_team}":
            return httpx.Response(500)  # one team's identity write fails
        return httpx.Response(201, json=[{"id": f"player-{body['name']}"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(side_effect=_players_respond)
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    dgi_route = respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as sb, httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio:
        result = await run_master_refresh(
            supabase_client=sb, sportsdataio_client=sdio, sportsdataio_api_key="k",
            today=date(2026, 9, 10),
        )

    assert schedule_route.call_count == 1  # bulk Schedule stays bulk at 13-game scale
    assert depth_route.call_count == 1  # bulk DepthCharts stays bulk
    assert roster_call_count["n"] == len(distinct_teams) == 26  # one call per distinct team, bounded
    assert result.games_in_slate == SLATE_SIZE
    assert result.games_created == SLATE_SIZE
    assert result.daily_game_intelligence_written == SLATE_SIZE  # every game still refreshed
    assert dgi_route.call_count == SLATE_SIZE
    # One team's identity-write failure is isolated, not fatal to the run
    # or to any other team/game -- proven at full-league scale, not just
    # the 2-team scenario the isolation-fix tests already covered.
    assert result.status == "partial"
    assert any(bad_team in f for f in result.roster_ingestion_failures)
    assert len(result.roster_ingestion_failures) == 1


# ============================================================
# SportsDataIO TeamStats -- weekly bulk endpoint stays bulk across a full
# 13-game week, not 13 separate calls
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_sportsdataio_team_stats_weekly_bulk_stays_one_call_for_full_slate():
    from app.adapters.providers.sportsdataio import SportsDataIOTeamStatsAdapter

    game_ids = _slate_game_ids()
    teams = _slate_teams()
    bulk_rows = []
    for gid, (h, a) in zip(game_ids, teams):
        bulk_rows.append({"GameKey": gid, "Team": h, "Score": 20})
        bulk_rows.append({"GameKey": gid, "Team": a, "Score": 17})

    route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/TeamGameStats/2026REG/2").mock(
        return_value=httpx.Response(200, json=bulk_rows)
    )
    game_key_map = {gid: ("2026REG", 2) for gid in game_ids}
    adapter = SportsDataIOTeamStatsAdapter(
        client=httpx.AsyncClient(base_url=SPORTSDATAIO_URL), api_key="test-key",
        season_week_for_game=lambda gid: game_key_map[gid],
        cache_backend=InMemoryCacheBackend(),  # the adapter's own internal week-bulk cache
    )

    responses = [await adapter.fetch_team_stats(gid) for gid in game_ids]

    assert route.call_count == 1  # one bulk call served all 13 games' worth of team stats
    for gid, response in zip(game_ids, responses):
        assert len(response.value) == 2  # each game's own 2 team rows filtered correctly, no cross-contamination


# ============================================================
# Postgame Worker -- 5 simultaneous final games, shared weekly-bulk
# TeamStats/PlayerStats stays one call each, all 5 reconciled
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_postgame_worker_five_simultaneous_finals_bulk_reuse_across_games(monkeypatch):
    _headers_env(monkeypatch)
    NOW = datetime(2026, 9, 14, 21, 0, 0, tzinfo=timezone.utc)
    extra_games = [
        {"id": f"g-final-{i}", "key": f"20259910{i}", "home": f"H{i}", "away": f"A{i}"} for i in range(2, 6)
    ]
    all_rows = [_pg_game_row(status="final", finalized_at=NOW.isoformat())]
    for g in extra_games:
        all_rows.append({**_pg_game_row(status="final", finalized_at=NOW.isoformat()), "id": g["id"], "home_team": g["home"], "away_team": g["away"]})
    store = _GamesStore(all_rows)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=store.get)
    respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=store.patch)

    linked = {PG_GAME_ID: PG_GAME_KEY, **{g["id"]: g["key"] for g in extra_games}}

    def _game_provider_respond(request: httpx.Request) -> httpx.Response:
        game_id_param = request.url.params.get("game_id", "")
        provider_id_param = request.url.params.get("provider_game_id", "")
        if game_id_param:
            rows = [{"game_id": gid, "provider_game_id": pid} for gid, pid in linked.items() if gid in game_id_param]
        else:
            rows = [{"game_id": gid, "provider_game_id": pid} for gid, pid in linked.items() if pid in provider_id_param]
        return httpx.Response(200, json=rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_game_provider_respond)
    _mock_pg_season()
    _mock_schedule_final()
    _mock_team_provider_ids()
    _mock_player_provider_ids()

    team_stats_rows = [_team_stats_row(team="KC", home_or_away="HOME", score=27), _team_stats_row(team="BAL", home_or_away="AWAY", score=20)]
    for g in extra_games:
        team_stats_rows.append({"GameKey": g["key"], "Team": g["home"], "HomeOrAway": "HOME", "Score": 21})
        team_stats_rows.append({"GameKey": g["key"], "Team": g["away"], "HomeOrAway": "AWAY", "Score": 14})
    team_stats_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/TeamGameStats/{PG_SEASON}/{PG_WEEK}").mock(
        return_value=httpx.Response(200, json=team_stats_rows)
    )
    player_stats_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/stats/json/PlayerGameStatsByWeek/{PG_SEASON}/{PG_WEEK}").mock(
        return_value=httpx.Response(200, json=[])
    )
    _mock_team_stats_table()
    _mock_player_stats_table()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as sb, httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio:
        result = await run_postgame_worker(
            supabase_client=sb, sportsdataio_client=sdio, sportsdataio_api_key="k", now=NOW,
        )

    assert set(result.games_reconciled) == {PG_GAME_ID} | {g["id"] for g in extra_games}
    # REAL FINDING, documented not silently accepted (same "document
    # actual behavior, not aspirational" precedent as the original 3B
    # load test's own in-flight-coalescing finding): Postgame Worker's
    # `_ingest_final_stats_for_game` constructs a brand-new
    # `SportsDataIOTeamStatsAdapter`/`SportsDataIOPlayerStatsAdapter` per
    # game, with no shared `cache_backend` -- so N games from the SAME
    # week finalizing in the SAME Postgame Worker cycle each independently
    # re-fetch the identical weekly-bulk payload, rather than the first
    # game's fetch satisfying the rest (the "download once, reuse
    # everywhere" principle this codebase states elsewhere, not followed
    # here). Results are still correct (each game's own rows are filtered
    # correctly from each redundant fetch) -- this is a real efficiency
    # gap, not a correctness bug, out of this pass's explicit scope to
    # fix. 5 calls for 5 same-week simultaneous finals, not 1.
    assert team_stats_route.call_count == 5
    assert player_stats_route.call_count == 5


# ============================================================
# Pregame Worker -- 5 games crossing T-minus-5 in the same cycle: work
# stays bounded to exactly those 5 targeted games, not a full-slate rescan
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_pregame_worker_multiple_simultaneous_triggers_stay_bounded(monkeypatch):
    _headers_env(monkeypatch)
    kickoff = "2026-09-14T17:00:00Z"  # T-minus-5 at 16:55:00Z
    triggered_ids = [f"pg-{i}" for i in range(1, 6)]
    game_rows = [
        {
            "id": gid, "external_provider_id": None, "home_team": "KC", "away_team": "BAL",
            "scheduled_start": kickoff, "stadium": "X", "status": "scheduled",
            "season_type": "regular", "week": 2,
            "venue_lat": 39.05, "venue_long": -94.48, "venue_type": "outdoor",
        }
        for gid in triggered_ids
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=game_rows))
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(return_value=httpx.Response(200, json=[{"id": "l"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(200, json=[{"year": 2026, "start_date": "2026-09-04", "end_date": "2027-02-14"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(
        return_value=httpx.Response(200, json=[{"news": None, "players": None}])
    )
    dgi_route = respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))

    odds_route = respx.get(f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/odds").mock(
        return_value=httpx.Response(200, json=[])
    )
    injuries_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/stats/json/Injuries/2026REG/2").mock(
        return_value=httpx.Response(200, json=[])
    )
    from tests.adapters.weatherapi_fixtures import load as load_weather

    forecast_route = respx.get(f"{WEATHERAPI_URL}/v1/forecast.json").mock(
        return_value=httpx.Response(200, json=load_weather("forecast_normal.json"))
    )
    for gid in triggered_ids:
        respx.get(f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/events/{gid}/odds").mock(
            return_value=httpx.Response(200, json={"id": gid, "home_team": "KC", "away_team": "BAL", "commence_time": kickoff, "bookmakers": []})
        )

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as sb,
        httpx.AsyncClient(base_url=ODDS_API_URL) as odds,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio,
        httpx.AsyncClient(base_url=WEATHERAPI_URL) as wx,
    ):
        result = await run_pregame_worker(
            supabase_client=sb, the_odds_api_client=odds, the_odds_api_key="k",
            sportsdataio_client=sdio, sportsdataio_api_key="k",
            weatherapi_client=wx, weatherapi_key="k",
            now=datetime(2026, 9, 14, 16, 55, 0, tzinfo=timezone.utc),
        )

    # Odds discovery stays one bulk call (unaffected by 5 simultaneous
    # triggers -- same bulk mechanism as the full-slate Odds test above).
    assert odds_route.call_count == 1
    # Injury stays one bulk call regardless of how many games triggered.
    assert injuries_route.call_count == 1
    # Weather is per-game -- bounded to exactly the 5 triggered games.
    assert forecast_route.call_count == 5
    # Every triggered game gets its own targeted daily_game_intelligence
    # refresh -- 5, not fewer, not a full-slate rescan.
    assert dgi_route.call_count == 5
    assert len(result.games_triggered) == 5
