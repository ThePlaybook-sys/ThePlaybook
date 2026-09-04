"""Tests for app.persistence.game_events (2026 Data Preservation
Readiness Plan, pre-9/9 minimum implementation).

Covers the one property this module exists to prove: raw-capture-only
persistence works for an arbitrary provider payload shape -- a JSON
array of per-event fragments, a single nested object, or nothing at all
-- without requiring any typed-field normalization. No MySportsFeeds-
specific field name is assumed or exercised anywhere in this file.
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.persistence.game_events import PersistenceError, write_raw_game_events

SUPABASE_URL = "https://test-project.supabase.co"
GAME_ID = "db-game-1"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


@pytest.mark.asyncio
@respx.mock
async def test_list_shaped_payload_writes_one_row_per_fragment(monkeypatch):
    """A provider response that IS a JSON array of per-play objects --
    one hypothetical real shape, not assumed to be THE real shape."""
    _headers_env(monkeypatch)
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(201))

    raw_response = [
        {"quarter": 1, "clock": "14:55", "playType": "Run", "yards": 4},
        {"quarter": 1, "clock": "14:10", "playType": "Pass", "yards": 12},
    ]
    count = await write_raw_game_events(game_id=GAME_ID, provider_name="mysportsfeeds", raw_response=raw_response)

    assert count == 2
    assert insert_route.call_count == 1
    rows = _json.loads(insert_route.calls[0].request.content)
    assert len(rows) == 2
    for row, fragment in zip(rows, raw_response):
        assert row["game_id"] == GAME_ID
        assert row["provider_name"] == "mysportsfeeds"
        assert row["raw_payload"] == fragment
        # Every typed/normalized column is simply absent from the insert
        # payload -- never fabricated, never guessed.
        assert set(row.keys()) == {"game_id", "provider_name", "raw_payload", "captured_at"}


@pytest.mark.asyncio
@respx.mock
async def test_dict_shaped_payload_writes_one_row_for_the_whole_response(monkeypatch):
    """A provider response that is a single nested object with no
    obvious top-level list -- the OTHER plausible real shape. Both must
    be handled without guessing which one MySportsFeeds actually
    returns."""
    _headers_env(monkeypatch)
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(201))

    raw_response = {"gameId": "202609090", "plays": {"quarter1": ["..."], "quarter2": []}}
    count = await write_raw_game_events(game_id=GAME_ID, provider_name="mysportsfeeds", raw_response=raw_response)

    assert count == 1
    rows = _json.loads(insert_route.calls[0].request.content)
    assert len(rows) == 1
    assert rows[0]["raw_payload"] == raw_response


@pytest.mark.asyncio
@respx.mock
async def test_empty_response_writes_nothing(monkeypatch):
    _headers_env(monkeypatch)
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(201))

    count_none = await write_raw_game_events(game_id=GAME_ID, provider_name="mysportsfeeds", raw_response=None)
    count_empty_list = await write_raw_game_events(game_id=GAME_ID, provider_name="mysportsfeeds", raw_response=[])

    assert count_none == 0
    assert count_empty_list == 0
    assert insert_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_captured_at_defaults_to_now_and_is_overridable(monkeypatch):
    _headers_env(monkeypatch)
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(201))

    fixed_now = datetime(2026, 9, 10, 0, 25, tzinfo=timezone.utc)
    await write_raw_game_events(
        game_id=GAME_ID, provider_name="mysportsfeeds", raw_response={"x": 1}, now=fixed_now
    )

    rows = _json.loads(insert_route.calls[0].request.content)
    assert rows[0]["captured_at"] == fixed_now.isoformat()


@pytest.mark.asyncio
@respx.mock
async def test_insert_failure_raises_persistence_error(monkeypatch):
    _headers_env(monkeypatch)
    respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(PersistenceError):
        await write_raw_game_events(game_id=GAME_ID, provider_name="mysportsfeeds", raw_response={"x": 1})
