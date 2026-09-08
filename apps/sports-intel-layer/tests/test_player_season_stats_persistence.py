"""Tests for app.persistence.player_season_stats (Phase 8.3D, 2026-09-08).

Same idempotent, correction-aware insert design as
test_team_season_stats_persistence.py, adapted for player identity:
first fetch always inserts, an identical reconciliation check inserts
nothing, a genuine correction inserts a new row alongside the untouched
original (historical truth preserved -- HQ's explicit "must not silently
overwrite previous provider observations" instruction), unresolved
players are reported not guessed/auto-created, and the module never
attempts an UPDATE against the DB-level append-only player_stats table.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.persistence.player_season_stats import (
    PlayerSeasonStatLine,
    PlayerSeasonStatsPersistenceError,
    persist_player_season_stats,
)

SUPABASE_URL = "https://test-project.supabase.co"
SEASON_ID = "season-2025"
PLAYER_ID_HENRY = "player-henry"
PLAYER_ID_DIGGS = "player-diggs"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _mock_identity():
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"player_id": PLAYER_ID_HENRY, "provider_player_id": "9999"},
                {"player_id": PLAYER_ID_DIGGS, "provider_player_id": "7471"},
            ],
        )
    )


def _line(player: str, receptions: int) -> PlayerSeasonStatLine:
    return PlayerSeasonStatLine(player=player, stats={"receiving": {"receptions": receptions}})


@pytest.mark.asyncio
@respx.mock
async def test_first_fetch_always_inserts(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    result = await persist_player_season_stats(
        [_line("9999", 60)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )

    assert result.inserted == 1
    assert result.unchanged == 0
    assert insert_route.call_count == 1
    body = json.loads(insert_route.calls.last.request.content)
    assert body == {
        "player_id": PLAYER_ID_HENRY,
        "season_id": SEASON_ID,
        "stats": {"receiving": {"receptions": 60}},
    }
    assert "game_id" not in body


@pytest.mark.asyncio
@respx.mock
async def test_identical_reconciliation_check_inserts_nothing(monkeypatch):
    """Idempotency, explicitly proven: re-ingesting the same real
    observation must not create a duplicate row."""
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [
        {
            "id": "row1",
            "player_id": PLAYER_ID_HENRY,
            "season_id": SEASON_ID,
            "game_id": None,
            "stats": {"receiving": {"receptions": 60}},
            "created_at": "2026-09-08T18:31:14Z",
        }
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=existing))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    result = await persist_player_season_stats(
        [_line("9999", 60)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )

    assert result.inserted == 0
    assert result.unchanged == 1
    assert insert_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_genuine_correction_inserts_new_row_preserving_history(monkeypatch):
    """Historical truth preserved, explicitly proven: a real correction
    (e.g. a mid-season stat revision) inserts a NEW row rather than
    mutating the prior observation -- the old row is never touched, only
    ever superseded by created_at ordering."""
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [
        {
            "id": "row1",
            "player_id": PLAYER_ID_HENRY,
            "season_id": SEASON_ID,
            "game_id": None,
            "stats": {"receiving": {"receptions": 58}},
            "created_at": "2026-09-08T18:31:14Z",
        }
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=existing))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    result = await persist_player_season_stats(
        [_line("9999", 60)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )

    assert result.inserted == 1
    assert result.unchanged == 0
    body = json.loads(insert_route.calls.last.request.content)
    assert body["stats"]["receiving"]["receptions"] == 60
    assert insert_route.calls.last.request.method == "POST"  # never PATCH/PUT


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_player_is_reported_not_guessed_or_created(monkeypatch):
    """Identity resolution never joins by name and never auto-creates a
    player -- HQ's explicit instruction this pass. A provider id with no
    existing player_provider_ids mapping is simply unresolved."""
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    players_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(201))
    stats_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    result = await persist_player_season_stats(
        [_line("9999", 60)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )

    assert result.unresolved_players == ["9999"]
    assert stats_insert_route.call_count == 0
    assert players_insert_route.call_count == 0  # never creates a player


@pytest.mark.asyncio
async def test_empty_input_makes_no_calls():
    result = await persist_player_season_stats([], season_id=SEASON_ID, provider_name="mysportsfeeds")
    assert result.inserted == 0


@pytest.mark.asyncio
@respx.mock
async def test_raises_on_insert_failure(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(500))

    with pytest.raises(PlayerSeasonStatsPersistenceError):
        await persist_player_season_stats(
            [_line("9999", 60)], season_id=SEASON_ID, provider_name="mysportsfeeds"
        )


@pytest.mark.asyncio
@respx.mock
async def test_module_never_issues_an_update_to_player_stats(monkeypatch):
    """player_stats carries a DB-level append-only trigger
    (block_snapshot_updates(), 20260818080000_team_stats_player_stats_
    append_only.sql). This module's contribution to that guarantee is
    structural: no mock is registered for PATCH/PUT, so respx raises if
    this module ever attempted one, across both a first insert and a
    correction."""
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [
        {
            "id": "row1",
            "player_id": PLAYER_ID_HENRY,
            "season_id": SEASON_ID,
            "game_id": None,
            "stats": {"receiving": {"receptions": 58}},
            "created_at": "2026-09-08T18:31:14Z",
        }
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=existing))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    await persist_player_season_stats(
        [_line("9999", 60)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )  # no PATCH/PUT route registered -- would raise if attempted


@pytest.mark.asyncio
@respx.mock
async def test_multiple_players_resolved_and_persisted_independently(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    result = await persist_player_season_stats(
        [_line("9999", 60), _line("7471", 85)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )

    assert result.inserted == 2
    assert insert_route.call_count == 2
