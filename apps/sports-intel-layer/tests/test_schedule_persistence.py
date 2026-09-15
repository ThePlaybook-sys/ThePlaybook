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
        venue_lat=47.5952,
        venue_long=-122.331625,
        venue_type="outdoor",
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
    # Phase 3E-6, Option A: venue fields refreshed on every ingestion,
    # same as every other mutable field above.
    assert inserted_body["venue_lat"] == 47.5952
    assert inserted_body["venue_long"] == -122.331625
    assert inserted_body["venue_type"] == "outdoor"

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


@pytest.mark.asyncio
@respx.mock
async def test_missing_venue_metadata_persists_as_null_not_fabricated():
    """Phase 3E-6, Option A: an entry with no venue metadata at all (the
    adapter's own legitimate 'unknown' case) writes null for all three
    fields, never a guessed/defaulted value."""
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(201, json=[{"id": NEW_GAME_DB_ID}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(201))

    entry = _entry("202610130", venue_lat=None, venue_long=None, venue_type=None)
    response = AdapterResponse(value=[entry], source="sportsdataio")
    await persist_schedule_entries(response)

    inserted_body = json.loads(insert_route.calls.last.request.content)
    assert inserted_body["venue_lat"] is None
    assert inserted_body["venue_long"] is None
    assert inserted_body["venue_type"] is None


# --------------------------------------------------------------------------
# Final is terminal (2026-09-15, "CANONICAL SCHEDULE + FINALIZATION HARDENING").
#
# With Master Refresh V2 persisting the full season, every already-played game
# is re-seen on every daily refresh -- and SportsDataIO can still describe a
# played game as "Scheduled". A refresh must never undo a real finalization.
# The guard is Postgres's own `finalized_at=is.null` filter, so these tests
# mock that filter faithfully rather than ignoring the query params.
# --------------------------------------------------------------------------


def _mock_existing_mapping():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(
            200, json=[{"game_id": EXISTING_GAME_DB_ID, "provider_game_id": "202610130"}]
        )
    )


def _mock_games_patch(*, finalized: bool):
    """Faithful stand-in for the database: a PATCH filtered on
    `finalized_at=is.null` matches zero rows when the game is finalized."""

    def _respond(request: httpx.Request) -> httpx.Response:
        guarded = request.url.params.get("finalized_at") == "is.null"
        if guarded and finalized:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[{"id": EXISTING_GAME_DB_ID}])

    return respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_respond)


@pytest.mark.asyncio
@respx.mock
async def test_finalized_game_keeps_its_status_when_a_refresh_calls_it_scheduled():
    _mock_existing_mapping()
    patch_route = _mock_games_patch(finalized=True)

    response = AdapterResponse(value=[_entry("202610130", status="scheduled")], source="sportsdataio")
    created, updated = await persist_schedule_entries(response)

    assert (created, updated) == (0, 1)
    assert patch_route.call_count == 2  # guarded attempt, then the status-less retry

    guarded_body = json.loads(patch_route.calls[0].request.content)
    assert guarded_body["status"] == "scheduled"  # attempted...
    assert patch_route.calls[0].request.url.params["finalized_at"] == "is.null"  # ...but guarded

    retained_body = json.loads(patch_route.calls[1].request.content)
    assert "status" not in retained_body  # the downgrade never lands
    assert "final_score" not in retained_body and "finalized_at" not in retained_body
    # Everything else about a played game still reconciles.
    assert retained_body["stadium"] == "Lumen Field"
    assert retained_body["week"] == 1
    assert retained_body["venue_type"] == "outdoor"


@pytest.mark.asyncio
@respx.mock
async def test_unfinalized_game_still_gets_its_status_refreshed():
    _mock_existing_mapping()
    patch_route = _mock_games_patch(finalized=False)

    response = AdapterResponse(value=[_entry("202610130", status="live")], source="sportsdataio")
    created, updated = await persist_schedule_entries(response)

    assert (created, updated) == (0, 1)
    assert patch_route.call_count == 1  # no second write needed
    assert json.loads(patch_route.calls.last.request.content)["status"] == "live"
    assert patch_route.calls.last.request.url.params["finalized_at"] == "is.null"


@pytest.mark.asyncio
@respx.mock
async def test_the_guard_is_the_database_not_a_prior_read():
    """No read-then-write window exists to race through: nothing is read to
    decide whether to write `status` -- the filter travels with the write."""
    _mock_existing_mapping()
    games_get = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[])
    )
    _mock_games_patch(finalized=False)

    response = AdapterResponse(value=[_entry("202610130")], source="sportsdataio")
    await persist_schedule_entries(response)

    assert not games_get.called


@pytest.mark.asyncio
@respx.mock
async def test_a_failed_status_less_retry_is_raised_not_swallowed():
    _mock_existing_mapping()

    def _respond(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("finalized_at") == "is.null":
            return httpx.Response(200, json=[])
        return httpx.Response(500, text="db error")

    respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_respond)

    response = AdapterResponse(value=[_entry("202610130")], source="sportsdataio")
    with pytest.raises(PersistenceError, match="finalized game"):
        await persist_schedule_entries(response)


@pytest.mark.asyncio
@respx.mock
async def test_a_204_with_no_representation_is_treated_as_a_normal_update():
    """PostgREST can answer 204 with no body; that is not evidence of a guard
    hit, and must not trigger a spurious second write."""
    _mock_existing_mapping()
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(204)
    )

    response = AdapterResponse(value=[_entry("202610130")], source="sportsdataio")
    assert await persist_schedule_entries(response) == (0, 1)
    assert patch_route.call_count == 1
