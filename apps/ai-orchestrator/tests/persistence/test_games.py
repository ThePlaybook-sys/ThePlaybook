"""Tests for app.persistence.games (Milestone 4.1, Decision 7 eligibility)."""
from __future__ import annotations

import httpx
import pytest
import respx

from datetime import datetime, timezone

from app.persistence.games import (
    GamesReadError,
    GameStatusUnrecognizedError,
    check_pregame_workflow_eligibility,
    find_previous_final_game,
    get_game,
    is_pregame_workflow_eligible,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _game(status: str) -> dict:
    return {"id": "g1", "status": status, "home_team": "KC", "away_team": "BAL"}


# --- pure eligibility logic ---


def test_scheduled_is_eligible():
    assert is_pregame_workflow_eligible(_game("scheduled")) is True


@pytest.mark.parametrize("status", ["live", "final", "postponed", "canceled"])
def test_non_scheduled_statuses_are_ineligible(status):
    assert is_pregame_workflow_eligible(_game(status)) is False


def test_missing_status_raises():
    with pytest.raises(GameStatusUnrecognizedError):
        is_pregame_workflow_eligible({"id": "g1"})


def test_unrecognized_status_raises():
    with pytest.raises(GameStatusUnrecognizedError):
        is_pregame_workflow_eligible(_game("bogus"))


# --- get_game read ---


@pytest.mark.asyncio
@respx.mock
async def test_get_game_returns_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_game("scheduled")]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await get_game(client, _headers(), game_id="g1")
    assert result["status"] == "scheduled"


@pytest.mark.asyncio
@respx.mock
async def test_get_game_returns_none_when_missing():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await get_game(client, _headers(), game_id="does-not-exist")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_get_game_raises_on_supabase_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(GamesReadError):
            await get_game(client, _headers(), game_id="g1")


# --- check_pregame_workflow_eligibility: the safe, all-cases-covered entry point ---


@pytest.mark.asyncio
@respx.mock
async def test_eligibility_scheduled_game():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_game("scheduled")]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        eligible, reason = await check_pregame_workflow_eligibility(client, _headers(), game_id="g1")
    assert eligible is True
    assert reason == "eligible"


@pytest.mark.asyncio
@respx.mock
async def test_eligibility_live_game_rejected():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_game("live")]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        eligible, reason = await check_pregame_workflow_eligibility(client, _headers(), game_id="g1")
    assert eligible is False
    assert reason == "ineligible_status:live"


@pytest.mark.asyncio
@respx.mock
async def test_eligibility_final_game_rejected():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_game("final")]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        eligible, reason = await check_pregame_workflow_eligibility(client, _headers(), game_id="g1")
    assert eligible is False
    assert reason == "ineligible_status:final"


@pytest.mark.asyncio
@respx.mock
async def test_eligibility_postponed_game_rejected():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_game("postponed")]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        eligible, reason = await check_pregame_workflow_eligibility(client, _headers(), game_id="g1")
    assert eligible is False
    assert reason == "ineligible_status:postponed"


@pytest.mark.asyncio
@respx.mock
async def test_eligibility_canceled_game_rejected():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_game("canceled")]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        eligible, reason = await check_pregame_workflow_eligibility(client, _headers(), game_id="g1")
    assert eligible is False
    assert reason == "ineligible_status:canceled"


@pytest.mark.asyncio
@respx.mock
async def test_eligibility_missing_game_rejected_safely_not_an_exception():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        eligible, reason = await check_pregame_workflow_eligibility(client, _headers(), game_id="does-not-exist")
    assert eligible is False
    assert reason == "game_not_found"


@pytest.mark.asyncio
@respx.mock
async def test_eligibility_unrecognized_status_rejected_safely():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_game("bogus")]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        eligible, reason = await check_pregame_workflow_eligibility(client, _headers(), game_id="g1")
    assert eligible is False
    assert reason.startswith("invalid_status:")


# --- get_game's widened select (Milestone 4.4, Decision 5) ---


@pytest.mark.asyncio
@respx.mock
async def test_get_game_requests_venue_fields_in_select():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_game("scheduled")]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await get_game(client, _headers(), game_id="g1")
    select = route.calls.last.request.url.params["select"]
    for field in ("venue_lat", "venue_long", "stadium", "venue_type"):
        assert field in select


@pytest.mark.asyncio
@respx.mock
async def test_get_game_returns_venue_fields_when_present():
    row = {**_game("scheduled"), "venue_lat": 39.0489, "venue_long": -94.4839, "stadium": "Arrowhead Stadium", "venue_type": "outdoor"}
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[row]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await get_game(client, _headers(), game_id="g1")
    assert result["venue_lat"] == 39.0489
    assert result["stadium"] == "Arrowhead Stadium"


# --- find_previous_final_game (Milestone 4.4, Decision 5) ---


@pytest.mark.asyncio
@respx.mock
async def test_find_previous_final_game_returns_row():
    row = {"id": "g0", "home_team": "KC", "away_team": "DEN", "stadium": "Arrowhead Stadium", "venue_lat": 39.0489, "venue_long": -94.4839, "status": "final"}
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[row]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await find_previous_final_game(client, _headers(), team="KC", before=datetime(2026, 9, 21, tzinfo=timezone.utc))
    assert result == row
    request = route.calls.last.request
    assert request.url.params["status"] == "eq.final"


@pytest.mark.asyncio
@respx.mock
async def test_find_previous_final_game_none_when_season_opener():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await find_previous_final_game(client, _headers(), team="KC", before=datetime(2026, 9, 10, tzinfo=timezone.utc))
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_find_previous_final_game_raises_on_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(GamesReadError):
            await find_previous_final_game(client, _headers(), team="KC", before=datetime(2026, 9, 10, tzinfo=timezone.utc))
