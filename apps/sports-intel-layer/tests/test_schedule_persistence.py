"""Unit tests for app.persistence.schedule (Phase 3E-1).

Covers the two ingestion paths persist_schedule_entries must support:
  - a brand-new provider+external-id pair creates a games row and links it
    via game_provider_ids;
  - an already-mapped provider+external-id pair updates the existing games
    row (including season_type/week) instead of creating a duplicate.

Also proves season_type/week survive normalization end to end: a
ScheduleEntry carrying them writes them into the games row's payload.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.adapters.models import AdapterResponse, ScheduleEntry
from app.persistence.schedule import PersistenceError, persist_schedule_entries

SUPABASE_URL = "https://test-project.supabase.co"
NEW_GAME_DB_ID = "b2000000-0000-0000-0000-000000000001"
EXISTING_GAME_DB_ID = "b2000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def _supabase_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _entry(game_external_id: str, **overrides) -> ScheduleEntry:
    fields = dict(
        game_external_id=game_external_id,
        home_team="SEA",
        away_team="NE",
        scheduled_start="2026-09-10T00:20:00Z",
        stadium="Lumen Field",
        status="scheduled",
        season_type="regular",
        week=1,
    )
    fields.update(overrides)
    return ScheduleEntry(**fields)


@pytest.mark.asyncio
@respx.mock
async def test_new_provider_game_id_creates_game_and_links_mapping():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(201, json=[{"id": NEW_GAME_DB_ID}])
    )
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(201)
    )

    response = AdapterResponse(value=[_entry("202610130")], source="sportsdataio")
    created, updated = await persist_schedule_entries(response)

    assert (created, updated) == (1, 0)
    assert insert_route.called
    inserted_body = json.loads(insert_route.calls.last.request.content)
    assert inserted_body["season_type"] == "regular"
    assert inserted_body["week"] == 1
    assert inserted_body["sport"] == "nfl"

    assert link_route.called
    link_body = json.loads(link_route.calls.last.request.content)
    assert link_body == {
        "game_id": NEW_GAME_DB_ID,
        "provider_name": "sportsdataio",
        "provider_game_id": "202610130",
    }


@pytest.mark.asyncio
@respx.mock
async def test_existing_mapping_updates_game_not_duplicate_create():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[{"game_id": EXISTING_GAME_DB_ID, "provider_game_id": "202610130"}],
        )
    )
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(204)
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(201, json=[{"id": "should-not-be-created"}])
    )

    response = AdapterResponse(
        value=[_entry("202610130", week=2, season_type="postseason")], source="sportsdataio"
    )
    created, updated = await persist_schedule_entries(response)

    assert (created, updated) == (0, 1)
    assert patch_route.called
    assert not insert_route.called
    assert patch_route.calls.last.request.url.params["id"] == f"eq.{EXISTING_GAME_DB_ID}"
    patched_body = json.loads(patch_route.calls.last.request.content)
    assert patched_body["week"] == 2
    assert patched_body["season_type"] == "postseason"


@pytest.mark.asyncio
@respx.mock
async def test_game_create_failure_raises_persistence_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(500, text="db error")
    )

    response = AdapterResponse(value=[_entry("202610130")], source="sportsdataio")
    with pytest.raises(PersistenceError):
        await persist_schedule_entries(response)


@pytest.mark.asyncio
async def test_empty_entries_is_a_no_op():
    response = AdapterResponse(value=[], source="sportsdataio")
    assert await persist_schedule_entries(response) == (0, 0)
