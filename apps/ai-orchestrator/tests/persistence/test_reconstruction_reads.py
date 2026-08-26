"""Tests for app.persistence.reconstruction_reads (Milestone 5.3)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.reconstruction_reads import (
    ReconstructionReadError,
    read_activation_snapshot,
    read_activation_snapshot_legs,
    read_activation_snapshot_source_products,
    read_latest_user_selection,
    read_leg_explanation_by_leg_id,
    read_product_explanation_by_id,
    read_recommendation_leg,
    read_recommendation_product,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_read_recommendation_product_returns_none_when_missing():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await read_recommendation_product(client, _headers(), recommendation_product_id="prod-1")
    assert row is None


@pytest.mark.asyncio
@respx.mock
async def test_read_recommendation_product_returns_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-1", "recommendation_type": "single"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await read_recommendation_product(client, _headers(), recommendation_product_id="prod-1")
    assert row["recommendation_type"] == "single"


@pytest.mark.asyncio
@respx.mock
async def test_read_recommendation_product_raises_on_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ReconstructionReadError):
            await read_recommendation_product(client, _headers(), recommendation_product_id="prod-1")


@pytest.mark.asyncio
@respx.mock
async def test_read_activation_snapshot_returns_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": "expl-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await read_activation_snapshot(client, _headers(), recommendation_product_id="prod-1")
    assert row["strategy_version"] == "v1"


@pytest.mark.asyncio
@respx.mock
async def test_read_activation_snapshot_legs_orders_by_leg_order():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(200, json=[{"recommendation_leg_id": "leg-1", "leg_order": 1}, {"recommendation_leg_id": "leg-2", "leg_order": 2}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_activation_snapshot_legs(client, _headers(), activation_snapshot_id="snap-1")
    assert [r["leg_order"] for r in rows] == [1, 2]
    assert route.calls.last.request.url.params["order"] == "leg_order.asc"


@pytest.mark.asyncio
@respx.mock
async def test_read_activation_snapshot_source_products_returns_rows():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_source_products").mock(
        return_value=httpx.Response(200, json=[{"source_recommendation_product_id": "prod-nobet-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_activation_snapshot_source_products(client, _headers(), activation_snapshot_id="snap-bp")
    assert rows == [{"source_recommendation_product_id": "prod-nobet-1"}]


@pytest.mark.asyncio
@respx.mock
async def test_read_recommendation_leg_returns_none_when_missing():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await read_recommendation_leg(client, _headers(), recommendation_leg_id="leg-1")
    assert row is None


@pytest.mark.asyncio
@respx.mock
async def test_read_product_explanation_by_id_returns_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(200, json=[{"id": "expl-1", "why_this_shape": "reason"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await read_product_explanation_by_id(client, _headers(), explanation_id="expl-1")
    assert row["why_this_shape"] == "reason"


@pytest.mark.asyncio
@respx.mock
async def test_read_leg_explanation_by_leg_id_returns_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-expl-1", "why_selected": "reason"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await read_leg_explanation_by_leg_id(client, _headers(), recommendation_leg_id="leg-1")
    assert row["why_selected"] == "reason"


@pytest.mark.asyncio
@respx.mock
async def test_read_latest_user_selection_returns_none_when_no_row_ever_written():
    respx.get(f"{SUPABASE_URL}/rest/v1/user_recommendation_selections").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await read_latest_user_selection(
            client, _headers(), recommendation_product_id="prod-1", recommendation_leg_id="leg-1", user_id="user-1"
        )
    assert row is None


@pytest.mark.asyncio
@respx.mock
async def test_read_latest_user_selection_orders_by_created_at_desc_limit_1():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/user_recommendation_selections").mock(
        return_value=httpx.Response(200, json=[{"id": "sel-2", "stake": 25.0}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await read_latest_user_selection(
            client, _headers(), recommendation_product_id="prod-1", recommendation_leg_id="leg-1", user_id="user-1"
        )
    assert row["stake"] == 25.0
    params = route.calls.last.request.url.params
    assert params["order"] == "created_at.desc"
    assert params["limit"] == "1"
