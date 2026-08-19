"""Orchestration tests for app.master_refresh.run (Phase 3E-2).

Every HTTP boundary -- Supabase and SportsDataIO both -- is respx-mocked.
`run_master_refresh`'s signature only ever accepts a `supabase_client` and
a `sportsdataio_client` -- structurally, there is no way for it to call
The Odds API, WeatherAPI, or NewsAPI/GNews, which is itself the strongest
proof of Decision 1's "does not directly fetch odds/props/injuries/
weather/news." No real network is used anywhere in this file.
"""
from __future__ import annotations

import json as _json
from datetime import date, datetime, timezone

import httpx
import pytest
import respx

from app.adapters.cache import InMemoryCacheBackend, RedisCacheBackend
from app.master_refresh.run import run_master_refresh

SUPABASE_URL = "https://test-project.supabase.co"
SPORTSDATAIO_URL = "https://api.sportsdata.io"

TODAY = date(2026, 9, 9)


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _game_row(game_key, home, away, dt, week=1, stadium="Lumen Field"):
    return {
        "GameKey": game_key,
        "SeasonType": 1,
        "Season": 2026,
        "Week": week,
        "HomeTeam": home,
        "AwayTeam": away,
        "DateTimeUTC": dt,
        "Status": "Scheduled",
        "StadiumDetails": {"Name": stadium},
    }


def _mock_season(seasons_response=None):
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(
        return_value=httpx.Response(200, json=[{"id": "league-nfl"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(
            200,
            json=seasons_response
            or [{"year": 2026, "start_date": "2026-09-04", "end_date": "2027-02-14"}],
        )
    )


def _mock_players_and_depth_charts(teams):
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/DepthCharts").mock(
        return_value=httpx.Response(200, json=[])
    )
    for team in teams:
        respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/{team}").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"PlayerID": 1, "Team": team, "Name": f"{team} QB", "Position": "QB"},
                ],
            )
        )
    _mock_roster_ingestion_supabase(teams)


def _mock_roster_ingestion_supabase(teams):
    """Generic success mocks for Phase 3F-1's persist_roster writes (team
    resolution, players create-or-confirm, player_provider_ids link,
    roster_memberships read/insert, players.team_id sync,
    depth_chart_snapshots insert). Master Refresh orchestration tests only
    need this to not block the run -- dedicated roster/depth-chart
    persistence behavior (team change, unresolved team, unchanged
    membership, snapshot shape) is covered in test_roster_ingestion.py."""
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(
            200, json=[{"team_id": f"team-{team}", "provider_team_id": team} for team in teams]
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": "roster-player-1"}])
    )
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))


def _mock_empty_intelligence():
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))


def _mock_games_read(slate_rows, previous_by_team=None):
    """One route serves both list_games_in_window (no `status` filter) and
    find_previous_final_game (has `status=eq.final`) -- distinguished by
    inspecting the request's own query params, since respx matches routes
    by URL, not by query string, unless told to."""
    previous_by_team = previous_by_team or {}

    def _respond(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("status") == "eq.final":
            or_clause = params.get("or", "")
            for team, row in previous_by_team.items():
                if team in or_clause:
                    return httpx.Response(200, json=[row] if row else [])
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=slate_rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_respond)


def _mock_game_provider_ids(existing: dict | None = None):
    existing = existing or {}

    def _get_respond(request: httpx.Request) -> httpx.Response:
        ids_param = request.url.params.get("provider_game_id", "")
        rows = []
        for game_key, game_id in existing.items():
            if game_key in ids_param:
                rows.append({"game_id": game_id, "provider_game_id": game_key})
        return httpx.Response(200, json=rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_get_respond)
    respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(201))


def _mock_games_create(created_id="db-game-1"):
    return respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(201, json=[{"id": created_id}])
    )


def _mock_games_patch():
    return respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(204))


def _mock_dgi_upsert():
    return respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(
        return_value=httpx.Response(201)
    )


