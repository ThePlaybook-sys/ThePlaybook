"""Tests for app.persistence.player_identity (Phase 3E-8, Decision 1).

Mirrors test_team_identity.py's structure -- same properties Mac's 3E-1/
3E-3 checkpoints required for games/teams, applied to players: provider ->
internal resolution, reverse resolution via ensure_player's create path,
unknown player stays absent (never guessed), and ensure_player's
resolve-before-create idempotency prevents a duplicate players row for an
already-known provider identity.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.persistence.player_identity import PlayerIdentityError, ensure_player, link_provider_player_id, resolve_player_ids

SUPABASE_URL = "https://test-project.supabase.co"
PLAYER_ID = "c4000000-0000-0000-0000-000000000001"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_resolve_player_ids_maps_provider_id_to_internal_id():
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": PLAYER_ID, "provider_player_id": "24924"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_player_ids(
            client, _headers(), provider_name="sportsdataio", provider_player_ids=["24924"]
        )
    assert result == {"24924": PLAYER_ID}


@pytest.mark.asyncio
@respx.mock
async def test_unmapped_provider_player_id_is_absent_not_guessed():
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_player_ids(
            client, _headers(), provider_name="sportsdataio", provider_player_ids=["99999999"]
        )
    assert result == {}


@pytest.mark.asyncio
async def test_resolve_player_ids_empty_input_makes_no_call():
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_player_ids(
            client, _headers(), provider_name="sportsdataio", provider_player_ids=[]
        )
    assert result == {}


@pytest.mark.asyncio
@respx.mock
async def test_resolve_player_ids_raises_on_non_200():
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(PlayerIdentityError):
            await resolve_player_ids(client, _headers(), provider_name="sportsdataio", provider_player_ids=["24924"])


@pytest.mark.asyncio
@respx.mock
async def test_link_provider_player_id_upserts_on_conflict():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await link_provider_player_id(
            client, _headers(), player_id=PLAYER_ID, provider_name="sportsdataio", provider_player_id="24924"
        )
    request = route.calls.last.request
    assert request.url.params["on_conflict"] == "player_id,provider_name"
    assert request.headers["Prefer"] == "resolution=merge-duplicates"
    body = json.loads(request.content)
    assert body == {"player_id": PLAYER_ID, "provider_name": "sportsdataio", "provider_player_id": "24924"}


@pytest.mark.asyncio
@respx.mock
async def test_link_provider_player_id_raises_on_failure():
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(409))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(PlayerIdentityError):
            await link_provider_player_id(
                client, _headers(), player_id=PLAYER_ID, provider_name="sportsdataio", provider_player_id="24924"
            )


@pytest.mark.asyncio
@respx.mock
async def test_ensure_player_creates_and_links_on_first_sight():
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": PLAYER_ID}])
    )
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result_id = await ensure_player(
            client, _headers(), provider_name="sportsdataio", provider_player_id="24924",
            name="Xavier Worthy", team_id="team-kc", position="WR",
        )

    assert result_id == PLAYER_ID
    assert insert_route.called
    insert_body = json.loads(insert_route.calls.last.request.content)
    assert insert_body == {"name": "Xavier Worthy", "team_id": "team-kc", "position": "WR"}
    link_body = json.loads(link_route.calls.last.request.content)
    assert link_body == {"player_id": PLAYER_ID, "provider_name": "sportsdataio", "provider_player_id": "24924"}


@pytest.mark.asyncio
@respx.mock
async def test_ensure_player_is_idempotent_no_duplicate_row_on_second_call():
    """Duplicate provider identity prevention: a second call for the same
    (provider_name, provider_player_id) resolves via the existing mapping
    and never re-inserts into players."""
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": PLAYER_ID, "provider_player_id": "24924"}])
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": "should-not-be-used"}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result_id = await ensure_player(
            client, _headers(), provider_name="sportsdataio", provider_player_id="24924",
            name="Xavier Worthy", team_id="team-kc", position="WR",
        )

    assert result_id == PLAYER_ID  # resolved from the existing mapping
    assert insert_route.call_count == 0  # never inserted a second players row


@pytest.mark.asyncio
@respx.mock
async def test_ensure_player_raises_on_players_insert_failure():
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(PlayerIdentityError):
            await ensure_player(
                client, _headers(), provider_name="sportsdataio", provider_player_id="24924",
                name="Xavier Worthy", team_id="team-kc", position="WR",
            )
