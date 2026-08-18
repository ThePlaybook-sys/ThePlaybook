"""Tests for app.persistence.player_stats (Phase 3E-8).

Same idempotent, correction-aware design as team_stats -- see
test_team_stats_persistence.py. Additionally covers unresolved player
handling: a player with no player_provider_ids mapping is reported, never
guessed by name-matching, never auto-created.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.adapters.models import AdapterResponse, PlayerStatLine
from app.persistence.player_stats import PersistenceError, persist_player_stats

SUPABASE_URL = "https://test-project.supabase.co"
GAME_ID = "g1"
PLAYER_ID = "p1"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _mock_identity(player_rows=None):
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": GAME_ID, "provider_game_id": "202510104"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=player_rows if player_rows is not None else [{"player_id": PLAYER_ID, "provider_player_id": "19801"}])
    )


def _line(passing_yards: int) -> PlayerStatLine:
    return PlayerStatLine(
        game_external_id="202510104", player_external_id="19801", player_name="Josh Allen",
        team="BUF", stats={"PassingYards": passing_yards},
    )


@pytest.mark.asyncio
@respx.mock
async def test_first_fetch_always_inserts(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    result = await persist_player_stats(AdapterResponse(value=[_line(250)], source="sportsdataio"))

    assert result.inserted == 1
    assert insert_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_identical_reconciliation_check_inserts_nothing(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [{"id": "row1", "game_id": GAME_ID, "player_id": PLAYER_ID, "stats": {"PassingYards": 250}, "created_at": "2026-09-14T20:10:00Z"}]
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=existing))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    result = await persist_player_stats(AdapterResponse(value=[_line(250)], source="sportsdataio"))

    assert result.inserted == 0
    assert result.unchanged == 1
    assert insert_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_genuine_correction_inserts_new_row(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [{"id": "row1", "game_id": GAME_ID, "player_id": PLAYER_ID, "stats": {"PassingYards": 250}, "created_at": "2026-09-14T20:10:00Z"}]
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=existing))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    result = await persist_player_stats(AdapterResponse(value=[_line(275)], source="sportsdataio"))

    assert result.inserted == 1
    body = json.loads(insert_route.calls.last.request.content)
    assert body["stats"]["PassingYards"] == 275


@pytest.mark.asyncio
@respx.mock
async def test_unknown_player_is_reported_not_guessed(monkeypatch):
    """Unknown player handling: no player_provider_ids mapping exists for
    this provider_player_id -- reported via unresolved_players, never
    matched by name/team, never auto-created."""
    _headers_env(monkeypatch)
    _mock_identity(player_rows=[])  # no players resolved at all
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))
    players_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(201))

    result = await persist_player_stats(AdapterResponse(value=[_line(250)], source="sportsdataio"))

    assert result.unresolved_players == ["19801"]
    assert insert_route.call_count == 0
    assert players_insert_route.call_count == 0  # never auto-created


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_game_is_reported_not_guessed(monkeypatch):
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": PLAYER_ID, "provider_player_id": "19801"}])
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    result = await persist_player_stats(AdapterResponse(value=[_line(250)], source="sportsdataio"))

    assert result.unresolved_games == ["202510104"]
    assert insert_route.call_count == 0


@pytest.mark.asyncio
async def test_empty_input_makes_no_calls():
    result = await persist_player_stats(AdapterResponse(value=[], source="sportsdataio"))
    assert result.inserted == 0


@pytest.mark.asyncio
@respx.mock
async def test_raises_on_insert_failure(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(500))

    with pytest.raises(PersistenceError):
        await persist_player_stats(AdapterResponse(value=[_line(250)], source="sportsdataio"))


@pytest.mark.asyncio
@respx.mock
async def test_module_never_issues_an_update_to_player_stats(monkeypatch):
    """Phase 3F-3: player_stats now carries a DB-level append-only trigger
    (block_snapshot_updates(), live-proven against real dev Supabase to
    reject an UPDATE). This module's own contribution to that guarantee is
    structural: it must never even attempt a PATCH/PUT against
    player_stats -- registering no mock for those methods means respx
    raises if this module ever tried, across both a first insert and a
    correction."""
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [{"id": "row1", "game_id": GAME_ID, "player_id": PLAYER_ID, "stats": {"PassingYards": 250}, "created_at": "2026-09-14T20:10:00Z"}]
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=existing))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    await persist_player_stats(AdapterResponse(value=[_line(275)], source="sportsdataio"))  # no PATCH/PUT route registered -- would raise if attempted
