"""Tests for app.persistence.subscriptions (Milestone 4.7, Elite trigger)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.subscriptions import SubscriptionsReadError, read_subscription_tier

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_read_subscription_tier_returns_elite():
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(200, json=[{"tier": "elite"}]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        tier = await read_subscription_tier(client, _headers(), user_id="u1")
    assert tier == "elite"


@pytest.mark.asyncio
@respx.mock
async def test_read_subscription_tier_returns_free():
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(200, json=[{"tier": "free"}]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        tier = await read_subscription_tier(client, _headers(), user_id="u1")
    assert tier == "free"


@pytest.mark.asyncio
@respx.mock
async def test_read_subscription_tier_only_considers_active_status():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await read_subscription_tier(client, _headers(), user_id="u1")
    assert route.calls.last.request.url.params["status"] == "eq.active"


@pytest.mark.asyncio
@respx.mock
async def test_read_subscription_tier_returns_none_when_missing():
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        tier = await read_subscription_tier(client, _headers(), user_id="does-not-exist")
    assert tier is None


@pytest.mark.asyncio
@respx.mock
async def test_read_subscription_tier_raises_on_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(SubscriptionsReadError):
            await read_subscription_tier(client, _headers(), user_id="u1")
