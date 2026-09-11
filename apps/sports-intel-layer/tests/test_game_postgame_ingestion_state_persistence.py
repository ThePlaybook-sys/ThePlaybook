"""Tests for app.persistence.game_postgame_ingestion_state (Permanent Box
Score Worker Build, 2026-09-11)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.persistence.game_postgame_ingestion_state import (
    IngestionStateError,
    claim_game_for_capture,
    ensure_scheduled_row,
    get_ingestion_state,
    promote_due_scheduled_row,
    update_ingestion_state,
)

SUPABASE_URL = "https://test-project.supabase.co"
GAME_ID = "50d14afd-2861-4e07-b235-90ea857f004d"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_get_ingestion_state_returns_none_when_absent():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await get_ingestion_state(client, _headers(), game_id=GAME_ID)
    assert row is None


@pytest.mark.asyncio
@respx.mock
async def test_get_ingestion_state_raises_on_failure():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(IngestionStateError):
            await get_ingestion_state(client, _headers(), game_id=GAME_ID)


@pytest.mark.asyncio
@respx.mock
async def test_ensure_scheduled_row_creates_when_absent():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[])
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(201, json=[{"id": "row-1", "state": "scheduled", "attempt_count": 0}])
    )
    first_eligible = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await ensure_scheduled_row(client, _headers(), game_id=GAME_ID, first_eligible_at=first_eligible)

    assert row["state"] == "scheduled"
    body = json.loads(insert_route.calls.last.request.content)
    assert body["game_id"] == GAME_ID
    assert body["provider_name"] == "mysportsfeeds"
    assert body["state"] == "scheduled"
    assert body["next_eligible_attempt_at"] == first_eligible.isoformat()


@pytest.mark.asyncio
@respx.mock
async def test_ensure_scheduled_row_never_overwrites_existing_row():
    """Check-then-insert, not upsert -- an existing row (any state) is
    returned untouched; no POST is ever made."""
    existing = {"id": "row-1", "state": "capture_in_progress", "attempt_count": 1}
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[existing])
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(201, json=[{"id": "should-not-be-created"}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await ensure_scheduled_row(
            client, _headers(), game_id=GAME_ID,
            first_eligible_at=datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc),
        )

    assert row == existing
    assert insert_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_promote_due_scheduled_row_patches_state():
    route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await promote_due_scheduled_row(
            client, _headers(), game_id=GAME_ID, now=datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
        )
    body = json.loads(route.calls.last.request.content)
    assert body == {"state": "eligible_for_postgame_check"}
    assert route.calls.last.request.url.params["state"] == "eq.scheduled"


@pytest.mark.asyncio
@respx.mock
async def test_claim_game_for_capture_returns_row_on_success():
    route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 2, "state": "capture_in_progress"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await claim_game_for_capture(
            client, _headers(), game_id=GAME_ID, now=datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
        )
    assert row is not None
    assert row["attempt_count"] == 2
    assert route.calls.last.request.url.params["state"] == "eq.eligible_for_postgame_check"


@pytest.mark.asyncio
@respx.mock
async def test_claim_game_for_capture_returns_none_when_not_eligible():
    """A second claim against an already-claimed (or otherwise ineligible)
    row is a safe, silent no-op -- exactly the no-double-claim guarantee
    already proven for this table's own UPDATE shape."""
    respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await claim_game_for_capture(
            client, _headers(), game_id=GAME_ID, now=datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
        )
    assert row is None


@pytest.mark.asyncio
@respx.mock
async def test_update_ingestion_state_sends_arbitrary_fields():
    route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(204)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await update_ingestion_state(client, _headers(), game_id=GAME_ID, state="captured", attempt_count=1)
    body = json.loads(route.calls.last.request.content)
    assert body == {"state": "captured", "attempt_count": 1}


@pytest.mark.asyncio
async def test_update_ingestion_state_no_fields_makes_no_call():
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await update_ingestion_state(client, _headers(), game_id=GAME_ID)
