"""Tests for the `MASTER_REFRESH_ENABLED` pause gate (2026-09-15, HQ-authorized
"CANONICAL SCHEDULE + FINALIZATION HARDENING", Part 3).

**What this replaces.** The pause was previously expressed by setting
`CRON_DISPATCH_TARGET` to an invalid sentinel
(`master-refresh-DISABLED-pending-authorization`), which made the dispatcher
raise, exit non-zero, and post a CRASHED deployment every single day -- an
intentional cost pause that was indistinguishable from real infrastructure
failure. The gate proven here is a clean no-op instead.

**The gate is explicit-opt-in, deliberately inverted from
`MSF_POSTGAME_ENABLED`.** Only a case-insensitive `"true"` runs the refresh;
unset, empty, `"false"`, and anything else pause it. The two flags fail safe in
opposite directions on purpose: a removed `MSF_POSTGAME_ENABLED` should keep
ingestion running, whereas a removed `MASTER_REFRESH_ENABLED` must never be
able to start spending SportsDataIO calls on its own.

respx runs in strict mode throughout with NO routes registered at all, so any
request of any kind -- provider or Supabase -- raises rather than passing
silently. That is the actual proof of "zero calls".
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.master_refresh.run import (
    MASTER_REFRESH_ENABLED_ENV,
    master_refresh_enabled,
    run_master_refresh,
    run_roster_refresh,
    run_schedule_refresh,
)

SUPABASE_URL = "https://test-project.supabase.co"
SPORTSDATAIO_URL = "https://api.sportsdata.io"


def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


@pytest.mark.parametrize("value", ["true", "TRUE", "True", " true "])
def test_only_an_explicit_true_enables_the_refresh(monkeypatch, value):
    monkeypatch.setenv(MASTER_REFRESH_ENABLED_ENV, value)
    assert master_refresh_enabled() is True


@pytest.mark.parametrize("value", ["false", "FALSE", "", "  ", "1", "yes", "enabled", "0"])
def test_everything_other_than_true_pauses(monkeypatch, value):
    """Strict by design: this gate guards paid provider calls, so a typo or a
    half-applied config change must fail closed rather than start spending."""
    monkeypatch.setenv(MASTER_REFRESH_ENABLED_ENV, value)
    assert master_refresh_enabled() is False


def test_an_unset_variable_pauses_rather_than_running(monkeypatch):
    """The fail-safe direction that matters: a deleted or never-created
    variable can never authorize spend."""
    monkeypatch.delenv(MASTER_REFRESH_ENABLED_ENV, raising=False)
    assert master_refresh_enabled() is False


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("entry_point", [run_master_refresh, run_schedule_refresh])
async def test_paused_refresh_makes_zero_calls_of_any_kind(monkeypatch, entry_point):
    _env(monkeypatch)
    monkeypatch.setenv(MASTER_REFRESH_ENABLED_ENV, "false")

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await entry_point(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
        )

    assert result.status == "paused"
    assert result.paused is True
    # Not one request left the process -- provider OR database. A single
    # unmocked call here would have raised instead.
    assert len(respx.calls) == 0


@pytest.mark.asyncio
@respx.mock
async def test_paused_roster_refresh_makes_zero_calls_too(monkeypatch):
    _env(monkeypatch)
    monkeypatch.delenv(MASTER_REFRESH_ENABLED_ENV, raising=False)

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_roster_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
        )

    assert result.status == "paused"
    assert len(respx.calls) == 0


@pytest.mark.asyncio
@respx.mock
async def test_a_paused_run_creates_no_master_refresh_runs_row(monkeypatch):
    """The gate is checked BEFORE `start_master_refresh_run`, so a pause never
    leaves a durable row claiming a run that did no work."""
    _env(monkeypatch)
    monkeypatch.setenv(MASTER_REFRESH_ENABLED_ENV, "false")
    runs_route = respx.post(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(201, json=[{"id": "mrr-1"}])
    )

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
        )

    assert not runs_route.called
    assert result.run_id is None


@pytest.mark.asyncio
@respx.mock
async def test_paused_is_not_a_failure_status(monkeypatch):
    """A caller derives its exit code from `status`. `paused` must be
    distinguishable from `failed`, so the cron exits 0 and stops posting a
    daily CRASHED deployment for a deliberate pause."""
    _env(monkeypatch)
    monkeypatch.setenv(MASTER_REFRESH_ENABLED_ENV, "false")

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_master_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
        )

    assert result.status == "paused"
    assert result.status != "failed"
    assert result.error is None