@pytest.mark.asyncio
@respx.mock
async def test_normal_master_refresh(monkeypatch):
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200, json=[_game_row("g1", "SEA", "NE", "2026-09-10T00:20:00")]
        )
    )
    _mock_game_provider_ids()
    _mock_games_create()
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled", "venue_lat": 47.5952, "venue_long": -122.3316, "venue_type": "outdoor"}])
    _mock_players_and_depth_charts(["SEA", "NE"])
    _mock_empty_intelligence()
    dgi_route = _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
            today=TODAY,
        )

    assert result.status == "success"
    assert result.season_string == "2026REG"
    assert result.games_in_slate == 1
    assert result.games_created == 1
    assert result.daily_game_intelligence_written == 1
    assert dgi_route.called
    body = _json.loads(dgi_route.calls.last.request.content)
    assert set(body.keys()).isdisjoint(
        {"ai_scores", "momentum", "matchup_ratings", "ev_calculations", "confidence_scores", "recommendation_candidates"}
    )
    assert body["public_betting"] is None and body["sharp_money"] is None
    assert body["rest"]["home"]["season_opener"] is True  # no prior games mocked
    # Phase 3F-3: Master Refresh's own per-game refresh call goes through
    # the same shared app.master_refresh.game_refresh._build_stadium as
    # Pregame Worker -- venue_lat/venue_long/venue_type now surface here.
    assert body["stadium"] == {
        "name": "Lumen Field", "latitude": 47.5952, "longitude": -122.3316, "venue_type": "outdoor",
    }


@pytest.mark.asyncio
@respx.mock
async def test_empty_slate(monkeypatch):
    _headers_env(monkeypatch)
    _mock_season()
    # Only a game far outside the 7-day window.
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g-far", "SEA", "NE", "2026-10-01T00:20:00")])
    )

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
            today=TODAY,
        )

    assert result.status == "success"
    assert result.games_in_slate == 0
    assert result.games_created == 0


@pytest.mark.asyncio
@respx.mock
async def test_full_slate_multiple_games(monkeypatch):
    _headers_env(monkeypatch)
    _mock_season()
    games = [
        _game_row("g1", "SEA", "NE", "2026-09-10T00:20:00"),
        _game_row("g2", "KC", "BUF", "2026-09-13T17:00:00"),
        _game_row("g3", "DAL", "PHI", "2026-09-14T20:00:00"),
    ]
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=games)
    )
    _mock_game_provider_ids()
    created_ids = iter(["db-1", "db-2", "db-3"])
    respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": next(created_ids)}])
    )
    slate_rows = [
        {"id": "db-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"},
        {"id": "db-2", "home_team": "KC", "away_team": "BUF", "scheduled_start": "2026-09-13T17:00:00+00:00", "stadium": "Arrowhead", "status": "scheduled"},
        {"id": "db-3", "home_team": "DAL", "away_team": "PHI", "scheduled_start": "2026-09-14T20:00:00+00:00", "stadium": "AT&T Stadium", "status": "scheduled"},
    ]
    _mock_games_read(slate_rows)
    _mock_players_and_depth_charts(["SEA", "NE", "KC", "BUF", "DAL", "PHI"])
    _mock_empty_intelligence()
    _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
            today=TODAY,
        )

    assert result.status == "success"
    assert result.games_in_slate == 3
    assert result.games_created == 3
    assert result.daily_game_intelligence_written == 3


@pytest.mark.asyncio
@respx.mock
async def test_rerun_idempotency_no_duplicate_provider_calls(monkeypatch):
    _headers_env(monkeypatch)
    _mock_season()
    schedule_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-10T00:20:00")])
    )
    # Second run resolves via an already-existing game_provider_ids mapping.
    _mock_game_provider_ids(existing={"g1": "db-game-1"})
    patch_route = _mock_games_patch()
    create_route = respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(201, json=[{"id": "should-not-be-created"}])
    )
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}])
    depth_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/DepthCharts").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/SEA").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/NE").mock(
        return_value=httpx.Response(200, json=[])
    )
    _mock_empty_intelligence()
    _mock_dgi_upsert()

    cache = InMemoryCacheBackend()
    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result1 = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY, cache_backend=cache,
        )
        result2 = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY, cache_backend=cache,
        )

    assert result1.status == "success" and result2.status == "success"
    assert not create_route.called  # existing mapping -> PATCH path both times, never a create
    assert patch_route.call_count == 2  # one per run
    assert schedule_route.call_count == 1  # second run hit the 24h cache
    assert depth_route.call_count == 1  # roster bulk cache also reused


