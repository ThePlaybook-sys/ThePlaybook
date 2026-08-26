"""Tests for app.persistence.games.read_grading_candidate_game_ids
(Milestone 5.4)."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.persistence.games import read_grading_candidate_game_ids

SUPABASE_URL = "https://test-project.supabase.co"
_NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_returns_candidate_ids_from_or_filtered_query():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}, {"id": "g2"}]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        ids = await read_grading_candidate_game_ids(client, _headers(), now=_NOW)
    assert ids == ["g1", "g2"]
    sent_or = route.calls.last.request.url.params.get("or")
    assert "status.eq.postponed" in sent_or
    assert "status.eq.canceled" in sent_or
    assert "status.eq.final" in sent_or


@pytest.mark.asyncio
@respx.mock
async def test_returns_empty_list_when_none_found():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        ids = await read_grading_candidate_game_ids(client, _headers(), now=_NOW)
    assert ids == []
