"""Tests for app.persistence.odds_snapshots (Milestone 4.5)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.odds_snapshots import OddsSnapshotsReadError, read_odds_snapshots

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_read_odds_snapshots_returns_rows_ordered():
    rows = [
        {"sportsbook": "DraftKings", "market_type": "spread", "line_data": {"outcomes": []}, "captured_at": "2026-09-18T12:00:00+00:00"},
        {"sportsbook": "DraftKings", "market_type": "spread", "line_data": {"outcomes": []}, "captured_at": "2026-09-20T12:00:00+00:00"},
    ]
    route = respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=rows))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_odds_snapshots(client, _headers(), game_id="g1")
    assert result == rows
    request = route.calls.last.request
    assert request.url.params["game_id"] == "eq.g1"
    assert request.url.params["order"] == "captured_at.asc"


@pytest.mark.asyncio
@respx.mock
async def test_read_odds_snapshots_returns_empty_list_not_none_when_no_rows():
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_odds_snapshots(client, _headers(), game_id="g1")
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_read_odds_snapshots_raises_on_supabase_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(OddsSnapshotsReadError):
            await read_odds_snapshots(client, _headers(), game_id="g1")