@pytest.mark.asyncio
@respx.mock
async def test_schedule_provider_failure_blocks_the_run(monkeypatch):
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(503)
    )

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "failed"
    assert "Schedule fetch failed" in result.error


@pytest.mark.asyncio
@respx.mock
async def test_malformed_schedule_row_is_isolated_not_batch_fatal(monkeypatch):
    """Row isolation (2026-08-18): a single malformed row (missing
    GameKey here) no longer fails the whole Master Refresh run --
    SportsDataIOScheduleAdapter.fetch_schedule logs and skips that row,
    returning every other valid row. This fixture has only the one
    malformed row, so the fetch succeeds with an empty slate (a
    legitimately different outcome from the old batch-fatal behavior,
    not a bug)."""
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200,
            json=[{"HomeTeam": "SEA", "AwayTeam": "NE", "DateTimeUTC": "2026-09-10T00:20:00", "Status": "Scheduled", "SeasonType": 1}],
        )
    )
    games_write_route = respx.post(f"{SUPABASE_URL}/rest/v1/games")
    dgi_route = respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence")

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "success"
    assert result.games_in_slate == 0
    assert not games_write_route.called  # the one row was skipped, nothing to write
    assert not dgi_route.called


@pytest.mark.asyncio
@respx.mock
async def test_one_bad_schedule_row_does_not_block_other_games_in_slate(monkeypatch):
    """The fuller row-isolation proof at the Master Refresh level: a
    slate with one genuinely unrecognized-status game alongside a valid
    one -- the valid game is still created and gets its
    daily_game_intelligence row; the bad one is simply absent."""
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200,
            json=[
                _game_row("g1", "SEA", "NE", "2026-09-10T00:20:00"),
                {"GameKey": "g-bad", "HomeTeam": "KC", "AwayTeam": "BUF", "DateTimeUTC": "2026-09-10T17:00:00", "SeasonType": 1, "Status": "TBD"},
            ],
        )
    )
    _mock_game_provider_ids()
    _mock_games_create()
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}])
    _mock_players_and_depth_charts(["SEA", "NE"])
    _mock_empty_intelligence()
    dgi_route = _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "success"
    assert result.games_in_slate == 1  # only the valid game -- the bad row never reached slate filtering
    assert result.games_created == 1
    assert dgi_route.called


@pytest.mark.asyncio
@respx.mock
async def test_one_team_roster_failure_does_not_block_other_games(monkeypatch):
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200,
            json=[
                _game_row("g1", "SEA", "NE", "2026-09-10T00:20:00"),
                _game_row("g2", "KC", "BUF", "2026-09-13T17:00:00"),
            ],
        )
    )
    _mock_game_provider_ids()
    created_ids = iter(["db-1", "db-2"])
    respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": next(created_ids)}])
    )
    _mock_games_read(
        [
            {"id": "db-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"},
            {"id": "db-2", "home_team": "KC", "away_team": "BUF", "scheduled_start": "2026-09-13T17:00:00+00:00", "stadium": "Arrowhead", "status": "scheduled"},
        ]
    )
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/DepthCharts").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/SEA").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/NE").mock(return_value=httpx.Response(500))  # fails
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/KC").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/BUF").mock(return_value=httpx.Response(200, json=[]))
    _mock_empty_intelligence()
    _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "partial"
    assert result.roster_failures == ["NE"]
    assert result.games_created == 2
    assert result.daily_game_intelligence_written == 2  # both games still got a row


