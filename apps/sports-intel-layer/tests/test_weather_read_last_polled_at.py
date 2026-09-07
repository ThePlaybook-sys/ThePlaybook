"""Tests for `app.persistence.weather_snapshots.read_last_polled_at`
(Phase 8.0.5 Weather Activation, 2026-09-07) -- derives
`run_weather_worker`'s `last_polled_at` argument from already-persisted
`weather_snapshots.captured_at` history, identical derivation to
`app.persistence.odds_snapshots.read_last_polled_at` (Phase 7), so the new
`/v1/internal/weather-worker/run` endpoint realizes real per-game cadence
instead of treating every invocation as "never polled" for every
candidate game -- the exact gap Pass 2.1 found missing for News Worker's
own real call site, fixed here from day one instead of repeated."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.weather_snapshots import PersistenceError, read_last_polled_at

SUPABASE_URL = "https://test-project.supabase.co"


@pytest.fixture(autouse=True)
def _supabase_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


@pytest.mark.asyncio
@respx.mock
async def test_empty_history_returns_empty_dict():
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))

    result = await read_last_polled_at()

    assert result == {}


@pytest.mark.asyncio
@respx.mock
async def test_most_recent_captured_at_wins_per_game():
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"game_id": "game-1", "captured_at": "2026-09-07T23:00:00Z"},
                {"game_id": "game-1", "captured_at": "2026-09-07T22:00:00Z"},
                {"game_id": "game-2", "captured_at": "2026-09-07T21:30:00Z"},
            ],
        )
    )

    result = await read_last_polled_at()

    assert set(result.keys()) == {"game-1", "game-2"}
    assert result["game-1"].isoformat() == "2026-09-07T23:00:00+00:00"
    assert result["game-2"].isoformat() == "2026-09-07T21:30:00+00:00"


@pytest.mark.asyncio
@respx.mock
async def test_a_game_with_no_rows_is_absent_not_defaulted():
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(
        return_value=httpx.Response(200, json=[{"game_id": "game-1", "captured_at": "2026-09-07T23:00:00Z"}])
    )

    result = await read_last_polled_at()

    assert "game-1" in result
    assert "game-2-never-captured" not in result


@pytest.mark.asyncio
@respx.mock
async def test_supabase_failure_raises_persistence_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(500, text="db error"))

    with pytest.raises(PersistenceError):
        await read_last_polled_at()
