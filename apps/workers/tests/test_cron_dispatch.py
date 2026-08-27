"""Tests for app.cron_dispatch (Pre-Phase-6 Operational Readiness Gate,
Decision 3) -- the finite Railway Cron Job entry point. Only `dispatch`
(the pure-enough async call) is tested directly; `main`'s `sys.exit` is
deliberately not exercised here (an OS-process-boundary concern, not
this module's own dispatch logic)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.cron_dispatch import CronDispatchError, dispatch

BASE_URL = "https://worker-scheduled.test"


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_recommendation_worker_posts_to_correct_path_with_token():
    route = respx.post(f"{BASE_URL}/v1/internal/recommendation-worker/run").mock(
        return_value=httpx.Response(200, json={"status": "no_eligible_run", "run_id": None, "games": []})
    )
    async with httpx.AsyncClient() as client:
        result = await dispatch(target="recommendation-worker", base_url=BASE_URL, internal_token="secret", client=client)
    assert result["status"] == "no_eligible_run"
    assert route.calls.last.request.headers["X-Internal-Token"] == "secret"


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_postgame_grading_posts_to_correct_path():
    respx.post(f"{BASE_URL}/v1/internal/postgame-grading/run").mock(
        return_value=httpx.Response(200, json={"status": "completed", "game_ids": []})
    )
    async with httpx.AsyncClient() as client:
        result = await dispatch(target="postgame-grading", base_url=BASE_URL, internal_token="secret", client=client)
    assert result["status"] == "completed"


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_adaptive_weighting_posts_to_correct_path():
    respx.post(f"{BASE_URL}/v1/internal/adaptive-weighting/run").mock(
        return_value=httpx.Response(200, json={"status": "completed", "response": {}})
    )
    async with httpx.AsyncClient() as client:
        result = await dispatch(target="adaptive-weighting", base_url=BASE_URL, internal_token="secret", client=client)
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_dispatch_rejects_unknown_target():
    async with httpx.AsyncClient() as client:
        with pytest.raises(CronDispatchError):
            await dispatch(target="not-a-real-target", base_url=BASE_URL, internal_token="secret", client=client)


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_raises_on_non_200():
    respx.post(f"{BASE_URL}/v1/internal/recommendation-worker/run").mock(return_value=httpx.Response(500, text="boom"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(CronDispatchError):
            await dispatch(target="recommendation-worker", base_url=BASE_URL, internal_token="secret", client=client)


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_raises_on_transport_failure():
    respx.post(f"{BASE_URL}/v1/internal/recommendation-worker/run").mock(side_effect=httpx.ConnectError("refused"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(CronDispatchError):
            await dispatch(target="recommendation-worker", base_url=BASE_URL, internal_token="secret", client=client)