@pytest.mark.asyncio
@respx.mock
async def test_cache_outage_degrades_gracefully(monkeypatch):
    """Reuses 3D's own fail-open RedisCacheBackend guarantee rather than
    reinventing cache-failure handling in Master Refresh itself."""
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-10T00:20:00")])
    )
    _mock_game_provider_ids()
    _mock_games_create()
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}])
    _mock_players_and_depth_charts(["SEA", "NE"])
    _mock_empty_intelligence()
    _mock_dgi_upsert()

    class _BrokenRedisClient:
        async def get(self, key):
            import redis.exceptions

            raise redis.exceptions.ConnectionError("simulated outage")

        async def set(self, key, value, ex=None):
            import redis.exceptions

            raise redis.exceptions.ConnectionError("simulated outage")

    broken_cache = RedisCacheBackend(_BrokenRedisClient())

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY, cache_backend=broken_cache,
        )

    assert result.status == "success"  # degraded to real calls, did not crash


@pytest.mark.asyncio
@respx.mock
async def test_database_partial_failure_isolated_per_game(monkeypatch):
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200,
            json=[
                _game_row("g1", "SEA", "NE", "2026-09-10T00:20:00"),
                _game_row("g2", "KC", "BUF", "2026-09-13T17:00:00"),
            ],
        )
    )
    _mock_game_provider_ids()
    created_ids = iter(["db-1", "db-2"])
    respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": next(created_ids)}])
    )
    _mock_games_read(
        [
            {"id": "db-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"},
            {"id": "db-2", "home_team": "KC", "away_team": "BUF", "scheduled_start": "2026-09-13T17:00:00+00:00", "stadium": "Arrowhead", "status": "scheduled"},
        ]
    )
    _mock_players_and_depth_charts(["SEA", "NE", "KC", "BUF"])
    _mock_empty_intelligence()

    def _dgi_respond(request: httpx.Request) -> httpx.Response:
        body = _json.loads(request.content)
        if body["game_id"] == "db-1":
            return httpx.Response(500, text="simulated write failure")
        return httpx.Response(201)

    respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(side_effect=_dgi_respond)

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "partial"
    assert result.daily_game_intelligence_written == 1
    assert len(result.daily_game_intelligence_failures) == 1
    assert "db-1" in result.daily_game_intelligence_failures[0]


@pytest.mark.asyncio
@respx.mock
async def test_season_opener_and_bye_week_rest_via_orchestration(monkeypatch):
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-10T00:20:00")])
    )
    _mock_game_provider_ids()
    _mock_games_create()
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}])
    # SEA has a previous final game 14 days back (elevated rest); NE has none (opener).
    _mock_previous_games = {
        "SEA": {"id": "prev", "home_team": "X", "away_team": "SEA", "scheduled_start": "2026-08-27T00:20:00+00:00"},
        "NE": None,
    }
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        side_effect=lambda request: (
            httpx.Response(
                200,
                json=(
                    [{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}]
                    if request.url.params.get("status") != "eq.final"
                    else (
                        [_mock_previous_games["SEA"]] if "SEA" in request.url.params.get("or", "")
                        else ([_mock_previous_games["NE"]] if _mock_previous_games["NE"] else [])
                    )
                ),
            )
        )
    )
    _mock_players_and_depth_charts(["SEA", "NE"])
    _mock_empty_intelligence()
    dgi_route = _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "success"
    body = _json.loads(dgi_route.calls.last.request.content)
    assert body["rest"]["home"]["rest_days"] == 14
    assert body["rest"]["home"]["season_opener"] is False
    assert body["rest"]["away"]["season_opener"] is True


@pytest.mark.asyncio
@respx.mock
async def test_no_unauthorized_provider_urls_are_ever_contacted(monkeypatch):
    """Only supabase + sportsdataio routes are registered -- if the code
    path ever attempted the-odds-api.com/weatherapi.com/newsapi.org, respx
    would raise on the unmatched request rather than the run silently
    succeeding."""
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-10T00:20:00")])
    )
    _mock_game_provider_ids()
    _mock_games_create()
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}])
    _mock_players_and_depth_charts(["SEA", "NE"])
    _mock_empty_intelligence()
    _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "success"
    for call in respx.calls:
        host = call.request.url.host
        assert host in ("test-project.supabase.co", "api.sportsdata.io")


