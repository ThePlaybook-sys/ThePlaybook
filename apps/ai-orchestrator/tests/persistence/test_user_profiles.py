"""Tests for app.persistence.user_profiles (Milestone 4.6, Decision F)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.user_profiles import UserProfilesReadError, read_user_profile

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_read_user_profile_returns_row():
    row = {"id": "u1", "risk_tolerance": "moderate", "preferred_unit_size": 25.0, "optional_bankroll": 1000.0}
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(return_value=httpx.Response(200, json=[row]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_user_profile(client, _headers(), user_id="u1")
    assert result == row


@pytest.mark.asyncio
@respx.mock
async def test_read_user_profile_incomplete_real_style_profile_has_null_bankroll():
    """Matches every real (non-fixture) user_profiles row confirmed live
    in dev: onboarding never completed, every bankroll-relevant field
    NULL."""
    row = {"id": "u2", "risk_tolerance": None, "preferred_unit_size": None, "optional_bankroll": None}
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(return_value=httpx.Response(200, json=[row]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_user_profile(client, _headers(), user_id="u2")
    assert result["optional_bankroll"] is None
    assert result["risk_tolerance"] is None


@pytest.mark.asyncio
@respx.mock
async def test_read_user_profile_returns_none_when_missing():
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_user_profile(client, _headers(), user_id="does-not-exist")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_read_user_profile_raises_on_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(UserProfilesReadError):
            await read_user_profile(client, _headers(), user_id="u1")
