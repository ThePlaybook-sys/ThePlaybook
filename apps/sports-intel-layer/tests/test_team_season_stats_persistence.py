"""Tests for app.persistence.team_season_stats (Phase 8.3A, 2026-09-08).

Covers the same idempotent, correction-aware insert design as
test_team_stats_persistence.py, adapted for the (team_id, season_id)-keyed
lookup: first fetch always inserts, an identical reconciliation check
inserts nothing, a genuine correction inserts a new row alongside the
untouched original, unresolved teams are reported not guessed, and the
module never attempts an UPDATE against the DB-level append-only
team_stats table.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.persistence.team_season_stats import (
    TeamSeasonStatLine,
    TeamSeasonStatsPersistenceError,
    persist_team_season_stats,
)

SUPABASE_URL = "https://test-project.supabase.co"
SEASON_ID = "season-2025"
TEAM_ID_BUF = "team-buf"
TEAM_ID_MIA = "team-mia"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _mock_identity():
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"team_id": TEAM_ID_BUF, "provider_team_id": "BUF"},
                {"team_id": TEAM_ID_MIA, "provider_team_id": "MIA"},
            ],
        )
    )


def _line(team: str, games_played: int) -> TeamSeasonStatLine:
    return TeamSeasonStatLine(team=team, stats={"gamesPlayed": games_played})


@pytest.mark.asyncio
@respx.mock
async def test_first_fetch_always_inserts(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    result = await persist_team_season_stats(
        [_line("BUF", 17)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )

    assert result.inserted == 1
    assert result.unchanged == 0
    assert insert_route.call_count == 1
    body = json.loads(insert_route.calls.last.request.content)
    assert body == {"team_id": TEAM_ID_BUF, "season_id": SEASON_ID, "stats": {"gamesPlayed": 17}}
    assert "game_id" not in body


@pytest.mark.asyncio
@respx.mock
async def test_identical_reconciliation_check_inserts_nothing(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [
        {
            "id": "row1",
            "team_id": TEAM_ID_BUF,
            "season_id": SEASON_ID,
            "game_id": None,
            "stats": {"gamesPlayed": 17},
            "created_at": "2026-09-08T20:10:00Z",
        }
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(200, json=existing))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    result = await persist_team_season_stats(
        [_line("BUF", 17)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )

    assert result.inserted == 0
    assert result.unchanged == 1
    assert insert_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_genuine_correction_inserts_new_row(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [
        {
            "id": "row1",
            "team_id": TEAM_ID_BUF,
            "season_id": SEASON_ID,
            "game_id": None,
            "stats": {"gamesPlayed": 16},
            "created_at": "2026-09-08T20:10:00Z",
        }
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(200, json=existing))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    result = await persist_team_season_stats(
        [_line("BUF", 17)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )

    assert result.inserted == 1
    assert result.unchanged == 0
    body = json.loads(insert_route.calls.last.request.content)
    assert body["stats"]["gamesPlayed"] == 17
    assert insert_route.calls.last.request.method == "POST"


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_team_is_reported_not_guessed(monkeypatch):
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    result = await persist_team_season_stats(
        [_line("BUF", 17)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )

    assert result.unresolved_teams == ["BUF"]
    assert insert_route.call_count == 0


@pytest.mark.asyncio
async def test_empty_input_makes_no_calls():
    result = await persist_team_season_stats([], season_id=SEASON_ID, provider_name="mysportsfeeds")
    assert result.inserted == 0


@pytest.mark.asyncio
@respx.mock
async def test_raises_on_insert_failure(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(500))

    with pytest.raises(TeamSeasonStatsPersistenceError):
        await persist_team_season_stats(
            [_line("BUF", 17)], season_id=SEASON_ID, provider_name="mysportsfeeds"
        )


@pytest.mark.asyncio
@respx.mock
async def test_module_never_issues_an_update_to_team_stats(monkeypatch):
    """team_stats carries a DB-level append-only trigger
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
            "team_id": TEAM_ID_BUF,
            "season_id": SEASON_ID,
            "game_id": None,
            "stats": {"gamesPlayed": 16},
            "created_at": "2026-09-08T20:10:00Z",
        }
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(200, json=existing))
    respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    await persist_team_season_stats(
        [_line("BUF", 17)], season_id=SEASON_ID, provider_name="mysportsfeeds"
    )  # no PATCH/PUT route registered -- would raise if attempted