def _mock_player_provider_ids_matching(mapping: dict[str, str]):
    """Phase 3F-4: a differentiated player_provider_ids GET mock -- returns
    only the rows whose provider_player_id appears in the request's own
    `in.(...)` filter, so both persist_roster's internal per-player
    resolve calls and the new end-of-cycle batched resolve call get a
    realistic, query-scoped answer instead of one blanket response."""

    def _respond(request: httpx.Request) -> httpx.Response:
        ids_param = request.url.params.get("provider_player_id", "")
        rows = [
            {"provider_player_id": provider_id, "player_id": player_id}
            for provider_id, player_id in mapping.items()
            if provider_id in ids_param
        ]
        return httpx.Response(200, json=rows)

    return respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(side_effect=_respond)


@pytest.mark.asyncio
@respx.mock
async def test_player_id_resolved_from_durable_identity_layer(monkeypatch):
    """Phase 3F-4: a player already known to player_provider_ids (from a
    prior cycle's persist_roster) gets its internal player_id attached to
    daily_game_intelligence.players this cycle."""
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-10T00:20:00")])
    )
    _mock_game_provider_ids()
    _mock_games_create()
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}])
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/DepthCharts").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/SEA").mock(
        return_value=httpx.Response(200, json=[{"PlayerID": 1, "Team": "SEA", "Name": "SEA QB", "Position": "QB"}])
    )
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/NE").mock(
        return_value=httpx.Response(200, json=[{"PlayerID": 2, "Team": "NE", "Name": "NE QB", "Position": "QB"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-SEA", "provider_team_id": "SEA"}, {"team_id": "team-NE", "provider_team_id": "NE"}])
    )
    _mock_player_provider_ids_matching({"1": "internal-uuid-sea-qb", "2": "internal-uuid-ne-qb"})
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(201, json=[{"id": "unused"}]))
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))
    _mock_empty_intelligence()
    dgi_route = _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "success"
    body = _json.loads(dgi_route.calls.last.request.content)
    assert body["players"]["home"][0]["player_id"] == "internal-uuid-sea-qb"
    assert body["players"]["away"][0]["player_id"] == "internal-uuid-ne-qb"
    # unchanged fields still present
    assert body["players"]["home"][0]["player_name"] == "SEA QB"


@pytest.mark.asyncio
@respx.mock
async def test_persist_roster_failure_preserves_fresh_roster_with_null_player_id(monkeypatch):
    """Phase 3F-4, the required partial-failure case: roster fetch
    succeeds for a team, but that team's persist_roster call fails (here,
    the depth_chart_snapshots write -- the one RosterIngestionError-raising
    failure mode run.py already isolates per-team). daily_game_intelligence
    still shows that team's fresh roster data -- it is never dropped -- but
    player_id must not be fabricated: since no confirmed identity mapping
    exists for that player this cycle, it stays null."""
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-10T00:20:00")])
    )
    _mock_game_provider_ids()
    _mock_games_create()
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}])
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/DepthCharts").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/SEA").mock(
        return_value=httpx.Response(200, json=[{"PlayerID": 1, "Team": "SEA", "Name": "SEA QB", "Position": "QB"}])
    )
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/NE").mock(
        return_value=httpx.Response(200, json=[{"PlayerID": 2, "Team": "NE", "Name": "NE QB", "Position": "QB"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-SEA", "provider_team_id": "SEA"}, {"team_id": "team-NE", "provider_team_id": "NE"}])
    )
    # No confirmed identity mapping exists yet for either player this cycle.
    _mock_player_provider_ids_matching({})
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(201, json=[{"id": "some-id"}]))
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))

    def _depth_chart_respond(request: httpx.Request) -> httpx.Response:
        body = _json.loads(request.content)
        if body.get("team_id") == "team-SEA":
            return httpx.Response(500)  # SEA's persist_roster call fails here
        return httpx.Response(201)

    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(side_effect=_depth_chart_respond)
    _mock_empty_intelligence()
    dgi_route = _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "partial"
    assert result.roster_ingestion_failures == ["SEA: failed to insert depth_chart_snapshots for team team-SEA: 500 "]
    body = _json.loads(dgi_route.calls.last.request.content)
    # SEA's roster data is still fresh and present -- never dropped because
    # the durable write failed.
    assert body["players"]["home"][0]["player_name"] == "SEA QB"
    assert body["players"]["home"][0]["depth_chart_rank"] is None
    # ...but its internal player_id is not fabricated.
    assert body["players"]["home"][0]["player_id"] is None
    # NE's game data is unaffected by SEA's failure.
    assert body["players"]["away"][0]["player_name"] == "NE QB"


