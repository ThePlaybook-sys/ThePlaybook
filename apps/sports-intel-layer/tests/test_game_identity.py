"""Unit tests for app.persistence.game_identity (Phase 3E-1, Decision 2).

Proves the two properties Mac's checkpoint explicitly required:
  1. A SportsDataIO id and a The Odds API id can both resolve to the SAME
     games.id -- game_provider_ids supports multiple providers per game.
  2. A provider id that has no mapping row is simply absent from the
     result -- callers decide what to do, resolve_game_ids doesn't guess
     or silently create anything.

Both Supabase boundaries are respx-intercepted -- no live network, no real
credentials, matching test_pipeline.py's existing convention.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.persistence.game_identity import GameIdentityError, link_provider_id, resolve_game_ids

SUPABASE_URL = "https://test-project.supabase.co"
GAME_ID = "b1000000-0000-0000-0000-000000000001"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_two_different_providers_resolve_to_the_same_game_id():
    # Two rows in game_provider_ids, one per provider, both pointing at GAME_ID --
    # exactly what the migration's live backfill + Decision 2 proof established
    # against real dev Supabase. The mock's side_effect filters by the request's
    # own provider_name param, so each call only ever sees its own provider's row,
    # proving resolution is genuinely per-provider and not coincidentally equal.
    rows_by_provider = {
        "eq.the_odds_api": [{"game_id": GAME_ID, "provider_game_id": "odds-evt-1"}],
        "eq.sportsdataio": [{"game_id": GAME_ID, "provider_game_id": "sdio-gamekey-1"}],
    }

    def _respond(request: httpx.Request) -> httpx.Response:
        provider_name = request.url.params["provider_name"]
        return httpx.Response(200, json=rows_by_provider[provider_name])

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_respond)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        odds_api_result = await resolve_game_ids(
            client, _headers(), provider_name="the_odds_api", provider_game_ids=["odds-evt-1"]
        )
        sportsdataio_result = await resolve_game_ids(
            client, _headers(), provider_name="sportsdataio", provider_game_ids=["sdio-gamekey-1"]
        )

    assert odds_api_result == {"odds-evt-1": GAME_ID}
    assert sportsdataio_result == {"sdio-gamekey-1": GAME_ID}
    # The actual cross-vendor identity proof: both providers' own ids
    # resolved to the exact same games.id -- no duplicate game involved.
    assert odds_api_result["odds-evt-1"] == sportsdataio_result["sdio-gamekey-1"]


@pytest.mark.asyncio
@respx.mock
async def test_unmapped_provider_id_is_absent_not_guessed():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_game_ids(
            client, _headers(), provider_name="sportsdataio", provider_game_ids=["unknown-id"]
        )
    assert result == {}


@pytest.mark.asyncio
async def test_resolve_game_ids_empty_input_makes_no_call():
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_game_ids(
            client, _headers(), provider_name="sportsdataio", provider_game_ids=[]
        )
    assert result == {}


@pytest.mark.asyncio
@respx.mock
async def test_resolve_game_ids_raises_on_non_200():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(500, text="db error")
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(GameIdentityError):
            await resolve_game_ids(
                client, _headers(), provider_name="sportsdataio", provider_game_ids=["x"]
            )


@pytest.mark.asyncio
@respx.mock
async def test_link_provider_id_upserts_on_conflict():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(201)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await link_provider_id(
            client,
            _headers(),
            game_id=GAME_ID,
            provider_name="sportsdataio",
            provider_game_id="sdio-gamekey-1",
        )
    assert route.called
    request = route.calls.last.request
    assert request.url.params["on_conflict"] == "game_id,provider_name"
    assert request.headers["Prefer"] == "resolution=merge-duplicates"
    body = json.loads(request.content)
    assert body == {
        "game_id": GAME_ID,
        "provider_name": "sportsdataio",
        "provider_game_id": "sdio-gamekey-1",
    }


@pytest.mark.asyncio
@respx.mock
async def test_link_provider_id_raises_on_failure():
    respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(409, text="conflict")
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(GameIdentityError):
            await link_provider_id(
                client,
                _headers(),
                game_id=GAME_ID,
                provider_name="sportsdataio",
                provider_game_id="sdio-gamekey-1",
            )
