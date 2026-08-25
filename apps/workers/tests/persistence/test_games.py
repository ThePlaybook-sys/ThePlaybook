"""Tests for app.persistence.games (Milestone 4.9)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.games import GamesReadError, read_eligible_game_ids

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_returns_ids_of_scheduled_games_only():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g1"}, {"id": "g2"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_eligible_game_ids(client, _headers())
    assert result == ["g1", "g2"]
    assert route.calls.last.request.url.params["status"] == "eq.scheduled"


@pytest.mark.asyncio
@respx.mock
async def test_returns_empty_list_when_none_scheduled():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_eligible_game_ids(client, _headers())
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_raises_on_non_200():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(GamesReadError):
            await read_eligible_game_ids(client, _headers())
