"""Tests for app.workers.msf_postgame_worker._default_fetch_boxscore --
the ONE function in the permanent path that could ever make a real
MySportsFeeds call. NO real network call happens anywhere in this file:
respx intercepts httpx's transport entirely (the same technique used
throughout this codebase to test adapter fetch functions, e.g.
tests/adapters/test_sportsdataio_adapters.py), so these tests exercise
this function's real response-handling/header-parsing logic without
ever reaching MySportsFeeds. Nothing in this pass invokes this function
through the worker itself -- see test_msf_postgame_worker.py, which
injects fakes via the dependency-injection seam instead.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.workers.msf_postgame_worker import _default_fetch_boxscore

MSF_BASE_URL = "https://api.mysportsfeeds.com/v2.1/pull"
SEASON = "2026-2027-regular"
MSF_GAME_ID = "163542"
_PATH = f"/nfl/{SEASON}/games/{MSF_GAME_ID}/boxscore.json"


def _env(monkeypatch):
    monkeypatch.setenv("MYSPORTSFEEDS_API_KEY", "test-msf-key")


@pytest.mark.asyncio
@respx.mock
async def test_success_captures_real_cache_control_max_age(monkeypatch):
    _env(monkeypatch)
    respx.get(f"{MSF_BASE_URL}{_PATH}").mock(
        return_value=httpx.Response(
            200,
            json={"game": {"id": int(MSF_GAME_ID), "playedStatus": "COMPLETED"}},
            headers={"Cache-Control": "no-transform, max-age=10800"},
        )
    )

    result = await _default_fetch_boxscore(season=SEASON, msf_game_id=MSF_GAME_ID)

    assert result.status == "success"
    assert result.cache_max_age_seconds == 10800
    assert result.retry_after_seconds is None


@pytest.mark.asyncio
@respx.mock
async def test_success_with_no_cache_control_header_leaves_max_age_none(monkeypatch):
    _env(monkeypatch)
    respx.get(f"{MSF_BASE_URL}{_PATH}").mock(
        return_value=httpx.Response(200, json={"game": {"id": int(MSF_GAME_ID), "playedStatus": "LIVE"}})
    )

    result = await _default_fetch_boxscore(season=SEASON, msf_game_id=MSF_GAME_ID)

    assert result.status == "success"
    assert result.cache_max_age_seconds is None


@pytest.mark.asyncio
@respx.mock
async def test_429_captures_retry_after_without_local_retry(monkeypatch):
    """429 must give up immediately -- exactly one request, never the
    bounded local retry loop 5xx/network failures get."""
    _env(monkeypatch)
    route = respx.get(f"{MSF_BASE_URL}{_PATH}").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "120"})
    )

    result = await _default_fetch_boxscore(season=SEASON, msf_game_id=MSF_GAME_ID)

    assert result.status == "transient_error"
    assert result.http_status == 429
    assert result.retry_after_seconds == 120
    assert route.call_count == 1  # no local retry consumed on a 429


@pytest.mark.asyncio
@respx.mock
async def test_429_with_no_retry_after_header_leaves_it_none(monkeypatch):
    _env(monkeypatch)
    respx.get(f"{MSF_BASE_URL}{_PATH}").mock(return_value=httpx.Response(429))

    result = await _default_fetch_boxscore(season=SEASON, msf_game_id=MSF_GAME_ID)

    assert result.status == "transient_error"
    assert result.retry_after_seconds is None


@pytest.mark.asyncio
@respx.mock
async def test_5xx_still_uses_the_bounded_local_retry_loop(monkeypatch):
    """5xx/network failures remain on the separate, pre-existing bounded
    local-retry policy (rule 3) -- unaffected by the 429/Retry-After
    hardening. 3 total attempts (1 + MAX_LOCAL_TRANSIENT_RETRIES)."""
    _env(monkeypatch)
    route = respx.get(f"{MSF_BASE_URL}{_PATH}").mock(return_value=httpx.Response(503))

    result = await _default_fetch_boxscore(season=SEASON, msf_game_id=MSF_GAME_ID)

    assert result.status == "transient_error"
    assert result.retry_after_seconds is None
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_401_escalates_permanent_immediately_no_retry_after_parsing(monkeypatch):
    _env(monkeypatch)
    route = respx.get(f"{MSF_BASE_URL}{_PATH}").mock(return_value=httpx.Response(401))

    result = await _default_fetch_boxscore(season=SEASON, msf_game_id=MSF_GAME_ID)

    assert result.status == "permanent_error"
    assert result.retry_after_seconds is None
    assert route.call_count == 1
