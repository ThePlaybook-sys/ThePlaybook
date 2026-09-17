"""Tests for app.persistence.games (Milestone 4.9)."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.persistence.games import GamesReadError, read_eligible_game_ids

SUPABASE_URL = "https://test-project.supabase.co"

#: The eligibility contract became time-bounded on 2026-09-17 (the 7-day
#: recommendation horizon), so every call now needs an explicit `now`.
#: Fixed rather than wall-clock, so these tests cannot rot.
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_returns_ids_of_scheduled_games_only():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g1"}, {"id": "g2"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_eligible_game_ids(client, _headers(), now=NOW)
    assert result == ["g1", "g2"]
    assert route.calls.last.request.url.params["status"] == "eq.scheduled"


@pytest.mark.asyncio
@respx.mock
async def test_returns_empty_list_when_none_scheduled():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_eligible_game_ids(client, _headers(), now=NOW)
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_raises_on_non_200():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(GamesReadError):
            await read_eligible_game_ids(client, _headers(), now=NOW)
