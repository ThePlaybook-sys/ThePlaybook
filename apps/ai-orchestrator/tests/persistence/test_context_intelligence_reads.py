"""Tests for app.persistence.context_intelligence_reads (Phase 8.1
Foundation Pass), proven against a mocked PostgREST -- same discipline
as test_market_integrity_persistence.py."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.context_intelligence_reads import (
    ContextIntelligenceReadError,
    read_all_odds_snapshots,
    read_all_weather_snapshots,
    read_game_venue_context,
    read_games_sharing_venue,
    read_venue,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_read_all_weather_snapshots_returns_rows():
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(
        return_value=httpx.Response(200, json=[{"game_id": "g1", "weather_data": {}, "captured_at": "2026-09-07T00:00:00Z"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_all_weather_snapshots(client, _headers())
    assert len(rows) == 1


@pytest.mark.asyncio
@respx.mock
async def test_read_all_weather_snapshots_raises_on_non_200():
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ContextIntelligenceReadError):
            await read_all_weather_snapshots(client, _headers())


@pytest.mark.asyncio
@respx.mock
async def test_read_all_odds_snapshots_returns_rows():
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(
        return_value=httpx.Response(200, json=[{"game_id": "g1", "sportsbook": "dk", "market_type": "spread", "line_data": {}, "captured_at": "2026-09-07T00:00:00Z"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_all_odds_snapshots(client, _headers())
    assert len(rows) == 1


@pytest.mark.asyncio
@respx.mock
async def test_read_game_venue_context_returns_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g1", "venue_id": "v1", "venue_type": "outdoor"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        game = await read_game_venue_context(client, _headers(), game_id="g1")
    assert game["id"] == "g1"


@pytest.mark.asyncio
@respx.mock
async def test_read_game_venue_context_returns_none_when_missing():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        game = await read_game_venue_context(client, _headers(), game_id="missing")
    assert game is None


@pytest.mark.asyncio
@respx.mock
async def test_read_venue_returns_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/venues").mock(
        return_value=httpx.Response(200, json=[{"id": "v1", "name": "Lumen Field"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        venue = await read_venue(client, _headers(), venue_id="v1")
    assert venue["name"] == "Lumen Field"


@pytest.mark.asyncio
@respx.mock
async def test_read_games_sharing_venue_returns_rows():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g2", "scheduled_start": "2026-09-14T17:00:00Z"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_games_sharing_venue(client, _headers(), venue_id="v1", exclude_game_id="g1")
    assert len(rows) == 1
