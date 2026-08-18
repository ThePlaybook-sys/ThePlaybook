"""Tests for app.persistence.roster_ingestion (Phase 3F-1).

Every HTTP boundary is respx-mocked. Covers the exact behaviors Decision 1
(roster_memberships) and Decision 2 (depth_chart_snapshots) required be
defined before the migration was written: first observed membership,
unchanged membership, team change, rejoining a prior team, unresolved
identity, and idempotent re-ingestion.
"""
from __future__ import annotations

import json as _json

import httpx
import pytest
import respx

from app.adapters.models import AdapterResponse, RosterEntry
from app.persistence.roster_ingestion import RosterIngestionError, persist_roster

SUPABASE_URL = "https://test-project.supabase.co"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _roster_response(team="KC", entries=None):
    entries = entries if entries is not None else [
        RosterEntry(team=team, player_external_id="24924", player_name="Xavier Worthy", position="WR", depth_chart_rank=1),
        RosterEntry(team=team, player_external_id="17958", player_name="Emmanuel Ogbah", position="DL", depth_chart_rank=2),
    ]
    return AdapterResponse(value=entries, source="sportsdataio")


def _mock_team_resolved(team_abbrev, team_id):
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": team_id, "provider_team_id": team_abbrev}])
    )


@pytest.mark.asyncio
@respx.mock
async def test_first_roster_ingestion_creates_players_and_memberships(monkeypatch):
    _headers_env(monkeypatch)
    _mock_team_resolved("KC", "team-kc")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    created_ids = iter(["player-1", "player-2"])
    create_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": next(created_ids)}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    membership_route = respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    depth_route = respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    result = await persist_roster(_roster_response())

    assert result.players_created == 2
    assert result.players_confirmed == 0
    assert result.memberships_inserted == 2
    assert result.memberships_unchanged == 0
    assert result.depth_chart_written is True
    assert result.unresolved_team is None
    assert result.unresolved_players == []
    assert create_route.call_count == 2
    assert link_route.call_count == 2
    assert membership_route.call_count == 2
    assert patch_route.call_count == 2  # sync players.team_id on first observation too
    assert depth_route.call_count == 1  # one snapshot for the whole team, not per player

    depth_body = _json.loads(depth_route.calls.last.request.content)
    assert depth_body["team_id"] == "team-kc"
    assert len(depth_body["depth_chart_data"]) == 2
    assert depth_body["depth_chart_data"][0]["depth_chart_rank"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_unchanged_roster_reingestion_inserts_no_new_membership(monkeypatch):
    _headers_env(monkeypatch)
    _mock_team_resolved("KC", "team-kc")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"player_id": "player-1", "provider_player_id": "24924"},
                {"player_id": "player-2", "provider_player_id": "17958"},
            ],
        )
    )
    create_route = respx.post(f"{SUPABASE_URL}/rest/v1/players")
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-kc"}])
    )
    membership_route = respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships")
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/players")
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    result = await persist_roster(_roster_response())

    assert result.players_created == 0
    assert result.players_confirmed == 2
    assert result.memberships_inserted == 0
    assert result.memberships_unchanged == 2
    assert not create_route.called  # already-known players, never re-created
    assert not membership_route.called  # no change -> no insert
    assert not patch_route.called  # already correct -> no redundant write