@pytest.mark.asyncio
@respx.mock
async def test_player_id_resolution_is_batched_single_query_for_whole_slate(monkeypatch):
    """Phase 3F-4: the internal-player_id lookup is one batched query for
    the entire slate, not one per team or one per player -- avoiding N+1.
    Distinguishes the batched call from persist_roster's own pre-existing
    per-player resolve calls (each queries exactly one id) by asserting
    the *last* call (the new one, made after every team's roster loop
    finishes) carries every player's id in one `in.(...)` filter."""
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200,
            json=[
                _game_row("g1", "SEA", "NE", "2026-09-10T00:20:00"),
                _game_row("g2", "KC", "BUF", "2026-09-13T17:00:00"),
            ],
        )
    )
    _mock_game_provider_ids()
    created_ids = iter(["db-1", "db-2"])
    respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": next(created_ids)}])
    )
    _mock_games_read(
        [
            {"id": "db-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"},
            {"id": "db-2", "home_team": "KC", "away_team": "BUF", "scheduled_start": "2026-09-13T17:00:00+00:00", "stadium": "Arrowhead", "status": "scheduled"},
        ]
    )
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/DepthCharts").mock(return_value=httpx.Response(200, json=[]))
    for team, player_id in [("SEA", 1), ("NE", 2), ("KC", 3), ("BUF", 4)]:
        respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/{team}").mock(
            return_value=httpx.Response(200, json=[{"PlayerID": player_id, "Team": team, "Name": f"{team} QB", "Position": "QB"}])
        )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(
            200, json=[{"team_id": f"team-{t}", "provider_team_id": t} for t in ("SEA", "NE", "KC", "BUF")]
        )
    )
    player_ids_route = _mock_player_provider_ids_matching(
        {"1": "uuid-1", "2": "uuid-2", "3": "uuid-3", "4": "uuid-4"}
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(201, json=[{"id": "some-id"}]))
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))
    _mock_empty_intelligence()
    _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "success"
    # persist_roster's own 4 per-player resolve calls (one per new player)
    # each query exactly one id; the new batched call is the *last* one and
    # queries all 4 at once -- proof it's genuinely one query for the slate.
    last_call_ids = player_ids_route.calls.last.request.url.params.get("provider_player_id")
    assert last_call_ids == "in.(1,2,3,4)"


@pytest.mark.asyncio
@respx.mock
async def test_player_id_resolution_query_failure_is_non_blocking(monkeypatch):
    """Phase 3F-4: if the batched player_id lookup itself fails (e.g. a
    transient Supabase error), the run is NON-BLOCKING -- fresh roster
    data still reaches daily_game_intelligence.players, just with every
    player_id left null this cycle rather than fabricated."""
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-10T00:20:00")])
    )
    _mock_game_provider_ids()
    _mock_games_create()
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}])
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/DepthCharts").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/SEA").mock(
        return_value=httpx.Response(200, json=[{"PlayerID": 1, "Team": "SEA", "Name": "SEA QB", "Position": "QB"}])
    )
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/NE").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-SEA", "provider_team_id": "SEA"}])
    )

    call_count = {"n": 0}

    def _player_provider_ids_respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        # persist_roster's own pre-existing per-player resolve calls (one
        # from its own is_new check, one from inside ensure_player -- both
        # for SEA's single new player) succeed with "not found yet"; the
        # new batched call made after the whole roster loop finishes (the
        # 3rd hit) is the one that fails.
        if call_count["n"] <= 2:
            return httpx.Response(200, json=[])
        return httpx.Response(500)

    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(side_effect=_player_provider_ids_respond)
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(201, json=[{"id": "some-id"}]))
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))
    _mock_empty_intelligence()
    dgi_route = _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "partial"
    assert result.player_id_resolution_failed is True
    body = _json.loads(dgi_route.calls.last.request.content)
    # roster data still fresh and present despite the lookup failure
    assert body["players"]["home"][0]["player_name"] == "SEA QB"
    assert body["players"]["home"][0]["player_id"] is None


