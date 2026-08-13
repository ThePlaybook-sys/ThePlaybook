"""Full internal pipeline proof (Phase 3B, approved 2026-08-11):

    fixture-backed provider response
    -> TheOddsApiOddsAdapter (real, production-shaped)
    -> CachingAdapter (3A's cache boundary)
    -> app.persistence.odds_snapshots (real httpx/PostgREST write)
    -> downstream read

Every HTTP boundary -- the vendor and Supabase both -- is intercepted by
respx, so this test is fully deterministic and needs no live network or
credentials. It's the concrete proof for the "no downstream caller can
tell whether the adapter was backed by the fixture transport or the real
one" requirement: the persistence and read functions below only ever see
normalized `OddsLine`/`AdapterResponse` objects, never a vendor payload.
"""
from __future__ import annotations

import os

import httpx
import pytest
import respx

from app.adapters.cache import CachingAdapter, InMemoryCacheBackend
from app.adapters.models import AdapterResponse, OddsLine
from app.adapters.providers.the_odds_api import TheOddsApiOddsAdapter
from app.persistence.odds_snapshots import persist_odds_lines, read_latest_odds_snapshots
from tests.adapters.the_odds_api_fixtures import load

ODDS_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
SUPABASE_URL = "https://test-project.supabase.co"

GAME_CHIEFS_RAVENS = "e912304de2b25f2879b0293fd6a48ef4"
GAME_CHIEFS_RAVENS_DB_ID = "b1000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _supabase_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


@pytest.mark.asyncio
@respx.mock
async def test_fixture_to_adapter_to_cache_to_persistence_to_downstream_read():
    # 1. Vendor boundary — fixture-backed, respx-intercepted.
    odds_route = respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json"))
    )

    adapter = TheOddsApiOddsAdapter(
        client=httpx.AsyncClient(base_url="https://api.the-odds-api.com"),
        api_key="test-key",
    )
    caching = CachingAdapter(adapter, InMemoryCacheBackend(), ttl_seconds=30)

    # 2. Adapter -> cache boundary.
    response = await caching.call(
        "fetch_odds", [GAME_CHIEFS_RAVENS], response_model=AdapterResponse[list[OddsLine]]
    )
    assert response.from_cache is False
    assert len(response.value) > 0

    # 3. Persistence boundary — Supabase PostgREST, also respx-intercepted.
    # No vendor-shaped data crosses this boundary, only normalized OddsLine.
    # Game resolution goes through game_provider_ids (Phase 3E-1, Decision 2),
    # not games.external_provider_id directly.
    game_lookup_route = respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"game_id": GAME_CHIEFS_RAVENS_DB_ID, "provider_game_id": GAME_CHIEFS_RAVENS}
            ],
        )
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(
        return_value=httpx.Response(201)
    )

    written_count = await persist_odds_lines(response)
    assert written_count == len(response.value)
    assert game_lookup_route.called
    assert insert_route.called

    inserted_rows = respx.calls.last.request.content
    import json as _json

    parsed_rows = _json.loads(inserted_rows)
    assert all(row["game_id"] == GAME_CHIEFS_RAVENS_DB_ID for row in parsed_rows)
    assert {row["market_type"] for row in parsed_rows} == {"moneyline", "spread", "total"}

    # 4. Downstream read — proves a caller reading persisted data back never
    # touches the adapter or the vendor shape at all.
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"game_id": GAME_CHIEFS_RAVENS_DB_ID, "provider_game_id": GAME_CHIEFS_RAVENS}
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "c1000000-0000-0000-0000-000000000001",
                    "game_id": GAME_CHIEFS_RAVENS_DB_ID,
                    "sportsbook": "draftkings",
                    "market_type": "moneyline",
                    "line_data": {"outcomes": [{"name": "Kansas City Chiefs", "price": -150}]},
                    "captured_at": "2026-09-14T12:00:00Z",
                }
            ],
        )
    )
    read_back = await read_latest_odds_snapshots(GAME_CHIEFS_RAVENS)
    assert len(read_back) == 1
    assert read_back[0]["sportsbook"] == "draftkings"

    assert odds_route.call_count == 1  # cache boundary means one real vendor call total


@pytest.mark.asyncio
@respx.mock
async def test_lines_for_unresolved_games_are_skipped_not_silently_written():
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json"))
    )
    adapter = TheOddsApiOddsAdapter(
        client=httpx.AsyncClient(base_url="https://api.the-odds-api.com"),
        api_key="test-key",
    )
    response = await adapter.fetch_odds([GAME_CHIEFS_RAVENS])

    # Supabase has no matching game_provider_ids row for this external id at all.
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(
        return_value=httpx.Response(201)
    )

    written_count = await persist_odds_lines(response)
    assert written_count == 0
    assert not insert_route.called