@pytest.mark.asyncio
@respx.mock
async def test_player_team_change_inserts_membership_and_syncs_current_team(monkeypatch):
    """A player previously on BUF is now observed on KC's roster --
    roster_memberships gets a new row, the old BUF row is never touched
    (no PATCH/UPDATE issued against it), and players.team_id is synced to
    the new team."""
    _headers_env(monkeypatch)
    _mock_team_resolved("KC", "team-kc")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "player-9", "provider_player_id": "19801"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-buf"}])  # latest known team
    )
    membership_route = respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    entries = [RosterEntry(team="KC", player_external_id="19801", player_name="Josh Allen", position="QB")]
    result = await persist_roster(_roster_response(entries=entries))

    assert result.memberships_inserted == 1
    assert result.memberships_unchanged == 0
    membership_body = _json.loads(membership_route.calls.last.request.content)
    assert membership_body == {"player_id": "player-9", "team_id": "team-kc"}
    patch_body = _json.loads(patch_route.calls.last.request.content)
    assert patch_body == {"team_id": "team-kc"}
    assert patch_route.calls.last.request.url.params.get("id") == "eq.player-9"
    # Only one INSERT was ever issued -- the prior BUF row is never mutated,
    # proven structurally: this module never sends a PATCH/UPDATE to
    # roster_memberships at all (only POST), so the old row is untouched.
    assert membership_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_rejoining_a_prior_team_is_treated_as_a_plain_team_change(monkeypatch):
    """The latest-row comparison only looks at the single most recent
    membership -- a rejoin (team X -> team Y -> team X again) needs no
    special-casing, it's just another "observed != latest" case."""
    _headers_env(monkeypatch)
    _mock_team_resolved("KC", "team-kc")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "player-9", "provider_player_id": "19801"}])
    )
    # Latest known row says the player is currently on BUF (even though an
    # even-older row -- not returned, since only latest is read -- was KC).
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-buf"}])
    )
    membership_route = respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    entries = [RosterEntry(team="KC", player_external_id="19801", player_name="Josh Allen", position="QB")]
    result = await persist_roster(_roster_response(entries=entries))

    assert result.memberships_inserted == 1
    assert membership_route.call_count == 1  # a fresh insert, same as any other team change


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_team_reports_every_player_and_writes_nothing(monkeypatch):
    """No team_provider_ids mapping for the roster's own team abbreviation
    -- none of its players can be safely anchored to a team, so nothing is
    written (no player created with a null/guessed team), and every player
    is reported via unresolved_players."""
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    create_route = respx.post(f"{SUPABASE_URL}/rest/v1/players")
    membership_route = respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships")
    depth_route = respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots")

    result = await persist_roster(_roster_response(team="XX"))

    assert result.unresolved_team == "XX"
    assert sorted(result.unresolved_players) == ["17958", "24924"]
    assert result.players_created == 0
    assert result.depth_chart_written is False
    assert not create_route.called
    assert not membership_route.called
    assert not depth_route.called


@pytest.mark.asyncio
@respx.mock
async def test_no_fuzzy_matching_same_name_different_provider_id_creates_new_player(monkeypatch):
    """Identity resolution is always by provider_player_id, never by name
    -- a different provider_player_id with a matching name is a distinct,
    newly-created player, not silently merged into an existing one."""
    _headers_env(monkeypatch)
    _mock_team_resolved("KC", "team-kc")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    create_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": "player-new"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    entries = [RosterEntry(team="KC", player_external_id="99999", player_name="Xavier Worthy", position="WR")]
    result = await persist_roster(_roster_response(entries=entries))

    assert result.players_created == 1
    create_body = _json.loads(create_route.calls.last.request.content)
    assert create_body["name"] == "Xavier Worthy"  # created fresh, not matched to an existing "Xavier Worthy"


@pytest.mark.asyncio
@respx.mock
async def test_idempotent_reingestion_is_a_pure_noop_on_players_and_memberships(monkeypatch):
    """Running the exact same roster fetch twice in a row (same mocked
    Supabase state both times) never creates a duplicate player or a
    duplicate membership row the second time."""
    _headers_env(monkeypatch)
    _mock_team_resolved("KC", "team-kc")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"player_id": "player-1", "provider_player_id": "24924"},
                {"player_id": "player-2", "provider_player_id": "17958"},
            ],
        )
    )
    create_route = respx.post(f"{SUPABASE_URL}/rest/v1/players")
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-kc"}])
    )
    membership_route = respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships")
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    result1 = await persist_roster(_roster_response())
    result2 = await persist_roster(_roster_response())

    assert result1.memberships_unchanged == 2 and result2.memberships_unchanged == 2
    assert not create_route.called
    assert not membership_route.called


@pytest.mark.asyncio
@respx.mock
async def test_depth_chart_write_failure_raises(monkeypatch):
    _headers_env(monkeypatch)
    _mock_team_resolved("KC", "team-kc")
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"player_id": "player-1", "provider_player_id": "24924"},
                {"player_id": "player-2", "provider_player_id": "17958"},
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-kc"}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(500))

    with pytest.raises(RosterIngestionError):
        await persist_roster(_roster_response())


@pytest.mark.asyncio
async def test_empty_roster_is_a_pure_noop():
    result = await persist_roster(AdapterResponse(value=[], source="sportsdataio"))
    assert result == type(result)()
