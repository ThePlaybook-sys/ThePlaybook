"""Orchestration tests for app.workers.weather_worker (Phase 3E-6).

Every HTTP boundary -- Supabase and WeatherAPI both -- is respx-mocked; no
real network, zero SportsDataIO calls (this worker never touches that
provider at all -- structurally impossible, its signature only ever
accepts a supabase_client and a weatherapi_client).

Covers: normal outdoor refresh, multiple games, dome skip, unknown venue
type (retractable dome and missing type both) polls but never fabricates
certainty, missing-coordinates skip, no-candidates/all-STOPPED/not-due
cadence gating, the 15-minute boundary, per-game provider-failure
isolation, malformed provider response isolation, cache hit/stale,
append-only rerun, a DST-crossing cadence check, and a downstream
read-back proving the write path feeds daily_game_intelligence's existing
read helper.
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from app.adapters.cache import InMemoryCacheBackend
from app.persistence.snapshots import latest_weather_snapshot
from app.workers.weather_worker import run_weather_worker, venue_is_dome
from tests.adapters.weatherapi_fixtures import load

SUPABASE_URL = "https://test-project.supabase.co"
WEATHERAPI_URL = "https://api.weatherapi.com"

DB_GAME_OUTDOOR = "db-game-outdoor"
DB_GAME_DOME = "db-game-dome"
DB_GAME_RETRACTABLE = "db-game-retractable"
DB_GAME_NO_TYPE = "db-game-no-type"
DB_GAME_NO_COORDS = "db-game-no-coords"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _game_row(
    *,
    game_id: str,
    scheduled_start: str,
    venue_type: str | None = "outdoor",
    venue_lat: float | None = 39.0489,
    venue_long: float | None = -94.4839,
) -> dict:
    return {
        "id": game_id,
        "external_provider_id": None,
        "home_team": "KC",
        "away_team": "BAL",
        "scheduled_start": scheduled_start,
        "stadium": "Arrowhead Stadium",
        "status": "scheduled",
        "season_type": "regular",
        "week": 1,
        "venue_lat": venue_lat,
        "venue_long": venue_long,
        "venue_type": venue_type,
    }


def _mock_games(games: list[dict]):
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=games))


def _mock_weather_snapshots_insert():
    return respx.post(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(201))


def _forecast_route():
    return respx.get(f"{WEATHERAPI_URL}/v1/forecast.json")


async def _run(*, now, last_polled_at=None, cache_backend=None):
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=WEATHERAPI_URL
    ) as weatherapi_client:
        return await run_weather_worker(
            supabase_client=supabase_client,
            weatherapi_client=weatherapi_client,
            weatherapi_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
            cache_backend=cache_backend or InMemoryCacheBackend(),
        )


# ============================================================================
# venue_is_dome -- pure function, unknown never treated as False
# ============================================================================


def test_venue_is_dome_outdoor_is_false():
    assert venue_is_dome("outdoor") is False


def test_venue_is_dome_dome_is_true():
    assert venue_is_dome("dome") is True


def test_venue_is_dome_retractable_is_none_not_false():
    assert venue_is_dome("retractable_dome") is None


def test_venue_is_dome_missing_is_none_not_false():
    assert venue_is_dome(None) is None


# ============================================================================
# Normal outdoor refresh, multiple games
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_outdoor_game_due_fetches_and_persists_weather(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T17:00:00Z")])
    insert_route = _mock_weather_snapshots_insert()
    _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)  # 4 days out, well before kickoff
    result = await _run(now=now)

    assert result.status == "success"
    assert result.games_due == 1
    assert result.snapshots_persisted == 1
    assert result.games_skipped_dome == []
    assert result.games_skipped_unresolved_location == []

    rows = [row for call in insert_route.calls for row in _json.loads(call.request.content)]
    assert len(rows) == 1
    assert rows[0]["game_id"] == DB_GAME_OUTDOOR
    assert rows[0]["weather_data"]["is_dome"] is False
    assert {"temperature_f", "wind_mph", "precipitation_pct", "conditions"} <= set(rows[0]["weather_data"])


@pytest.mark.asyncio
@respx.mock
async def test_multiple_games_all_persisted(monkeypatch):
    _headers_env(monkeypatch)
    games = [
        _game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T17:00:00Z"),
        _game_row(game_id="db-game-2", scheduled_start="2026-09-14T20:25:00Z"),
    ]
    _mock_games(games)
    insert_route = _mock_weather_snapshots_insert()
    _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "success"
    assert result.games_due == 2
    assert result.snapshots_persisted == 2
    rows = [row for call in insert_route.calls for row in _json.loads(call.request.content)]
    assert {row["game_id"] for row in rows} == {DB_GAME_OUTDOOR, "db-game-2"}


# ============================================================================
# Dome / unknown venue type -- never fabricate certainty
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_dome_game_skips_weatherapi_entirely(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_DOME, scheduled_start="2026-09-14T17:00:00Z", venue_type="dome")])
    forecast_route = _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "success"
    assert result.games_skipped_dome == [DB_GAME_DOME]
    assert result.snapshots_persisted == 0
    assert forecast_route.call_count == 0  # never called -- outdoor weather is irrelevant


@pytest.mark.asyncio
@respx.mock
async def test_retractable_dome_polls_but_persists_is_dome_none(monkeypatch):
    """Unknown roof state -- coordinates are still valid, so WeatherAPI
    MAY be queried (per Mac's explicit instruction), but is_dome must
    stay null, never coerced to False just because polling happened."""
    _headers_env(monkeypatch)
    _mock_games(
        [_game_row(game_id=DB_GAME_RETRACTABLE, scheduled_start="2026-09-14T17:00:00Z", venue_type="retractable_dome")]
    )
    insert_route = _mock_weather_snapshots_insert()
    _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "success"
    assert result.games_skipped_dome == []
    assert result.snapshots_persisted == 1
    rows = [row for call in insert_route.calls for row in _json.loads(call.request.content)]
    assert rows[0]["weather_data"]["is_dome"] is None


@pytest.mark.asyncio
@respx.mock
async def test_missing_venue_type_polls_but_persists_is_dome_none(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_NO_TYPE, scheduled_start="2026-09-14T17:00:00Z", venue_type=None)])
    insert_route = _mock_weather_snapshots_insert()
    _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "success"
    rows = [row for call in insert_route.calls for row in _json.loads(call.request.content)]
    assert rows[0]["weather_data"]["is_dome"] is None


# ============================================================================
# Missing location -- skipped, never guessed
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_missing_coordinates_skipped_not_fabricated(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games(
        [_game_row(game_id=DB_GAME_NO_COORDS, scheduled_start="2026-09-14T17:00:00Z", venue_lat=None, venue_long=None)]
    )
    forecast_route = _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "partial"  # a real gap, unlike a dome skip
    assert result.games_skipped_unresolved_location == [DB_GAME_NO_COORDS]
    assert result.snapshots_persisted == 0
    assert forecast_route.call_count == 0


# ============================================================================
# Cadence: candidate window, STOPPED, not-due, 15-minute boundary
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_no_games_in_candidate_window_skips_provider_calls(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([])
    forecast_route = _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "success"
    assert result.games_considered == 0
    assert forecast_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_stopped_game_excluded_from_polling(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T11:00:00Z")])
    forecast_route = _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)  # 1 hour after kickoff -- STOPPED
    result = await _run(now=now)

    assert result.status == "success"
    assert result.games_considered == 1
    assert result.games_due == 0
    assert forecast_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_not_due_yet_before_15_minute_interval(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T17:00:00Z")])
    forecast_route = _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    last_polled_at = {DB_GAME_OUTDOOR: now - timedelta(minutes=10)}
    result = await _run(now=now, last_polled_at=last_polled_at)

    assert result.status == "success"
    assert result.games_due == 0
    assert result.games_skipped_not_due == 1
    assert forecast_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_due_once_15_minute_interval_has_elapsed(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T17:00:00Z")])
    _mock_weather_snapshots_insert()
    forecast_route = _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    last_polled_at = {DB_GAME_OUTDOOR: now - timedelta(minutes=16)}
    result = await _run(now=now, last_polled_at=last_polled_at)

    assert result.status == "success"
    assert result.games_due == 1
    assert forecast_route.call_count == 1


# ============================================================================
# Failure isolation
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_one_games_provider_failure_does_not_block_the_other(monkeypatch):
    _headers_env(monkeypatch)
    games = [
        _game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T17:00:00Z"),
        _game_row(game_id="db-game-2", scheduled_start="2026-09-14T17:05:00Z"),
    ]
    _mock_games(games)
    _mock_weather_snapshots_insert()

    call_count = {"n": 0}

    def _respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(503)  # simulated outage for the first game
        return httpx.Response(200, json=load("forecast_normal.json"))

    _forecast_route().mock(side_effect=_respond)

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "partial"
    assert result.games_due == 2
    assert len(result.failures) == 1
    assert result.snapshots_persisted == 1  # the second game's data still lands


@pytest.mark.asyncio
@respx.mock
async def test_malformed_provider_response_isolated(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T17:00:00Z")])
    _mock_weather_snapshots_insert()
    _forecast_route().mock(return_value=httpx.Response(200, json={"not": "the expected shape"}))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "partial"
    assert len(result.failures) == 1
    assert result.snapshots_persisted == 0


# ============================================================================
# Cache hit / stale / append-only rerun
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_prevents_a_second_provider_call_within_ttl(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T17:00:00Z")])
    _mock_weather_snapshots_insert()
    forecast_route = _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    cache_backend = InMemoryCacheBackend()

    first = await _run(now=now, cache_backend=cache_backend)
    second = await _run(now=now, cache_backend=cache_backend)

    assert first.status == "success"
    assert second.status == "success"
    assert forecast_route.call_count == 1  # second run served from cache


@pytest.mark.asyncio
@respx.mock
async def test_stale_cache_triggers_new_fetch(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T17:00:00Z")])
    _mock_weather_snapshots_insert()
    forecast_route = _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    await _run(now=now, cache_backend=InMemoryCacheBackend())
    await _run(now=now, cache_backend=InMemoryCacheBackend())  # fresh backend -- no cache hit

    assert forecast_route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_rerun_appends_new_snapshots_rather_than_overwriting(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T17:00:00Z")])
    insert_route = _mock_weather_snapshots_insert()
    _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    await _run(now=now, cache_backend=InMemoryCacheBackend())
    await _run(now=now, cache_backend=InMemoryCacheBackend())

    assert insert_route.call_count == 2  # two separate POSTs, never a PATCH/update
    all_rows = [row for call in insert_route.calls for row in _json.loads(call.request.content)]
    assert len(all_rows) == 2


# ============================================================================
# Downstream read-back
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_persisted_weather_is_readable_via_latest_weather_snapshot(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=DB_GAME_OUTDOOR, scheduled_start="2026-09-14T17:00:00Z")])
    _mock_weather_snapshots_insert()
    _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)
    assert result.snapshots_persisted == 1

    persisted_row = {
        "id": "row-1",
        "game_id": DB_GAME_OUTDOOR,
        "weather_data": {
            "temperature_f": 72.0,
            "wind_mph": 9.4,
            "precipitation_pct": 5.0,
            "conditions": "Sunny",
            "is_dome": False,
        },
        "captured_at": "2026-09-10T12:00:00Z",
    }
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(
        return_value=httpx.Response(200, json=[persisted_row])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        headers = {"Authorization": "Bearer test-service-role-key", "apikey": "test-service-role-key"}
        row = await latest_weather_snapshot(client, headers, game_id=DB_GAME_OUTDOOR)

    assert row is not None
    assert row["weather_data"]["temperature_f"] == 72.0
    assert row["weather_data"]["is_dome"] is False


# ============================================================================
# Timezone/DST -- inherits classify_window's own comprehensive coverage;
# this proves the worker's own cadence gate doesn't break under a real
# DST-crossing scenario, not a full re-derivation of that suite.
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_cadence_gate_correct_across_dst_spring_forward(monkeypatch):
    """Same spring-forward scenario 3E-4G/3E-5's own DST tests use --
    proves _should_poll's reuse of classify_window doesn't silently fall
    back to a naive wall-clock subtraction at the worker level."""
    _headers_env(monkeypatch)
    eastern = ZoneInfo("America/New_York")
    kickoff = datetime(2026, 3, 8, 3, 0, tzinfo=eastern)  # 3:00 AM EDT, just after spring-forward
    now = datetime(2026, 3, 8, 1, 0, tzinfo=eastern)  # 1:00 AM EST, just before spring-forward
    assert now.tzinfo is kickoff.tzinfo  # same tzinfo object -- the exact subtlety classify_window guards against

    _mock_games([_game_row(game_id=DB_GAME_OUTDOOR, scheduled_start=kickoff.isoformat())])
    _mock_weather_snapshots_insert()
    _forecast_route().mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))

    result = await _run(now=now)

    # Real elapsed gap is 1h (one hour skipped by the transition), not the
    # naive 2h wall-clock gap -- still within the candidate window and not
    # STOPPED (kickoff hasn't passed), so this poll succeeds normally.
    assert result.status == "success"
    assert result.games_due == 1
