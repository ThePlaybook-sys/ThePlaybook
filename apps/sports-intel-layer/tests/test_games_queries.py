"""Tests for app.persistence.games (Phase 3E-2)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest
import respx

from app.persistence.games import GamesQueryError, find_previous_final_game, list_games_in_window

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_find_previous_final_game_returns_row():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g0", "home_team": "SEA", "away_team": "NE"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await find_previous_final_game(
            client, _headers(), team="SEA", before=datetime(2026, 9, 17, tzinfo=timezone.utc)
        )
    assert result == {"id": "g0", "home_team": "SEA", "away_team": "NE"}
    request = route.calls.last.request
    assert request.url.params["status"] == "eq.final"


@pytest.mark.asyncio
@respx.mock
async def test_find_previous_final_game_none_when_season_opener():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await find_previous_final_game(
            client, _headers(), team="SEA", before=datetime(2026, 9, 10, tzinfo=timezone.utc)
        )
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_find_previous_final_game_raises_on_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(GamesQueryError):
            await find_previous_final_game(
                client, _headers(), team="SEA", before=datetime(2026, 9, 10, tzinfo=timezone.utc)
            )


@pytest.mark.asyncio
@respx.mock
async def test_list_games_in_window_returns_rows():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g1"}, {"id": "g2"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await list_games_in_window(
            client, _headers(), start=date(2026, 9, 9), end=date(2026, 9, 16)
        )
    assert len(result) == 2
