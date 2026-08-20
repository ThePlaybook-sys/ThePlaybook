"""Tests for app.persistence.daily_game_intelligence (Milestone 4.1)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.daily_game_intelligence import (
    DailyGameIntelligenceReadError,
    read_daily_game_intelligence,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_read_full_row_preserves_every_populated_category():
    row = {
        "game_id": "g1",
        "teams": {"home": "KC", "away": "BAL"},
        "players": {"KC": [{"player_name": "Demo QB"}]},
        "odds": {"value": {"home": -120, "away": 100}, "source": "the_odds_api", "last_updated": "2026-08-20T12:00:00+00:00", "status": "fresh"},
        "props": {"value": {"line": 1.5}, "source": "the_odds_api", "last_updated": "2026-08-20T12:00:00+00:00", "status": "fresh"},
        "weather": {"value": {"conditions": "clear"}, "source": "weatherapi", "last_updated": "2026-08-20T12:00:00+00:00", "status": "needs_refresh"},
        "injuries": {"value": [{"status": "questionable"}], "source": "sportsdataio", "last_updated": "2026-08-20T12:00:00+00:00", "status": "fresh"},
        "news": {"value": [], "source": "newsapi", "last_updated": "2026-08-20T12:00:00+00:00", "status": "fresh"},
        "rest": {"rest_days": 7, "season_opener": False},
        "stadium": {"name": "Arrowhead Stadium", "latitude": 39.0489, "longitude": -94.4839, "venue_type": "outdoor"},
        "travel": None,
        "public_betting": None,
        "sharp_money": None,
        "ai_scores": None,
        "momentum": None,
        "matchup_ratings": None,
        "ev_calculations": None,
        "confidence_scores": None,
        "recommendation_candidates": None,
        "last_updated": "2026-08-20T12:00:00+00:00",
    }
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[row]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_daily_game_intelligence(client, _headers(), game_id="g1")
    assert result == row
    # Populated categories are returned exactly as stored -- no confidence
    # key required or fabricated.
    assert "confidence" not in result["odds"]
    assert result["odds"]["status"] == "fresh"


@pytest.mark.asyncio
@respx.mock
async def test_null_categories_are_preserved_as_none_never_defaulted():
    row = {
        "game_id": "g1",
        "travel": None,
        "public_betting": None,
        "sharp_money": None,
        "injuries": None,
    }
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[row]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_daily_game_intelligence(client, _headers(), game_id="g1")
    assert result["travel"] is None
    assert result["public_betting"] is None
    assert result["sharp_money"] is None
    assert result["injuries"] is None


@pytest.mark.asyncio
@respx.mock
async def test_partial_row_missing_columns_still_reads():
    """A row with only a subset of categories populated (matching what a
    real, not-yet-fully-refreshed daily_game_intelligence row can
    legitimately look like) reads correctly -- no assumption that every
    category key is present."""
    row = {"game_id": "g2", "teams": {"home": "SEA", "away": "NE"}, "odds": None}
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[row]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_daily_game_intelligence(client, _headers(), game_id="g2")
    assert result["teams"] == {"home": "SEA", "away": "NE"}
    assert result["odds"] is None


@pytest.mark.asyncio
@respx.mock
async def test_returns_none_when_no_row_exists():
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_daily_game_intelligence(client, _headers(), game_id="does-not-exist")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_raises_on_supabase_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(DailyGameIntelligenceReadError):
            await read_daily_game_intelligence(client, _headers(), game_id="g1")


@pytest.mark.asyncio
@respx.mock
async def test_requests_full_row_select_star():
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await read_daily_game_intelligence(client, _headers(), game_id="g1")
    request = respx.calls.last.request
    assert request.url.params["select"] == "*"
    assert request.url.params["game_id"] == "eq.g1"
