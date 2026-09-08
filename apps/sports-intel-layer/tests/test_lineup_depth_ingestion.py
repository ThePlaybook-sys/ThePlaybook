"""Tests for app.persistence.lineup_depth_ingestion (Phase 8.2 Lineup/
Depth Activation, 2026-09-08). Fixture shapes mirror the real
lineup.json payload captured live by the 2026-09-03 gap test (game
163541, NE @ SEA), not invented -- including the real Brock Lampe
FB/"Defense-CB-2" slot-label mismatch."""
from __future__ import annotations

import json as _json

import httpx
import pytest
import respx

from app.persistence.lineup_depth_ingestion import (
    LineupDepthIngestionError,
    LineupDepthIngestionResult,
    parse_lineup_slot,
    persist_lineup_depth_chart,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _real_lineup_body(*, include_unconfirmed=True):
    ne_positions = [
        {
            "position": "Offense-RB-1",
            "player": {"id": 31103, "firstName": "Rhamondre", "lastName": "Stevenson", "position": "RB", "jerseyNumber": 38},
        },
        {"position": "Offense-C", "player": {"id": 166763, "firstName": "Jared", "lastName": "Wilson", "position": "C", "jerseyNumber": 58}},
    ]
    if include_unconfirmed:
        ne_positions.append({"position": "Offense-RB-3", "player": None})
    sea_positions = [
        {
            # Real observed anomaly: label says CB-2, player's own position is FB.
            "position": "Defense-CB-2",
            "player": {"id": 168249, "firstName": "Brock", "lastName": "Lampe", "position": "FB", "jerseyNumber": 46},
        },
    ]
    return {
        "lastUpdatedOn": "2026-09-03T19:24:29.492Z",
        "game": {"id": 163541, "week": 1, "homeTeam": {"abbreviation": "SEA"}, "awayTeam": {"abbreviation": "NE"}},
        "teamLineups": [
            {"team": {"id": 50, "abbreviation": "NE"}, "expected": {"lineupPositions": ne_positions}},
            {"team": {"id": 79, "abbreviation": "SEA"}, "expected": {"lineupPositions": sea_positions}},
        ],
    }


def _mock_team_resolved(team_abbrev, team_id):
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": team_id, "provider_team_id": team_abbrev}])
    )


# --- parse_lineup_slot -------------------------------------------------


def test_parses_side_group_and_rank():
    assert parse_lineup_slot("Offense-RB-1") == ("Offense", "RB", 1)
    assert parse_lineup_slot("Defense-CB-2") == ("Defense", "CB", 2)
    assert parse_lineup_slot("SpecialTeams-K-1") == ("SpecialTeams", "K", 1)


def test_no_rank_suffix_stays_none_not_defaulted_to_one():
    assert parse_lineup_slot("Offense-C") == ("Offense", "C", None)


def test_unrecognized_label_returns_all_none():
    assert parse_lineup_slot("something-unexpected") == (None, None, None)


# --- persist_lineup_depth_chart -----------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_real_shape_resolves_and_writes_one_snapshot(monkeypatch):
    _headers_env(monkeypatch)
    _mock_team_resolved("NE", "team-ne")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"player_id": "player-stevenson", "provider_player_id": "31103"},
                {"player_id": "player-wilson", "provider_player_id": "166763"},
            ],
        )
    )
    depth_route = respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    result = await persist_lineup_depth_chart(_real_lineup_body(), team="NE", provider_name="mysportsfeeds")

    assert result.snapshot_written is True
    assert result.entries_written == 2  # the unconfirmed RB-3 slot (player=None) is dropped, never fabricated
    assert result.unresolved_players == []
    assert result.unresolved_team is None
    assert depth_route.call_count == 1

    body = _json.loads(depth_route.calls.last.request.content)
    assert body["team_id"] == "team-ne"
    data = body["depth_chart_data"]
    assert data["provider_name"] == "mysportsfeeds"
    assert data["provider_last_updated_on"] == "2026-09-03T19:24:29.492Z"
    assert data["source_game_external_id"] == "163541"
    entries = {e["provider_player_id"]: e for e in data["entries"]}
    assert entries["31103"]["depth_chart_rank"] == 1
    assert entries["31103"]["lineup_slot"] == "Offense-RB-1"
    assert entries["166763"]["depth_chart_rank"] is None  # "Offense-C" carries no rank suffix


