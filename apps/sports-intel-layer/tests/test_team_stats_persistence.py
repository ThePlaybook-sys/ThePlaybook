"""Tests for app.persistence.team_stats (Phase 3E-8).

Covers the idempotent, correction-aware insert design: first fetch always
inserts, an identical reconciliation check inserts nothing, a genuine
correction inserts a new row alongside the untouched original, and
unresolved games/teams are reported, never guessed.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.adapters.models import AdapterResponse, TeamStatLine
from app.persistence.team_stats import PersistenceError, persist_team_stats

SUPABASE_URL = "https://test-project.supabase.co"
GAME_ID = "g1"
TEAM_ID_ARI = "team-ari"
TEAM_ID_NO = "team-no"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _mock_identity():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": GAME_ID, "provider_game_id": "202510122"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"team_id": TEAM_ID_ARI, "provider_team_id": "ARI"},
                {"team_id": TEAM_ID_NO, "provider_team_id": "NO"},
            ],
        )
    )


def _line(team: str, score: int) -> TeamStatLine:
    return TeamStatLine(game_external_id="202510122", team=team, stats={"Score": score, "HomeOrAway": "AWAY"})


@pytest.mark.asyncio
@respx.mock
async def test_first_fetch_always_inserts(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    result = await persist_team_stats(AdapterResponse(value=[_line("ARI", 10)], source="sportsdataio"))

    assert result.inserted == 1
    assert result.unchanged == 0
    assert insert_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_identical_reconciliation_check_inserts_nothing(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [{"id": "row1", "game_id": GAME_ID, "team_id": TEAM_ID_ARI, "stats": {"Score": 10, "HomeOrAway": "AWAY"}, "created_at": "2026-09-14T20:10:00Z"}]
    respx.get(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(200, json=existing))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    result = await persist_team_stats(AdapterResponse(value=[_line("ARI", 10)], source="sportsdataio"))

    assert result.inserted == 0
    assert result.unchanged == 1
    assert insert_route.call_count == 0  # no duplicate row


@pytest.mark.asyncio
@respx.mock
async def test_genuine_correction_inserts_new_row(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [{"id": "row1", "game_id": GAME_ID, "team_id": TEAM_ID_ARI, "stats": {"Score": 10, "HomeOrAway": "AWAY"}, "created_at": "2026-09-14T20:10:00Z"}]
    respx.get(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(200, json=existing))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    # A provider stat correction: the score changed from 10 to 13.
    result = await persist_team_stats(AdapterResponse(value=[_line("ARI", 13)], source="sportsdataio"))

    assert result.inserted == 1
    assert result.unchanged == 0
    body = json.loads(insert_route.calls.last.request.content)
    assert body["stats"]["Score"] == 13
    # the original row was never touched -- only ever a POST, never a PATCH
    assert insert_route.calls.last.request.method == "POST"


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_game_is_reported_not_guessed(monkeypatch):
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": TEAM_ID_ARI, "provider_team_id": "ARI"}])
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    result = await persist_team_stats(AdapterResponse(value=[_line("ARI", 10)], source="sportsdataio"))

    assert result.unresolved_games == ["202510122"]
    assert insert_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_team_is_reported_not_guessed(monkeypatch):
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": GAME_ID, "provider_game_id": "202510122"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    result = await persist_team_stats(AdapterResponse(value=[_line("ARI", 10)], source="sportsdataio"))

    assert result.unresolved_teams == ["ARI"]
    assert insert_route.call_count == 0


@pytest.mark.asyncio
async def test_empty_input_makes_no_calls():
    result = await persist_team_stats(AdapterResponse(value=[], source="sportsdataio"))
    assert result.inserted == 0


@pytest.mark.asyncio
@respx.mock
async def test_raises_on_insert_failure(monkeypatch):
    _headers_env(monkeypatch)
    _mock_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(500))

    with pytest.raises(PersistenceError):
        await persist_team_stats(AdapterResponse(value=[_line("ARI", 10)], source="sportsdataio"))


@pytest.mark.asyncio
@respx.mock
async def test_module_never_issues_an_update_to_team_stats(monkeypatch):
    """Phase 3F-3: team_stats now carries a DB-level append-only trigger
    (block_snapshot_updates(), live-proven against real dev Supabase to
    reject an UPDATE). This module's own contribution to that guarantee is
    structural: it must never even attempt a PATCH/PUT against team_stats
    -- registering no mock for those methods means respx raises if this
    module ever tried, across both a first insert and a correction."""
    _headers_env(monkeypatch)
    _mock_identity()
    existing = [{"id": "row1", "game_id": GAME_ID, "team_id": TEAM_ID_ARI, "stats": {"Score": 10, "HomeOrAway": "AWAY"}, "created_at": "2026-09-14T20:10:00Z"}]
    respx.get(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(200, json=existing))
    respx.post(f"{SUPABASE_URL}/rest/v1/team_stats").mock(return_value=httpx.Response(201))

    await persist_team_stats(AdapterResponse(value=[_line("ARI", 13)], source="sportsdataio"))  # no PATCH/PUT route registered -- would raise if attempted
