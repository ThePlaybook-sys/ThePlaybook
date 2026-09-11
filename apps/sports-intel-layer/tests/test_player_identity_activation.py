"""Tests for app.persistence.player_identity_activation (2026-09-11,
HQ-authorized "AUTOMATIC PLAYER IDENTITY + QUARANTINE BUILD").

Proves every rule (A-J) the module's own docstring names: safe unseen-
player creation, provider-ID reuse, unresolved-team quarantine,
provider-ID collision quarantine, ambiguous/name-similarity quarantine
(never merge), malformed-identity quarantine, idempotency across
repeated calls, and that one quarantined player never blocks a peer's
resolution. The Gate B 69-real-player replay test lives in a separate
file (test_player_identity_activation_gate_b_replay.py) since it
exercises a real fixture rather than synthetic respx mocks.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.persistence.player_identity_activation import (
    ActivationResult,
    activate_msf_player,
)

SUPABASE_URL = "https://test-project.supabase.co"
GAME_ID = "50d14afd-2861-4e07-b235-90ea857f004d"
TEAM_ID = "a3000000-0000-0000-0000-000000000003"
PLAYER_ID = "c4000000-0000-0000-0000-000000000099"
NEW_PLAYER_ID = "c4000000-0000-0000-0000-000000000100"
QUARANTINE_ID = "d5000000-0000-0000-0000-000000000001"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _mock_empty_quarantine_check() -> None:
    respx.get(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(
        return_value=httpx.Response(200, json=[])
    )


@pytest.mark.asyncio
@respx.mock
async def test_reuse_path_never_touches_team_or_quarantine_endpoints():
    """Rule B: an already-mapped provider_player_id resolves immediately
    -- no team resolution, no name check, no quarantine read/write."""
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": PLAYER_ID, "provider_player_id": "78123"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id="78123", provider_team_id="LAR",
            raw_player_name="Someone", raw_position="WR",
        )
    assert result == ActivationResult(outcome="resolved", player_id=PLAYER_ID)


@pytest.mark.asyncio
@respx.mock
async def test_safe_unseen_player_is_created_and_linked():
    """Rules A/C/E: a genuinely unseen provider_player_id, with a
    resolvable team and no existing-player name conflict, is created
    fresh -- provider-ID-first, never from name alone."""
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": TEAM_ID, "provider_team_id": "SF"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": NEW_PLAYER_ID}])
    )
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(201)
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id="99001", provider_team_id="SF",
            raw_player_name="Brand New Player", raw_position="TE",
        )

    assert result == ActivationResult(outcome="resolved", player_id=NEW_PLAYER_ID)
    insert_body = json.loads(insert_route.calls.last.request.content)
    assert insert_body == {"name": "Brand New Player", "team_id": TEAM_ID, "position": "TE"}
    link_body = json.loads(link_route.calls.last.request.content)
    assert link_body == {
        "player_id": NEW_PLAYER_ID,
        "provider_name": "mysportsfeeds",
        "provider_player_id": "99001",
    }


@pytest.mark.asyncio
@respx.mock
async def test_missing_provider_team_id_quarantines_team_unresolved():
    """Rule D: no provider_team_id at all -- never create, quarantine."""
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    _mock_empty_quarantine_check()
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(
        return_value=httpx.Response(201, json=[{"id": QUARANTINE_ID}])
    )
    players_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": "should-not-be-created"}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id="99002", provider_team_id=None,
            raw_player_name="No Team Player", raw_position="RB",
        )

    assert result == ActivationResult(outcome="quarantined", quarantine_id=QUARANTINE_ID, conflict_type="team_unresolved")
    assert players_insert_route.call_count == 0
    body = json.loads(insert_route.calls.last.request.content)
    assert body["conflict_type"] == "team_unresolved"
    assert body["provider_player_id"] == "99002"


@pytest.mark.asyncio
@respx.mock
async def test_unmapped_provider_team_id_quarantines_team_unresolved():
    """Rule C/D: provider_team_id is present but has no team_provider_ids
    mapping for mysportsfeeds -- still team_unresolved, still no create."""
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    _mock_empty_quarantine_check()
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(
        return_value=httpx.Response(201, json=[{"id": QUARANTINE_ID}])
    )
    players_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": "should-not-be-created"}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id="99003", provider_team_id="XX",
            raw_player_name="Unmapped Team Player", raw_position="LB",
        )

    assert result.outcome == "quarantined"
    assert result.conflict_type == "team_unresolved"
    assert players_insert_route.call_count == 0
    assert insert_route.called


@pytest.mark.asyncio
@respx.mock
async def test_malformed_identity_quarantines_without_any_other_lookup():
    """Rule H: no usable provider_player_id at all -- quarantine
    immediately, never even attempting resolve_player_ids/team
    resolution (no route registered for player_provider_ids GET or
    team_provider_ids at all -- a call to either would fail the test
    with an unmocked-request error)."""
    _mock_empty_quarantine_check()
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(
        return_value=httpx.Response(201, json=[{"id": QUARANTINE_ID}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id=None, provider_team_id="SF",
            raw_player_name="Ghost Entry", raw_position=None,
        )

    assert result == ActivationResult(outcome="quarantined", quarantine_id=QUARANTINE_ID, conflict_type="malformed_identity")
    body = json.loads(insert_route.calls.last.request.content)
    assert body["provider_player_id"] is None
    assert body["conflict_type"] == "malformed_identity"


@pytest.mark.asyncio
@respx.mock
async def test_ambiguous_name_similarity_quarantines_never_merges():
    """Rules F/G: an existing canonical player on the resolved team,
    without a mysportsfeeds mapping yet, whose name is similar enough to
    be a plausible duplicate -- quarantine with candidate_player_id set,
    never auto-merged, never created as a second player."""
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        side_effect=lambda request: (
            httpx.Response(200, json=[])
            if "player_id" not in request.url.params
            else httpx.Response(200, json=[])
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": TEAM_ID, "provider_team_id": "NE"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(200, json=[{"id": "existing-player-1", "name": "Drake Maye"}])
    )
    _mock_empty_quarantine_check()
    quarantine_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(
        return_value=httpx.Response(201, json=[{"id": QUARANTINE_ID}])
    )
    players_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": "should-not-be-created"}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id="99004", provider_team_id="NE",
            raw_player_name="Drake May", raw_position="QB",
        )

    assert result.outcome == "quarantined"
    assert result.conflict_type == "ambiguous_match"
    assert result.quarantine_id == QUARANTINE_ID
    assert players_insert_route.call_count == 0
    body = json.loads(quarantine_insert_route.calls.last.request.content)
    assert body["candidate_player_id"] == "existing-player-1"


@pytest.mark.asyncio
@respx.mock
async def test_name_similarity_skips_players_already_mapped_to_provider():
    """The ambiguity check only ever compares against team players who do
    NOT yet have a mysportsfeeds mapping -- an already-mapped namesake is
    not a fresh ambiguity, it's already-resolved identity, so a brand new
    unseen player is safely created even though a similarly-named,
    already-mapped player exists on the same team."""
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        side_effect=lambda request: (
            httpx.Response(200, json=[{"player_id": "existing-player-1"}])
            if request.url.params.get("player_id")
            else httpx.Response(200, json=[])
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": TEAM_ID, "provider_team_id": "NE"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(200, json=[{"id": "existing-player-1", "name": "Drake Maye"}])
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": NEW_PLAYER_ID}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id="99005", provider_team_id="NE",
            raw_player_name="Drake May", raw_position="QB",
        )

    assert result == ActivationResult(outcome="resolved", player_id=NEW_PLAYER_ID)
    assert insert_route.called


@pytest.mark.asyncio
@respx.mock
async def test_provider_id_collision_rolls_back_orphan_and_quarantines():
    """Rule H (id_collision): resolve_player_ids finds nothing, but
    linking the freshly-created player's provider identity hits a real
    23505-style conflict on (provider_name, provider_player_id) --
    the just-created players row is compensating-rolled-back (DELETE),
    never left as an unlinked orphan, and the case is quarantined."""
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": TEAM_ID, "provider_team_id": "SF"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": NEW_PLAYER_ID}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(409))
    delete_route = respx.delete(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    _mock_empty_quarantine_check()
    quarantine_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(
        return_value=httpx.Response(201, json=[{"id": QUARANTINE_ID}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id="99006", provider_team_id="SF",
            raw_player_name="Collision Case", raw_position="OL",
        )

    assert result == ActivationResult(outcome="quarantined", quarantine_id=QUARANTINE_ID, conflict_type="id_collision")
    assert delete_route.called
    assert delete_route.calls.last.request.url.params["id"] == f"eq.{NEW_PLAYER_ID}"
    body = json.loads(quarantine_insert_route.calls.last.request.content)
    assert body["conflict_type"] == "id_collision"
    assert body["provider_player_id"] == "99006"


@pytest.mark.asyncio
@respx.mock
async def test_repeated_quarantine_call_is_idempotent_no_duplicate_row():
    """Rule J + HQ's explicit duplicate-prevention requirement: calling
    the same unresolvable case twice returns the same quarantine row --
    the second call's check-then-insert finds the first call's row and
    never inserts a second one."""
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(
        return_value=httpx.Response(201, json=[{"id": QUARANTINE_ID}])
    )

    check_calls = {"n": 0}

    def _check_side_effect(request: httpx.Request) -> httpx.Response:
        check_calls["n"] += 1
        if check_calls["n"] == 1:
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json=[{"id": QUARANTINE_ID, "provider_player_id": "99007", "raw_player_name": None, "conflict_type": "team_unresolved"}],
        )

    respx.get(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(side_effect=_check_side_effect)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        first = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id="99007", provider_team_id="ZZ",
            raw_player_name="Retry Case", raw_position="DB",
        )
        second = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id="99007", provider_team_id="ZZ",
            raw_player_name="Retry Case", raw_position="DB",
        )

    assert first.quarantine_id == QUARANTINE_ID
    assert second.quarantine_id == QUARANTINE_ID
    assert insert_route.call_count == 1  # never inserted a second row


@pytest.mark.asyncio
@respx.mock
async def test_quarantined_player_does_not_block_a_safe_peer():
    """Rule I: one player's quarantine (malformed identity here) is
    followed, in the same game/caller loop, by a second, unrelated
    player who resolves normally -- proving the function never raises
    for a quarantine outcome and a caller can safely continue iterating
    a roster."""
    _mock_empty_quarantine_check()
    respx.post(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(
        return_value=httpx.Response(201, json=[{"id": QUARANTINE_ID}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": TEAM_ID, "provider_team_id": "SF"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": NEW_PLAYER_ID}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        quarantined_result = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id=None, provider_team_id="SF",
            raw_player_name="Malformed Peer", raw_position=None,
        )
        safe_peer_result = await activate_msf_player(
            client, _headers(), game_id=GAME_ID,
            provider_player_id="99008", provider_team_id="SF",
            raw_player_name="Safe Peer", raw_position="K",
        )

    assert quarantined_result.outcome == "quarantined"
    assert safe_peer_result == ActivationResult(outcome="resolved", player_id=NEW_PLAYER_ID)