@pytest.mark.asyncio
@respx.mock
async def test_player_enrichment_touches_no_phase4_or_phase5_fields(monkeypatch):
    """Phase 3F-4 is a read-side enrichment of `players` only -- confirms
    it doesn't newly introduce any Phase 4/5 field into the upsert body."""
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-10T00:20:00")])
    )
    _mock_game_provider_ids()
    _mock_games_create()
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}])
    _mock_players_and_depth_charts(["SEA", "NE"])
    _mock_empty_intelligence()
    dgi_route = _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "success"
    body = _json.loads(dgi_route.calls.last.request.content)
    assert set(body.keys()).isdisjoint(
        {"ai_scores", "momentum", "matchup_ratings", "ev_calculations", "confidence_scores", "recommendation_candidates"}
    )


# Phase 3F-5: identity-isolation fix. persist_roster calls into
# player_identity/team_identity, which can raise PlayerIdentityError/
# TeamIdentityError -- distinct exception types from RosterIngestionError,
# previously NOT caught by run_master_refresh (confirmed by direct test
# execution during 3F-4 to crash the whole run instead of isolating
# per-team). These tests prove the fix: the failure is isolated at the
# same per-team boundary RosterIngestionError already used, unaffected
# teams/games continue, player_id is never fabricated for the failed
# team, and a genuinely unrelated exception type still propagates rather
# than being silently swallowed.

def _two_game_slate_setup():
    """Shared setup for a 2-game, 4-team slate (SEA@NE, KC@BUF) used by
    the isolation-fix tests below -- SEA is the team whose identity
    resolution will be made to fail; NE/KC/BUF all resolve normally."""
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200,
            json=[
                _game_row("g1", "SEA", "NE", "2026-09-10T00:20:00"),
                _game_row("g2", "KC", "BUF", "2026-09-13T17:00:00"),
            ],
        )
    )
    _mock_game_provider_ids()
    created_ids = iter(["db-1", "db-2"])
    respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": next(created_ids)}])
    )
    _mock_games_read(
        [
            {"id": "db-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"},
            {"id": "db-2", "home_team": "KC", "away_team": "BUF", "scheduled_start": "2026-09-13T17:00:00+00:00", "stadium": "Arrowhead", "status": "scheduled"},
        ]
    )
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/DepthCharts").mock(return_value=httpx.Response(200, json=[]))
    for team, player_id in [("SEA", 1), ("NE", 2), ("KC", 3), ("BUF", 4)]:
        respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/{team}").mock(
            return_value=httpx.Response(200, json=[{"PlayerID": player_id, "Team": team, "Name": f"{team} QB", "Position": "QB"}])
        )
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(201, json=[{"id": "some-id"}]))
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))
    _mock_empty_intelligence()


@pytest.mark.asyncio
@respx.mock
async def test_player_identity_error_for_one_team_does_not_crash_master_refresh(monkeypatch):
    """Points 1/3/4/5/6/7: a PlayerIdentityError from ensure_player's own
    resolve_player_ids call (SEA's player) is isolated -- NE/KC/BUF
    resolve normally, both games still get a daily_game_intelligence row,
    SEA is reported in roster_ingestion_failures, status is "partial", and
    SEA's player_id stays null (never fabricated) while NE's resolves."""
    _headers_env(monkeypatch)
    _mock_season()
    _two_game_slate_setup()
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(
            200, json=[{"team_id": f"team-{t}", "provider_team_id": t} for t in ("SEA", "NE", "KC", "BUF")]
        )
    )

    def _player_provider_ids_respond(request: httpx.Request) -> httpx.Response:
        ids_param = request.url.params.get("provider_player_id", "")
        if "1" in ids_param:  # SEA's player (PlayerID=1) -- identity resolution fails
            return httpx.Response(500)
        return httpx.Response(200, json=[])

    player_ids_route = respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        side_effect=_player_provider_ids_respond
    )
    dgi_route = _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "partial"
    assert result.roster_ingestion_failures == [
        "SEA: failed to resolve player ids for provider sportsdataio: 500 "
    ]
    assert result.games_created == 2
    assert result.daily_game_intelligence_written == 2  # both games still refreshed
    assert player_ids_route.called

    # Both games' upserts are in dgi_route.calls -- find each by game_id.
    bodies = {_json.loads(c.request.content)["game_id"]: _json.loads(c.request.content) for c in dgi_route.calls}
    sea_game_body = bodies["db-1"]
    kc_game_body = bodies["db-2"]
    # SEA's identity resolution failed -- its player_id is never fabricated.
    assert sea_game_body["players"]["home"][0]["player_id"] is None
    assert sea_game_body["players"]["home"][0]["player_name"] == "SEA QB"  # fresh data still shown
    # NE (in the same game as SEA) is unaffected.
    assert sea_game_body["players"]["away"][0]["player_name"] == "NE QB"
    # KC/BUF's game is completely unaffected by SEA's failure.
    assert kc_game_body["players"]["home"][0]["player_name"] == "KC QB"
    assert kc_game_body["players"]["away"][0]["player_name"] == "BUF QB"


