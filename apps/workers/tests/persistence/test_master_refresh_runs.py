"""Tests for app.persistence.master_refresh_runs (Milestone 4.9)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.master_refresh_runs import MasterRefreshRunsReadError, read_latest_eligible_run

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_returns_none_when_no_eligible_run_exists():
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_latest_eligible_run(client, _headers())
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_returns_the_row_when_one_eligible_run_exists():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1", "status": "success", "completed_at": "2026-08-24T12:00:00+00:00"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_latest_eligible_run(client, _headers())
    assert result["id"] == "run-1"
    sent_params = route.calls.last.request.url.params
    assert sent_params["status"] == "in.(success,partial)"


@pytest.mark.asyncio
@respx.mock
async def test_raises_on_non_200():
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(MasterRefreshRunsReadError):
            await read_latest_eligible_run(client, _headers())
