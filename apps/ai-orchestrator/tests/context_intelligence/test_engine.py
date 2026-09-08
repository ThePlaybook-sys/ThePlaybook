"""End-to-end test for app.context_intelligence.engine.
build_contextual_intelligence (Phase 8.1 Foundation Pass) -- every real
Supabase boundary respx-mocked, matching this package's own established
convention. Proves the full 10-dimension result shape assembles
correctly from real I/O, not just from the pure per-dimension functions
already covered by their own dedicated test files."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.context_intelligence.engine import SUPPORTED_DIMENSIONS, build_contextual_intelligence
from app.context_intelligence.unsupported import UNSUPPORTED_DIMENSIONS

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _mock_all_empty():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=[]))


@pytest.mark.asyncio
@respx.mock
async def test_result_always_covers_all_ten_dimensions_even_with_zero_real_data():
    _mock_all_empty()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await build_contextual_intelligence(client, _headers(), game_id="g1")

    expected = set(SUPPORTED_DIMENSIONS) | set(UNSUPPORTED_DIMENSIONS)
    assert set(result.dimensions.keys()) == expected
    assert result.game_id == "g1"
    # Every supported dimension is honestly insufficient-evidence when
    # nothing real exists for this game.
    for name in SUPPORTED_DIMENSIONS:
        assert result.dimensions[name].insufficient_evidence is True
    # Every unsupported dimension is present too -- never silently omitted.
    for name in UNSUPPORTED_DIMENSIONS:
        assert result.dimensions[name].insufficient_evidence is True


@pytest.mark.asyncio
@respx.mock
async def test_result_serializes_to_json_cleanly():
    _mock_all_empty()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await build_contextual_intelligence(client, _headers(), game_id="g1")
    payload = result.to_json()
    assert payload["game_id"] == "g1"
    assert set(payload["dimensions"].keys()) == set(SUPPORTED_DIMENSIONS) | set(UNSUPPORTED_DIMENSIONS)
    assert isinstance(payload["dimensions"]["weather"]["confounders"], list)


@pytest.mark.asyncio
@respx.mock
async def test_missing_weather_still_produces_full_result_for_other_dimensions():
    """A real game with real odds history but zero weather rows must
    still produce a complete result -- weather insufficient, market
    still computed from what's real."""
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g1", "home_team": "SEA", "away_team": "NE", "venue_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "game_id": "g1",
                    "sportsbook": "draftkings",
                    "market_type": "spread",
                    "line_data": {"outcomes": [{"name": "Home", "point": 3.0, "price": -110}]},
                    "captured_at": "2026-09-07T00:00:00Z",
                },
                {
                    "game_id": "g1",
                    "sportsbook": "draftkings",
                    "market_type": "spread",
                    "line_data": {"outcomes": [{"name": "Home", "point": 1.0, "price": -110}]},
                    "captured_at": "2026-09-08T00:00:00Z",
                },
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(
        return_value=httpx.Response(200, json=[{"id": "t1", "name": "SEA"}, {"id": "t2", "name": "NE"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await build_contextual_intelligence(client, _headers(), game_id="g1")

    assert result.dimensions["weather"].insufficient_evidence is True
    assert result.dimensions["venue"].insufficient_evidence is True  # no venue_id resolved
    # Market has real target history -- not a crash, a real (if
    # sample-limited) result reflecting genuinely zero comparable games.
    assert result.dimensions["market"].facts != {}