@pytest.mark.asyncio
@respx.mock
async def test_team_identity_error_for_one_team_does_not_crash_master_refresh(monkeypatch):
    """Points 2/3/4/5/6/7: a TeamIdentityError from resolve_team_ids (SEA's
    own team_provider_ids lookup failing) is isolated the same way."""
    _headers_env(monkeypatch)
    _mock_season()
    _two_game_slate_setup()

    def _team_provider_ids_respond(request: httpx.Request) -> httpx.Response:
        ids_param = request.url.params.get("provider_team_id", "")
        if "SEA" in ids_param:
            return httpx.Response(500)
        return httpx.Response(
            200, json=[{"team_id": f"team-{t}", "provider_team_id": t} for t in ("NE", "KC", "BUF")]
        )

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(side_effect=_team_provider_ids_respond)
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    dgi_route = _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client, sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key", today=TODAY,
        )

    assert result.status == "partial"
    assert result.roster_ingestion_failures == [
        "SEA: failed to resolve team ids for provider sportsdataio: 500 "
    ]
    assert result.games_created == 2
    assert result.daily_game_intelligence_written == 2

    bodies = {_json.loads(c.request.content)["game_id"]: _json.loads(c.request.content) for c in dgi_route.calls}
    sea_game_body = bodies["db-1"]
    kc_game_body = bodies["db-2"]
    assert sea_game_body["players"]["home"][0]["player_id"] is None
    assert sea_game_body["players"]["home"][0]["player_name"] == "SEA QB"
    assert kc_game_body["players"]["home"][0]["player_name"] == "KC QB"


@pytest.mark.asyncio
@respx.mock
async def test_unrelated_exception_from_persist_roster_still_propagates(monkeypatch):
    """Point 8: the fix catches only the specific expected identity/
    ingestion exception classes at this boundary -- a genuinely unrelated
    exception (simulating a real programming error, not a known provider/
    persistence failure mode) is NOT silently swallowed; it still
    propagates out of run_master_refresh."""
    _headers_env(monkeypatch)
    _mock_season()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-10T00:20:00")])
    )
    _mock_game_provider_ids()
    _mock_games_create()
    _mock_games_read([{"id": "db-game-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "stadium": "Lumen Field", "status": "scheduled"}])
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/DepthCharts").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/SEA").mock(
        return_value=httpx.Response(200, json=[{"PlayerID": 1, "Team": "SEA", "Name": "SEA QB", "Position": "QB"}])
    )
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Players/NE").mock(return_value=httpx.Response(200, json=[]))

    def _team_provider_ids_raise(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("simulated unrelated programming error, not a known identity/ingestion failure")

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(side_effect=_team_provider_ids_raise)
    _mock_empty_intelligence()
    _mock_dgi_upsert()

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        with pytest.raises(RuntimeError, match="simulated unrelated programming error"):
            await run_master_refresh(
                supabase_client=supabase_client, sportsdataio_client=sdio_client,
                sportsdataio_api_key="test-key", today=TODAY,
            )
