"""Tests for app.agents.context (Milestone 4.4)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.agents.context import build_agent_context
from app.features.travel import TravelFeatures

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_build_agent_context_full_data():
    dgi_row = {
        "game_id": "g1",
        "injuries": {"value": [{"status": "questionable"}], "source": "sportsdataio", "status": "fresh"},
        "weather": {"value": {"conditions": "clear"}, "source": "weatherapi", "status": "fresh"},
        "rest": {"rest_days": 7, "season_opener": False},
        "stadium": {"name": "Highmark Stadium", "latitude": 42.7738, "longitude": -78.7870, "venue_type": "outdoor"},
    }
    game_row = {
        "id": "g1",
        "home_team": "BUF",
        "away_team": "KC",
        "scheduled_start": "2026-09-21T17:00:00+00:00",
        "venue_lat": 42.7738,
        "venue_long": -78.7870,
        "stadium": "Highmark Stadium",
        "venue_type": "outdoor",
    }
    previous_game_row = {
        "id": "g0",
        "home_team": "BUF",
        "away_team": "NE",
        "venue_lat": 42.7738,
        "venue_long": -78.7870,
        "stadium": "Highmark Stadium",
        "status": "final",
    }
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[dgi_row]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games", params={"status": "eq.final"}).mock(
        return_value=httpx.Response(200, json=[previous_game_row])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[game_row]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        context = await build_agent_context(client, _headers(), game_id="g1", correlation_id="corr-1")

    assert context.game_id == "g1"
    assert context.correlation_id == "corr-1"
    assert context.injuries == dgi_row["injuries"]
    assert context.weather == dgi_row["weather"]
    assert context.rest == dgi_row["rest"]
    assert context.stadium == dgi_row["stadium"]
    assert isinstance(context.travel, TravelFeatures)
    assert context.travel.travel_distance_miles == pytest.approx(0.0, abs=1e-6)  # same stadium as previous game


@pytest.mark.asyncio
@respx.mock
async def test_build_agent_context_missing_dgi_row_leaves_categories_none_not_defaulted():
    game_row = {
        "id": "g1",
        "home_team": "KC",
        "away_team": "BAL",
        "scheduled_start": "2026-09-21T17:00:00+00:00",
        "venue_lat": None,
        "venue_long": None,
        "stadium": None,
        "venue_type": None,
    }
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games", params={"status": "eq.final"}).mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[game_row]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        context = await build_agent_context(client, _headers(), game_id="g1", correlation_id="corr-1")

    assert context.injuries is None
    assert context.weather is None
    assert context.rest is None
    assert context.stadium is None
    assert context.travel.travel_distance_miles is None
    assert context.travel.timezone_shift_hours is None
