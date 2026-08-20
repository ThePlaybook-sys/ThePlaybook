"""Focused tests for the adapter-injection seam added to every worker
entrypoint (approved corrective change, preceding DEMO-3's own scope).

This is a general dependency-injection improvement to the existing worker
architecture -- enabling Demo Mode, deterministic testing, and future
vendor substitution -- not Demo-specific business logic. These tests prove
the seam is purely additive: every existing caller (no adapter argument)
behaves exactly as before, and a caller that does inject an adapter gets
that adapter used in place of the real vendor construction, with zero
change to result shape, persistence path, or credential requirements
otherwise.

Odds Worker is used as the representative single-adapter case (points
1-6 of the approved testing list); Pregame/Postgame get their own
dedicated tests since they wire more than one injectable adapter through
a call graph (points 8-9).
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.demo.adapters import (
    DemoInjuryAdapter,
    DemoOddsAdapter,
    DemoPlayerPropsAdapter,
    DemoScheduleAdapter,
    DemoWeatherAdapter,
)
from app.workers.odds_worker import OddsWorkerResult, run_odds_worker
from app.workers.postgame_worker import run_postgame_worker
from app.workers.pregame_worker import run_pregame_worker
from tests.adapters.the_odds_api_fixtures import load

SUPABASE_URL = "https://test-project.supabase.co"
ODDS_API_URL = "https://api.the-odds-api.com"
ODDS_URL = f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/odds"
UNREACHABLE_URL = "https://this-host-must-never-be-contacted.invalid"

DB_GAME_1 = "db-game-1"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _game_row(*, game_id: str = DB_GAME_1, scheduled_start: str = "2026-09-14T17:00:00Z") -> dict:
    return {
        "id": game_id,
        "external_provider_id": None,
        "home_team": "KC",
        "away_team": "BAL",
        "scheduled_start": scheduled_start,
        "stadium": "Some Stadium",
        "status": "scheduled",
        "season_type": "regular",
        "week": 2,
    }


def _mock_games(games=None):
    games = games if games is not None else [_game_row()]
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=games))


def _mock_odds_snapshots_insert():
    return respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))


def _mock_game_provider_ids_linked():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": DB_GAME_1, "provider_game_id": "demo-game-1"}])
    )


def _mock_season(*, year: int = 2026):
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(
        return_value=httpx.Response(200, json=[{"id": "league-nfl"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(
            200, json=[{"year": year, "start_date": f"{year}-09-01", "end_date": f"{year + 1}-02-15"}]
        )
    )


def _mock_team_provider_ids():
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"team_id": "t-kc", "provider_team_id": "Kansas City Chiefs"},
                {"team_id": "t-bal", "provider_team_id": "Baltimore Ravens"},
            ],
        )
    )


# ---------------------------------------------------------------------------
# 1/2/3 -- no adapter injected vs. adapter injected (Odds Worker)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_no_adapter_injected_real_adapter_is_constructed_and_calls_the_real_endpoint(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids()
    _mock_game_provider_ids_linked()
    _mock_odds_snapshots_insert()
    odds_route = respx.get(ODDS_URL).mock(return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json")))

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
        )

    # Unchanged existing behavior: the real adapter was constructed and hit
    # the real endpoint exactly as it always has. (status is "partial", not
    # "success", only because this test's minimal 1-game mock doesn't cover
    # every game the multi-game fixture response contains -- irrelevant to
    # what this test actually proves.)
    assert odds_route.call_count == 1
    assert result.status in {"success", "partial"}


@pytest.mark.asyncio
@respx.mock
async def test_injected_demo_adapter_is_used_instead_and_the_real_endpoint_is_never_contacted(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_game_provider_ids_linked()
    insert_route = _mock_odds_snapshots_insert()
    # Deliberately NOT mocking ODDS_URL at all -- if the real adapter were
    # ever constructed and called, respx would raise for the unmocked
    # route, failing this test loudly rather than silently passing.

    injected_line_data = {"home": -999, "away": 999}  # distinctive, unmistakable value
    demo_adapter = DemoOddsAdapter(
        odds_by_game={
            "demo-game-1": [
                _demo_odds_line(injected_line_data),
            ]
        }
    )

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)

    # Dummy client pointed at a host with no respx route registered, and a
    # nonsense key -- proving the injected adapter path never touches
    # either (point 6: no real credential required).
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=UNREACHABLE_URL
    ) as unused_odds_client:
        result = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=unused_odds_client,
            the_odds_api_key="not-a-real-key",
            now=now,
            odds_adapter=demo_adapter,
        )

    assert result.status == "success"
    assert result.lines_persisted == 1
    persisted_row = insert_route.calls[0].request.content
    assert b"-999" in persisted_row  # the injected data, not any real-adapter fixture data


def _demo_odds_line(line_data: dict):
    from datetime import datetime as _dt

    from app.adapters.models import OddsLine

    return OddsLine(
        game_external_id="demo-game-1", home_team="Demo Hawks", away_team="Demo Wolves",
        commence_time=_dt(2026, 9, 14, 17, 0, tzinfo=timezone.utc), sportsbook="DemoBook",
        market_type="moneyline", line_data=line_data,
    )


# ---------------------------------------------------------------------------
# 4 -- result shape unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_result_shape_is_identical_regardless_of_adapter_source(monkeypatch):
    import dataclasses

    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids()
    _mock_game_provider_ids_linked()
    _mock_odds_snapshots_insert()
    respx.get(ODDS_URL).mock(return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json")))
    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        real_result = await run_odds_worker(
            supabase_client=supabase_client, the_odds_api_client=odds_client,
            the_odds_api_key="test-key", now=now,
        )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=UNREACHABLE_URL
    ) as unused_client:
        demo_result = await run_odds_worker(
            supabase_client=supabase_client, the_odds_api_client=unused_client,
            the_odds_api_key="unused", now=now,
            odds_adapter=DemoOddsAdapter(odds_by_game={"demo-game-1": [_demo_odds_line({"home": -110})]}),
        )

    assert isinstance(real_result, OddsWorkerResult)
    assert isinstance(demo_result, OddsWorkerResult)
    assert {f.name for f in dataclasses.fields(real_result)} == {f.name for f in dataclasses.fields(demo_result)}


# ---------------------------------------------------------------------------
# 5/6 -- credential requirements: real path needs one, demo path doesn't
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_real_adapter_path_fails_without_a_working_provider_endpoint(monkeypatch):
    """Proves point 5 the other direction: the real path is NOT
    magically credential-free -- a broken/unauthorized real endpoint still
    produces a failed provider fetch, same as before this seam existed."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_game_provider_ids_linked()
    respx.get(ODDS_URL).mock(return_value=httpx.Response(401))
    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_odds_worker(
            supabase_client=supabase_client, the_odds_api_client=odds_client,
            the_odds_api_key="bad-key", now=now,
        )

    assert result.status == "failed"


