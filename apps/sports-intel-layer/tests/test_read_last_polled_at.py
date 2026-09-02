"""Tests for `app.persistence.odds_snapshots.read_last_polled_at` (Phase 7
Milestone 7.0B, 2026-09-02) -- derives `run_odds_worker`'s
`last_polled_at` argument from already-persisted `odds_snapshots.
captured_at` history, so a stateless HTTP-triggered caller (the new
`/v1/internal/odds-worker/run` endpoint) realizes `app.workers.windows`'s
existing adaptive cadence instead of treating every invocation as "never
polled" for every candidate game."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.odds_snapshots import PersistenceError, read_last_polled_at

SUPABASE_URL = "https://test-project.supabase.co"


@pytest.fixture(autouse=True)
def _supabase_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


@pytest.mark.asyncio
@respx.mock
async def test_empty_history_returns_empty_dict():
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))

    result = await read_last_polled_at()

    assert result == {}


@pytest.mark.asyncio
@respx.mock
async def test_most_recent_captured_at_wins_per_game():
    """Ordered newest-first by the query itself -- the first row seen per
    game_id is therefore its max(captured_at); older rows for the same
    game must not overwrite it."""
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"game_id": "game-1", "captured_at": "2026-09-02T23:00:00Z"},
                {"game_id": "game-1", "captured_at": "2026-09-02T22:00:00Z"},
                {"game_id": "game-2", "captured_at": "2026-09-02T21:30:00Z"},
            ],
        )
    )

    result = await read_last_polled_at()

    assert set(result.keys()) == {"game-1", "game-2"}
    assert result["game-1"].isoformat() == "2026-09-02T23:00:00+00:00"
    assert result["game-2"].isoformat() == "2026-09-02T21:30:00+00:00"


@pytest.mark.asyncio
@respx.mock
async def test_a_game_with_no_rows_is_absent_not_defaulted():
    """A game that has never been captured must be absent from the dict
    (not mapped to some sentinel) -- `should_poll`'s own `.get(game_id)`
    -> `None` -> "never polled, always due" default only fires correctly
    when the key is genuinely missing."""
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(
        return_value=httpx.Response(200, json=[{"game_id": "game-1", "captured_at": "2026-09-02T23:00:00Z"}])
    )

    result = await read_last_polled_at()

    assert "game-1" in result
    assert "game-2-never-captured" not in result


@pytest.mark.asyncio
@respx.mock
async def test_supabase_failure_raises_persistence_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(500, text="db error"))

    with pytest.raises(PersistenceError):
        await read_last_polled_at()
