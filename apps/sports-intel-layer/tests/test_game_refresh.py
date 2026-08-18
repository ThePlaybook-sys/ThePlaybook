"""Tests for app.master_refresh.game_refresh (Phase 3F-3's stadium
venue-surfacing addition, plus the pre-existing shared per-game refresh
behavior from 3E-2/3E-8).

`_build_stadium` is the one new piece of logic this phase adds -- pure,
directly unit-tested here. `refresh_daily_game_intelligence_for_game` is
the single shared assembly path both Master Refresh (run.py) and Pregame
Worker (pregame_worker.py) call -- proven once here that it wires
`_build_stadium`'s output into the upserted payload; test_master_refresh.py
and test_pregame_worker.py each add one assertion confirming their own
call site actually goes through this same function, not a duplicate.
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.master_refresh.game_refresh import _build_stadium, refresh_daily_game_intelligence_for_game

SUPABASE_URL = "https://test-project.supabase.co"


def test_stadium_includes_name_lat_long_type_when_all_present():
    game = {"stadium": "Lumen Field", "venue_lat": 47.5952, "venue_long": -122.3316, "venue_type": "outdoor"}
    assert _build_stadium(game) == {
        "name": "Lumen Field", "latitude": 47.5952, "longitude": -122.3316, "venue_type": "outdoor",
    }


def test_stadium_preserves_null_for_individually_missing_fields():
    """Real, partial current-state: name known, coordinates not yet
    captured -- each missing field stays None, never fabricated or
    defaulted to 0/empty string."""
    game = {"stadium": "Lumen Field", "venue_lat": None, "venue_long": None, "venue_type": None}
    assert _build_stadium(game) == {"name": "Lumen Field", "latitude": None, "longitude": None, "venue_type": None}


def test_stadium_is_none_when_nothing_at_all_is_known():
    game = {"stadium": None, "venue_lat": None, "venue_long": None, "venue_type": None}
    assert _build_stadium(game) is None


def test_stadium_is_none_when_venue_fields_absent_from_dict_entirely():
    """A caller-supplied game dict missing the venue keys altogether
    (rather than explicit None) -- .get() defaults, same result as
    explicit None, never a KeyError."""
    assert _build_stadium({}) is None


@pytest.mark.parametrize("venue_type", ["dome", "retractable_dome", "outdoor"])
def test_stadium_passes_through_every_venue_type_value_unchanged(venue_type):
    game = {"stadium": "Test Stadium", "venue_lat": 1.0, "venue_long": 2.0, "venue_type": venue_type}
    assert _build_stadium(game)["venue_type"] == venue_type


@pytest.mark.asyncio
@respx.mock
async def test_refresh_daily_game_intelligence_for_game_writes_full_venue_shape(monkeypatch):
    """The shared per-game refresh path -- used by both Master Refresh and
    Pregame Worker -- upserts the new venue shape, not just `name`."""
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))  # find_previous_final_game, both sides
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    upsert_route = respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))

    game = {
        "id": "game-1", "home_team": "SEA", "away_team": "NE",
        "scheduled_start": datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc).isoformat(),
        "stadium": "Lumen Field", "venue_lat": 47.5952, "venue_long": -122.3316, "venue_type": "outdoor",
    }

    await refresh_daily_game_intelligence_for_game(
        httpx.AsyncClient(base_url=SUPABASE_URL), {"Authorization": "Bearer x", "apikey": "x"}, game,
    )

    body = _json.loads(upsert_route.calls.last.request.content)
    assert body["stadium"] == {
        "name": "Lumen Field", "latitude": 47.5952, "longitude": -122.3316, "venue_type": "outdoor",
    }


@pytest.mark.asyncio
@respx.mock
async def test_refresh_daily_game_intelligence_never_fabricates_missing_venue_data(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    upsert_route = respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))

    # A game whose venue_lat/venue_long/venue_type haven't been captured
    # yet (pre-3E-6 row, or a provider that never supplied them).
    game = {
        "id": "game-1", "home_team": "SEA", "away_team": "NE",
        "scheduled_start": datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc).isoformat(),
        "stadium": "Lumen Field", "venue_lat": None, "venue_long": None, "venue_type": None,
    }

    await refresh_daily_game_intelligence_for_game(
        httpx.AsyncClient(base_url=SUPABASE_URL), {"Authorization": "Bearer x", "apikey": "x"}, game,
    )

    body = _json.loads(upsert_route.calls.last.request.content)
    assert body["stadium"] == {"name": "Lumen Field", "latitude": None, "longitude": None, "venue_type": None}
    # Phase 4/5 fields remain untouched by this change, same as always.
    assert {"ai_scores", "momentum", "matchup_ratings", "ev_calculations", "confidence_scores", "recommendation_candidates"}.isdisjoint(body.keys())