# ---------------------------------------------------------------------------
# 8 -- Pregame Worker passes injected adapters through to its 4 delegates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_pregame_worker_passes_injected_adapters_through_to_delegated_workers(monkeypatch):
    _headers_env(monkeypatch)
    now = datetime(2026, 9, 14, 16, 55, tzinfo=timezone.utc)  # 5 minutes before kickoff -> RAMP_5M
    game = _game_row(scheduled_start="2026-09-14T17:00:00Z")
    _mock_season()
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[game]))
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": DB_GAME_1, "provider_game_id": "demo-game-1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(201))
    respx.patch(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(200, json=[]))

    demo_odds = DemoOddsAdapter(odds_by_game={"demo-game-1": [_demo_odds_line({"home": -105})]})
    demo_props = DemoPlayerPropsAdapter(props_by_game={})
    demo_injury = DemoInjuryAdapter(injuries=[])
    demo_weather = DemoWeatherAdapter()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=UNREACHABLE_URL
    ) as unused_client:
        result = await run_pregame_worker(
            supabase_client=supabase_client,
            the_odds_api_client=unused_client, the_odds_api_key="unused",
            sportsdataio_client=unused_client, sportsdataio_api_key="unused",
            weatherapi_client=unused_client, weatherapi_key="unused",
            now=now,
            odds_adapter=demo_odds, player_props_adapter=demo_props,
            injury_adapter=demo_injury, weather_adapter=demo_weather,
        )

    # No respx route exists for UNREACHABLE_URL at all -- if any delegated
    # worker had constructed its real adapter instead of using the
    # injected one, this call would have raised, not returned a result.
    assert result.games_triggered == [DB_GAME_1]


# ---------------------------------------------------------------------------
# 9 -- Postgame Worker's delegated fetch paths receive injected adapters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_postgame_worker_schedule_adapter_injection_skips_the_real_endpoint(monkeypatch):
    """Scoped to the schedule-re-poll half (`_detect_newly_final_games`) --
    the smallest slice of Postgame Worker that proves the injection seam
    reaches a private helper, not just the public entrypoint."""
    _headers_env(monkeypatch)
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    _mock_season()
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))

    demo_schedule = DemoScheduleAdapter(schedule=[])

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=UNREACHABLE_URL
    ) as unused_client:
        result = await run_postgame_worker(
            supabase_client=supabase_client,
            sportsdataio_client=unused_client, sportsdataio_api_key="unused",
            now=now,
            schedule_adapter=demo_schedule,
        )

    # No respx route exists for UNREACHABLE_URL -- reaching a "success"
    # result (rather than a connection error) proves the injected
    # DemoScheduleAdapter, not SportsDataIOScheduleAdapter, was used.
    assert result.status == "success"
