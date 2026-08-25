"""Tests for app.persistence.master_refresh_runs (Milestone 4.9)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.master_refresh_runs import (
    MasterRefreshRunsError,
    complete_master_refresh_run,
    start_master_refresh_run,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_start_master_refresh_run_creates_running_row_and_returns_id():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(201, json=[{"id": "run-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        run_id = await start_master_refresh_run(client, _headers())
    assert run_id == "run-1"
    import json

    sent = json.loads(route.calls.last.request.content)
    assert sent == {"status": "running"}


@pytest.mark.asyncio
@respx.mock
async def test_start_master_refresh_run_raises_on_failure():
    respx.post(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(MasterRefreshRunsError):
            await start_master_refresh_run(client, _headers())


@pytest.mark.asyncio
@respx.mock
async def test_complete_master_refresh_run_patches_by_id():
    route = respx.patch(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(204))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await complete_master_refresh_run(
            client,
            _headers(),
            run_id="run-1",
            status="partial",
            season_string="2026-REG",
            games_in_slate=13,
            completed_at_iso="2026-09-09T12:00:00+00:00",
        )
    request = route.calls.last.request
    assert request.url.params["id"] == "eq.run-1"
    import json

    sent = json.loads(request.content)
    assert sent["status"] == "partial"  # never silently upgraded to success
    assert sent["season_string"] == "2026-REG"
    assert sent["games_in_slate"] == 13


@pytest.mark.asyncio
@respx.mock
async def test_complete_master_refresh_run_raises_on_failure():
    respx.patch(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(MasterRefreshRunsError):
            await complete_master_refresh_run(
                client,
                _headers(),
                run_id="run-1",
                status="failed",
                season_string=None,
                games_in_slate=0,
                completed_at_iso="2026-09-09T12:00:00+00:00",
            )
