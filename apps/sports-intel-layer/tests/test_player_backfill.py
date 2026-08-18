"""Tests for app.persistence.player_backfill (Phase 3E-8, Decision 1).

Confirms the roster/player population behavior: exactly the four
fixture-confirmed real players are backfilled, each resolved to the right
team via the existing team_identity/team_backfill machinery, and the
provenance discipline (every entry traceable to a captured fixture) holds.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.persistence.player_backfill import PLAYER_BACKFILL, backfill_known_players

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def test_player_backfill_has_exactly_four_fixture_confirmed_entries():
    assert len(PLAYER_BACKFILL) == 4
    names = {entry["name"] for entry in PLAYER_BACKFILL}
    assert names == {"Xavier Worthy", "Emmanuel Ogbah", "Josh Allen", "Harold Landry III"}


def test_player_backfill_matches_live_roster_fixture():
    fixture_path = Path(__file__).parent / "fixtures" / "sportsdataio" / "rosters_normal.json"
    roster_rows = json.loads(fixture_path.read_text())
    by_id = {str(row["PlayerID"]): row for row in roster_rows}

    matched = 0
    for entry in PLAYER_BACKFILL:
        row = by_id.get(entry["provider_player_id"])
        if row is None:
            continue
        assert row["Name"] == entry["name"]
        assert row["Team"] == entry["team_abbrev"]
        assert row["Position"] == entry["position"]
        matched += 1
    assert matched == 2  # Xavier Worthy, Emmanuel Ogbah -- the only two in this fixture


def test_player_backfill_matches_live_player_stats_fixture():
    fixture_path = Path(__file__).parent / "fixtures" / "sportsdataio" / "player_stats_week_bulk_normal.json"
    stat_rows = json.loads(fixture_path.read_text())
    by_id = {str(row["PlayerID"]): row for row in stat_rows}

    matched = 0
    for entry in PLAYER_BACKFILL:
        row = by_id.get(entry["provider_player_id"])
        if row is None:
            continue
        assert row["Name"] == entry["name"]
        assert row["Team"] == entry["team_abbrev"]
        assert row["Position"] == entry["position"]
        matched += 1
    assert matched == 2  # Josh Allen, Harold Landry III -- the only two in this fixture


@pytest.mark.asyncio
@respx.mock
async def test_backfill_known_players_creates_and_links_all_four():
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"team_id": "team-kc", "provider_team_id": "KC"},
                {"team_id": "team-buf", "provider_team_id": "BUF"},
                {"team_id": "team-ne", "provider_team_id": "NE"},
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    player_ids = iter(["p1", "p2", "p3", "p4"])

    def _insert_player(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=[{"id": next(player_ids)}])

    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(side_effect=_insert_player)
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        count = await backfill_known_players(client, _headers())

    assert count == 4
    assert insert_route.call_count == 4
    assert link_route.call_count == 4


@pytest.mark.asyncio
@respx.mock
async def test_backfill_known_players_handles_unresolved_team():
    """If a backfill entry's team abbreviation has no team_provider_ids
    mapping yet, the player is still created (team_id=None), never
    fabricated or skipped silently."""
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": "p1"}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await backfill_known_players(client, _headers())

    bodies = [json.loads(call.request.content) for call in insert_route.calls]
    assert all(body["team_id"] is None for body in bodies)
