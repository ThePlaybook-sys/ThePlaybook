"""Orchestration tests for app.workers.pregame_worker (Phase 3E-8).

A coordination worker, not a new provider category -- every HTTP boundary
these tests exercise (Supabase, The Odds API, SportsDataIO, WeatherAPI) is
respx-mocked and belongs to the four already-existing workers this module
delegates to; nothing here duplicates any of their fetch/persistence
logic. Covers: the T-minus-5-minute trigger boundary (and no premature
trigger before it), one execution per game/window via
`triggered_game_ids`, that the existing Odds/Player Props/Injury/Weather
workers are actually invoked (not re-implemented), the targeted
daily_game_intelligence refresh, one category's failure not corrupting
another's, and the structural "no duplicate provider pipeline" guarantee
(News Worker is never touched).
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.adapters.cache import InMemoryCacheBackend
from app.workers.pregame_worker import run_pregame_worker
from tests.adapters.weatherapi_fixtures import load as load_weather

SUPABASE_URL = "https://test-project.supabase.co"
ODDS_API_URL = "https://api.the-odds-api.com"
SPORTSDATAIO_URL = "https://api.sportsdata.io"
WEATHERAPI_URL = "https://api.weatherapi.com"

DB_GAME = "db-game-1"
KICKOFF = "2026-09-14T17:00:00Z"  # T-minus-5 at 2026-09-14T16:55:00Z


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _game_row(*, scheduled_start: str = KICKOFF) -> dict:
    return {
        "id": DB_GAME,
        "external_provider_id": None,
        "home_team": "KC",
        "away_team": "BAL",
        "scheduled_start": scheduled_start,
        "stadium": "Arrowhead Stadium",
        "status": "scheduled",
        "season_type": "regular",
        "week": 2,
        "venue_lat": 39.0489,
        "venue_long": -94.4839,
        "venue_type": "outdoor",
    }


def _mock_all_boundaries(*, injuries_status: int = 200, forecast_status: int = 200):
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_game_row()]))
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(return_value=httpx.Response(200, json=[{"id": "league-nfl"}]))
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
    dgi_upsert_route = respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))

    odds_route = respx.get(f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/odds").mock(
        return_value=httpx.Response(200, json=[])
    )
    injuries_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/stats/json/Injuries/2026REG/2").mock(
        return_value=httpx.Response(injuries_status, json=[] if injuries_status == 200 else None)
    )
    forecast_route = respx.get(f"{WEATHERAPI_URL}/v1/forecast.json").mock(
        return_value=httpx.Response(forecast_status, json=load_weather("forecast_normal.json") if forecast_status == 200 else None)
    )
    return {
        "odds": odds_route,
        "injuries": injuries_route,
        "forecast": forecast_route,
        "dgi_upsert": dgi_upsert_route,
    }


async def _run(*, now, triggered_game_ids=None):
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client, httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client, httpx.AsyncClient(
        base_url=WEATHERAPI_URL
    ) as weather_client:
        return await run_pregame_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
            weatherapi_client=weather_client,
            weatherapi_key="test-key",
            cache_backend=InMemoryCacheBackend(),
            now=now,
            triggered_game_ids=triggered_game_ids,
        )


T_MINUS_5 = datetime(2026, 9, 14, 16, 55, 0, tzinfo=timezone.utc)
T_MINUS_10 = datetime(2026, 9, 14, 16, 50, 0, tzinfo=timezone.utc)
T_MINUS_1H = datetime(2026, 9, 14, 16, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
@respx.mock
async def test_triggers_at_t_minus_5_and_coordinates_existing_workers(monkeypatch):
    _headers_env(monkeypatch)
    routes = _mock_all_boundaries()

    result = await _run(now=T_MINUS_5)

    assert result.games_triggered == [DB_GAME]
    assert routes["odds"].call_count == 1  # Odds Worker's own discovery call, reused not duplicated
    assert routes["injuries"].call_count == 1  # Injury Worker's own bulk call, reused not duplicated
    assert routes["forecast"].call_count == 1  # Weather Worker's own per-game call, reused not duplicated
    assert routes["dgi_upsert"].call_count == 1  # Decision 4: targeted daily_game_intelligence refresh

    # Phase 3F-3: the targeted refresh goes through the same shared
    # app.master_refresh.game_refresh._build_stadium as Master Refresh --
    # _game_row()'s real venue_lat/venue_long/venue_type surface here too.
    body = _json.loads(routes["dgi_upsert"].calls.last.request.content)
    assert body["stadium"] == {
        "name": "Arrowhead Stadium", "latitude": 39.0489, "longitude": -94.4839, "venue_type": "outdoor",
    }


@pytest.mark.asyncio
@respx.mock
async def test_no_premature_trigger_before_t_minus_5(monkeypatch):
    _headers_env(monkeypatch)
    routes = _mock_all_boundaries()

    result = await _run(now=T_MINUS_10)

    assert result.games_triggered == []
    assert routes["odds"].call_count == 0
    assert routes["injuries"].call_count == 0
    assert routes["forecast"].call_count == 0
    assert routes["dgi_upsert"].call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_no_trigger_well_before_kickoff(monkeypatch):
    _headers_env(monkeypatch)
    _mock_all_boundaries()

    result = await _run(now=T_MINUS_1H)

    assert result.games_triggered == []


@pytest.mark.asyncio
@respx.mock
async def test_one_execution_per_game_via_triggered_game_ids(monkeypatch):
    """Even though the game is still in its RAMP_5M window, a game already
    present in triggered_game_ids is not re-triggered -- one execution per
    game/window."""
    _headers_env(monkeypatch)
    routes = _mock_all_boundaries()

    result = await _run(now=T_MINUS_5, triggered_game_ids={DB_GAME})

    assert result.games_triggered == []
    assert routes["odds"].call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_one_category_failure_does_not_block_others_or_dgi_refresh(monkeypatch):
    _headers_env(monkeypatch)
    routes = _mock_all_boundaries(injuries_status=503)

    result = await _run(now=T_MINUS_5)

    assert result.status == "partial"
    assert any("injury" in f for f in result.category_failures)
    assert routes["odds"].call_count == 1  # odds still ran despite injury failing
    assert routes["forecast"].call_count == 1  # weather still ran despite injury failing
    assert routes["dgi_upsert"].call_count == 1  # DGI refresh still happens regardless
    assert result.daily_game_intelligence_refreshed == 1


@pytest.mark.asyncio
@respx.mock
async def test_no_games_in_candidate_window_is_a_no_op(monkeypatch):
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))

    result = await _run(now=T_MINUS_5)

    assert result.status == "success"
    assert result.games_considered == 0


def test_pregame_worker_never_touches_news_worker():
    """Structural guarantee: News Worker is deliberately excluded (see
    module docstring's explicit reasoning) -- this worker never imports
    it, even though the docstring names it to explain the exclusion."""
    import app.workers.pregame_worker as pregame_module

    assert not hasattr(pregame_module, "run_news_worker")
    assert not any(
        getattr(value, "__module__", "") == "app.workers.news_worker" for value in vars(pregame_module).values()
    )


def test_pregame_worker_signature_has_no_new_adapter_client():
    """No duplicate provider pipeline: every client parameter belongs to
    one of the four coordinated workers, none is a new adapter this
    module owns itself."""
    import inspect

    from app.workers.pregame_worker import run_pregame_worker as fn

    params = set(inspect.signature(fn).parameters)
    assert params == {
        "supabase_client",
        "the_odds_api_client",
        "the_odds_api_key",
        "sportsdataio_client",
        "sportsdataio_api_key",
        "weatherapi_client",
        "weatherapi_key",
        "cache_backend",
        "now",
        "triggered_game_ids",
        "odds_adapter",
        "player_props_adapter",
        "injury_adapter",
        "weather_adapter",
    }
