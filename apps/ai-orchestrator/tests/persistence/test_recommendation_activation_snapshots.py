"""Tests for app.persistence.recommendation_activation_snapshots (Milestone 5.3)."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.persistence.recommendation_activation_snapshots import (
    ActivationSnapshotError,
    persist_activation_snapshot,
    persist_activation_snapshot_leg,
    persist_activation_snapshot_source_product,
    persist_lifecycle_event,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


# --- persist_activation_snapshot ---


@pytest.mark.asyncio
@respx.mock
async def test_persist_activation_snapshot_sends_all_fields_and_returns_id():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(201, json=[{"id": "snap-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        snapshot_id = await persist_activation_snapshot(
            client,
            _headers(),
            recommendation_product_id="prod-1",
            strategy_version="v1",
            recommendation_product_explanation_id="expl-1",
        )
    assert snapshot_id == "snap-1"
    sent = json.loads(route.calls.last.request.content)
    assert sent == {
        "recommendation_product_id": "prod-1",
        "strategy_version": "v1",
        "recommendation_product_explanation_id": "expl-1",
    }


@pytest.mark.asyncio
@respx.mock
async def test_persist_activation_snapshot_allows_null_explanation_id():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(201, json=[{"id": "snap-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await persist_activation_snapshot(
            client,
            _headers(),
            recommendation_product_id="prod-1",
            strategy_version="v1",
            recommendation_product_explanation_id=None,
        )
    sent = json.loads(route.calls.last.request.content)
    assert sent["recommendation_product_explanation_id"] is None


@pytest.mark.asyncio
@respx.mock
async def test_persist_activation_snapshot_raises_on_error():
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(500, text="db error")
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ActivationSnapshotError):
            await persist_activation_snapshot(
                client,
                _headers(),
                recommendation_product_id="prod-1",
                strategy_version="v1",
                recommendation_product_explanation_id=None,
            )


# --- persist_activation_snapshot_leg ---


@pytest.mark.asyncio
@respx.mock
async def test_persist_activation_snapshot_leg_sends_all_fields_and_returns_id():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(201, json=[{"id": "snap-leg-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row_id = await persist_activation_snapshot_leg(
            client, _headers(), activation_snapshot_id="snap-1", recommendation_leg_id="leg-1", leg_order=2
        )
    assert row_id == "snap-leg-1"
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"activation_snapshot_id": "snap-1", "recommendation_leg_id": "leg-1", "leg_order": 2}


@pytest.mark.asyncio
@respx.mock
async def test_persist_activation_snapshot_leg_raises_on_error():
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(500, text="db error")
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ActivationSnapshotError):
            await persist_activation_snapshot_leg(
                client, _headers(), activation_snapshot_id="snap-1", recommendation_leg_id="leg-1", leg_order=1
            )


# --- persist_activation_snapshot_source_product ---


@pytest.mark.asyncio
@respx.mock
async def test_persist_activation_snapshot_source_product_sends_all_fields_and_returns_id():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_source_products").mock(
        return_value=httpx.Response(201, json=[{"id": "snap-src-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row_id = await persist_activation_snapshot_source_product(
            client, _headers(), activation_snapshot_id="snap-1", source_recommendation_product_id="prod-nobet-1"
        )
    assert row_id == "snap-src-1"
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"activation_snapshot_id": "snap-1", "source_recommendation_product_id": "prod-nobet-1"}


@pytest.mark.asyncio
@respx.mock
async def test_persist_activation_snapshot_source_product_raises_on_error():
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_source_products").mock(
        return_value=httpx.Response(500, text="db error")
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ActivationSnapshotError):
            await persist_activation_snapshot_source_product(
                client, _headers(), activation_snapshot_id="snap-1", source_recommendation_product_id="prod-nobet-1"
            )


# --- persist_lifecycle_event ---


@pytest.mark.asyncio
@respx.mock
async def test_persist_lifecycle_event_sends_all_fields_and_returns_id():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(
        return_value=httpx.Response(201, json=[{"id": "event-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        event_id = await persist_lifecycle_event(
            client, _headers(), recommendation_product_id="prod-1", event_type="ACTIVATED"
        )
    assert event_id == "event-1"
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"recommendation_product_id": "prod-1", "event_type": "ACTIVATED", "reason": None}


@pytest.mark.asyncio
@respx.mock
async def test_persist_lifecycle_event_with_reason():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(
        return_value=httpx.Response(201, json=[{"id": "event-2"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await persist_lifecycle_event(
            client, _headers(), recommendation_product_id="prod-1", event_type="WITHDRAWN", reason="line moved"
        )
    sent = json.loads(route.calls.last.request.content)
    assert sent["event_type"] == "WITHDRAWN"
    assert sent["reason"] == "line moved"


@pytest.mark.asyncio
@respx.mock
async def test_persist_lifecycle_event_raises_on_error():
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(
        return_value=httpx.Response(500, text="db error")
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ActivationSnapshotError):
            await persist_lifecycle_event(client, _headers(), recommendation_product_id="prod-1", event_type="ACTIVATED")
