"""Phase 7 Controlled Real Odds Activation (2026-09-07): the API-credit
safety guard added to `app.workers.odds_worker` -- self-counted (never
dependent on a parsed, ASSUMED vendor header), configurable (never an
invented default), fails closed once the configured floor is reached.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.adapters.cache import InMemoryCacheBackend
from app.workers.odds_worker import run_odds_worker
from tests.test_odds_worker import (
    DB_GAME_KC_BAL,
    _game_row,
    _headers_env,
    _mock_credit_ledger,
    _mock_games,
    _mock_game_provider_ids,
    _mock_team_provider_ids,
    _odds_response,
)

SUPABASE_URL = "https://test-project.supabase.co"
ODDS_API_URL = "https://api.the-odds-api.com"
ODDS_URL = f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/odds"

_ONE_GAME = [_game_row(game_id=DB_GAME_KC_BAL, home="KC", away="BAL", scheduled_start="2026-09-14T17:00:00Z")]


async def _run(*, now, monkeypatch):
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(base_url=ODDS_API_URL) as odds_client:
        return await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            cache_backend=InMemoryCacheBackend(),
            now=now,
        )


_NOW = datetime(2026, 9, 14, 16, 55, tzinfo=timezone.utc)  # 5 min before kickoff -> due


@pytest.mark.asyncio
@respx.mock
async def test_guard_disabled_when_env_vars_unset_makes_real_call(monkeypatch):
    monkeypatch.delenv("THE_ODDS_API_MONTHLY_CREDIT_BUDGET", raising=False)
    monkeypatch.delenv("THE_ODDS_API_MIN_REMAINING_CREDITS", raising=False)
    _headers_env(monkeypatch)
    _mock_games(_ONE_GAME)
    _mock_team_provider_ids()
    _mock_game_provider_ids()
    _mock_credit_ledger()
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    result = await _run(now=_NOW, monkeypatch=monkeypatch)
    assert odds_route.call_count == 1
    assert result.status != "skipped_credit_guard"


@pytest.mark.asyncio
@respx.mock
async def test_guard_allows_call_when_remaining_above_floor(monkeypatch):
    monkeypatch.setenv("THE_ODDS_API_MONTHLY_CREDIT_BUDGET", "500")
    monkeypatch.setenv("THE_ODDS_API_MIN_REMAINING_CREDITS", "50")
    _headers_env(monkeypatch)
    _mock_games(_ONE_GAME)
    _mock_team_provider_ids()
    _mock_game_provider_ids()
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(
        return_value=httpx.Response(200, json=[{"credits_used_this_period": 100}])  # remaining = 400 > 50
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(
        return_value=httpx.Response(201, json=[{"credits_used_this_period": 103}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    result = await _run(now=_NOW, monkeypatch=monkeypatch)
    assert odds_route.call_count == 1
    assert result.status != "skipped_credit_guard"
    assert result.credits_used_this_period == 103


@pytest.mark.asyncio
@respx.mock
async def test_guard_blocks_call_when_remaining_at_or_below_floor(monkeypatch):
    monkeypatch.setenv("THE_ODDS_API_MONTHLY_CREDIT_BUDGET", "500")
    monkeypatch.setenv("THE_ODDS_API_MIN_REMAINING_CREDITS", "50")
    _headers_env(monkeypatch)
    _mock_games(_ONE_GAME)
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(
        return_value=httpx.Response(200, json=[{"credits_used_this_period": 450}])  # remaining = 50, not > 50
    )
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    result = await _run(now=_NOW, monkeypatch=monkeypatch)
    assert odds_route.call_count == 0  # never even attempted -- fails closed BEFORE the provider call
    assert result.status == "skipped_credit_guard"
    assert result.credits_used_this_period == 450


@pytest.mark.asyncio
@respx.mock
async def test_guard_bootstrap_no_ledger_row_yet_allows_call(monkeypatch):
    monkeypatch.setenv("THE_ODDS_API_MONTHLY_CREDIT_BUDGET", "500")
    monkeypatch.setenv("THE_ODDS_API_MIN_REMAINING_CREDITS", "50")
    _headers_env(monkeypatch)
    _mock_games(_ONE_GAME)
    _mock_team_provider_ids()
    _mock_game_provider_ids()
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(
        return_value=httpx.Response(201, json=[{"credits_used_this_period": 3}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    result = await _run(now=_NOW, monkeypatch=monkeypatch)
    assert odds_route.call_count == 1
    assert result.credits_used_this_period == 3


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_never_records_credit_usage(monkeypatch):
    monkeypatch.delenv("THE_ODDS_API_MONTHLY_CREDIT_BUDGET", raising=False)
    monkeypatch.delenv("THE_ODDS_API_MIN_REMAINING_CREDITS", raising=False)
    _headers_env(monkeypatch)
    _mock_games(_ONE_GAME)
    _mock_team_provider_ids()
    _mock_game_provider_ids()
    ledger_post = respx.post(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(
        return_value=httpx.Response(201, json=[{"credits_used_this_period": 3}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))
    respx.get(ODDS_URL).mock(return_value=_odds_response())
    cache = InMemoryCacheBackend()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(base_url=ODDS_API_URL) as odds_client:
        first = await run_odds_worker(
            supabase_client=supabase_client, the_odds_api_client=odds_client, the_odds_api_key="test-key",
            cache_backend=cache, now=_NOW,
        )
        second = await run_odds_worker(
            supabase_client=supabase_client, the_odds_api_client=odds_client, the_odds_api_key="test-key",
            cache_backend=cache, now=_NOW, last_polled_at={DB_GAME_KC_BAL: _NOW},
        )
    assert ledger_post.call_count == 1  # only the first, real (non-cached) call recorded usage
    assert first.credits_used_this_period == 3