@pytest.mark.asyncio
@respx.mock
async def test_position_vs_slot_label_mismatch_is_preserved_not_reconciled(monkeypatch):
    """The real Brock Lampe case: player.position='FB' under a
    'Defense-CB-2' slot label. Both values are preserved verbatim,
    neither discarded or 'corrected'."""
    _headers_env(monkeypatch)
    _mock_team_resolved("SEA", "team-sea")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "player-lampe", "provider_player_id": "168249"}])
    )
    depth_route = respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    result = await persist_lineup_depth_chart(_real_lineup_body(), team="SEA", provider_name="mysportsfeeds")

    assert result.entries_written == 1
    body = _json.loads(depth_route.calls.last.request.content)
    entry = body["depth_chart_data"]["entries"][0]
    assert entry["position"] == "FB"  # from player.position, the authoritative source
    assert entry["lineup_slot"] == "Defense-CB-2"  # raw label preserved as-is, not "fixed"
    assert entry["side"] == "Defense"
    assert entry["depth_chart_rank"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_player_is_reported_and_excluded_not_fabricated(monkeypatch):
    _headers_env(monkeypatch)
    _mock_team_resolved("NE", "team-ne")
    # Neither player has an existing player_provider_ids row.
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    depth_route = respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    result = await persist_lineup_depth_chart(_real_lineup_body(), team="NE", provider_name="mysportsfeeds")

    assert sorted(result.unresolved_players) == ["166763", "31103"]
    assert result.entries_written == 0
    assert result.snapshot_written is False
    assert not depth_route.called  # nothing real to write -- no empty/fabricated snapshot


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_team_reports_every_named_player_and_writes_nothing(monkeypatch):
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    depth_route = respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots")

    result = await persist_lineup_depth_chart(_real_lineup_body(), team="NE", provider_name="mysportsfeeds")

    assert result.unresolved_team == "NE"
    assert sorted(result.unresolved_players) == ["166763", "31103"]
    assert not depth_route.called


@pytest.mark.asyncio
async def test_team_not_present_in_payload_is_a_pure_noop():
    result = await persist_lineup_depth_chart(_real_lineup_body(), team="KC", provider_name="mysportsfeeds")
    assert result == LineupDepthIngestionResult()


@pytest.mark.asyncio
@respx.mock
async def test_write_failure_raises(monkeypatch):
    _headers_env(monkeypatch)
    _mock_team_resolved("NE", "team-ne")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"player_id": "player-stevenson", "provider_player_id": "31103"},
                {"player_id": "player-wilson", "provider_player_id": "166763"},
            ],
        )
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(500))

    with pytest.raises(LineupDepthIngestionError):
        await persist_lineup_depth_chart(_real_lineup_body(), team="NE", provider_name="mysportsfeeds")


@pytest.mark.asyncio
@respx.mock
async def test_every_real_call_writes_a_new_row_append_only_not_deduplicated(monkeypatch):
    """Matches odds_snapshots/injury_reports/weather_snapshots' own
    'every poll is a new row' convention -- deliberately NOT deduplicated
    the way roster_memberships is. Two calls with identical input write
    two rows with identical entries content."""
    _headers_env(monkeypatch)
    _mock_team_resolved("NE", "team-ne")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"player_id": "player-stevenson", "provider_player_id": "31103"},
                {"player_id": "player-wilson", "provider_player_id": "166763"},
            ],
        )
    )
    depth_route = respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    result1 = await persist_lineup_depth_chart(_real_lineup_body(), team="NE", provider_name="mysportsfeeds")
    result2 = await persist_lineup_depth_chart(_real_lineup_body(), team="NE", provider_name="mysportsfeeds")

    assert depth_route.call_count == 2
    assert result1.entries_written == result2.entries_written == 2
    body1 = _json.loads(depth_route.calls[0].request.content)
    body2 = _json.loads(depth_route.calls[1].request.content)
    assert body1["depth_chart_data"]["entries"] == body2["depth_chart_data"]["entries"]
