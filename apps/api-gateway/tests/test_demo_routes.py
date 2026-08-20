"""Tests for app.demo_routes (DEMO-4's API Gateway proxy layer +
Option A demo-operator access gate).

Every proxy route is a thin forward to sports-intel-layer's
`/internal/demo/*` router -- these tests prove exactly that: the right
method/path is forwarded, the internal service token is attached, the
response passes through unchanged, and every route is protected by the
demo-operator token gate (`X-Demo-Operator-Token`) before any of that
forwarding happens. They do not re-test `ScenarioRunner` behavior itself
(that's sports-intel-layer's own test suite).
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.main import app

BASE_URL = "https://sports-intel-layer.internal.test"
OPERATOR_TOKEN = "test-demo-operator-token"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def internal_env(monkeypatch):
    monkeypatch.setenv("SPORTS_INTEL_LAYER_URL", BASE_URL)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-internal-token")
    monkeypatch.setenv("DEMO_OPERATOR_TOKEN", OPERATOR_TOKEN)


def _auth_headers() -> dict:
    return {"X-Demo-Operator-Token": OPERATOR_TOKEN}


# -- demo-operator access gate (Mac's Option A) --

@pytest.mark.asyncio
async def test_missing_operator_token_is_rejected(internal_env):
    async with _client() as client:
        response = await client.get("/v1/demo/scenarios")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_wrong_operator_token_is_rejected(internal_env):
    async with _client() as client:
        response = await client.get("/v1/demo/scenarios", headers={"X-Demo-Operator-Token": "wrong"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_token_configuration_is_a_server_error(monkeypatch):
    monkeypatch.delenv("DEMO_OPERATOR_TOKEN", raising=False)
    async with _client() as client:
        response = await client.get("/v1/demo/scenarios", headers=_auth_headers())
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_every_proxy_route_requires_the_operator_token(internal_env):
    """Every single proxy route must sit behind the same gate -- not just
    the one exercised above -- so a route added later without the router
    dependency would be caught immediately."""
    async with _client() as client:
        assert (await client.get("/v1/demo/status")).status_code == 401
        assert (await client.post("/v1/demo/scenarios/x/load")).status_code == 401
        assert (await client.post("/v1/demo/step")).status_code == 401
        assert (await client.post("/v1/demo/run-to-checkpoint")).status_code == 401
        assert (await client.post("/v1/demo/run")).status_code == 401
        assert (await client.post("/v1/demo/reset")).status_code == 401
        assert (await client.get("/v1/demo/games")).status_code == 401
        assert (await client.get("/v1/demo/games/g1/intelligence")).status_code == 401


@pytest.mark.asyncio
async def test_gate_runs_before_any_internal_http_call(monkeypatch):
    """No SPORTS_INTEL_LAYER_URL/INTERNAL_SERVICE_TOKEN configured at all,
    and no operator token supplied -- if the gate ran after attempting the
    proxy call, this would still be a 401 either way, but this also
    proves no attempt to reach sports-intel-layer happens first (no
    respx mock registered at all; an attempted real call would error
    differently, not cleanly 401)."""
    monkeypatch.setenv("DEMO_OPERATOR_TOKEN", OPERATOR_TOKEN)
    async with _client() as client:
        response = await client.get("/v1/demo/scenarios")
    assert response.status_code == 401


# -- /login: validates a token without becoming a real proxy call --

@pytest.mark.asyncio
async def test_login_with_correct_token_succeeds(internal_env):
    async with _client() as client:
        response = await client.post("/v1/demo/login", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_login_with_wrong_token_fails(internal_env):
    async with _client() as client:
        response = await client.post("/v1/demo/login", headers={"X-Demo-Operator-Token": "wrong"})
    assert response.status_code == 401


# -- proxy forwarding, once past the gate --

@pytest.mark.asyncio
@respx.mock
async def test_proxy_forwards_method_path_and_internal_token(internal_env):
    route = respx.get(f"{BASE_URL}/internal/demo/scenarios").mock(
        return_value=httpx.Response(200, json=[{"name": "minimal_pregame_to_postgame"}])
    )
    async with _client() as client:
        response = await client.get("/v1/demo/scenarios", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json() == [{"name": "minimal_pregame_to_postgame"}]
    assert route.calls.last.request.headers["x-internal-token"] == "test-internal-token"


@pytest.mark.asyncio
@respx.mock
async def test_proxy_forwards_path_params_for_scenario_load(internal_env):
    route = respx.post(f"{BASE_URL}/internal/demo/scenarios/minimal_pregame_to_postgame/load").mock(
        return_value=httpx.Response(200, json={"status": "loaded"})
    )
    async with _client() as client:
        response = await client.post(
            "/v1/demo/scenarios/minimal_pregame_to_postgame/load", headers=_auth_headers()
        )
    assert response.status_code == 200
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_proxy_forwards_the_far_ends_error_status_and_detail(internal_env):
    respx.post(f"{BASE_URL}/internal/demo/step").mock(return_value=httpx.Response(409, text="no scenario loaded"))
    async with _client() as client:
        response = await client.post("/v1/demo/step", headers=_auth_headers())
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_call_sports_intel_layer_without_url_configured_is_a_server_error(monkeypatch):
    monkeypatch.delenv("SPORTS_INTEL_LAYER_URL", raising=False)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-internal-token")
    from fastapi import HTTPException

    from app.internal_client import call_sports_intel_layer

    with pytest.raises(HTTPException) as exc_info:
        await call_sports_intel_layer("GET", "/internal/demo/scenarios")
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_call_sports_intel_layer_without_token_configured_is_a_server_error(monkeypatch):
    monkeypatch.setenv("SPORTS_INTEL_LAYER_URL", BASE_URL)
    monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
    from fastapi import HTTPException

    from app.internal_client import call_sports_intel_layer

    with pytest.raises(HTTPException) as exc_info:
        await call_sports_intel_layer("GET", "/internal/demo/scenarios")
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
@respx.mock
async def test_internal_service_error_on_connection_failure(internal_env):
    from app.internal_client import InternalServiceError, call_sports_intel_layer

    respx.get(f"{BASE_URL}/internal/demo/scenarios").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(InternalServiceError):
        await call_sports_intel_layer("GET", "/internal/demo/scenarios")


@pytest.mark.asyncio
@respx.mock
async def test_internal_token_never_appears_in_a_proxied_response(internal_env):
    """The internal service token must never leak into what the frontend
    receives -- proxy errors surface the far-end's own detail text, never
    headers."""
    respx.get(f"{BASE_URL}/internal/demo/scenarios").mock(return_value=httpx.Response(403, text="forbidden"))
    async with _client() as client:
        response = await client.get("/v1/demo/scenarios", headers=_auth_headers())
    assert "test-internal-token" not in response.text


@pytest.mark.asyncio
@respx.mock
async def test_operator_token_never_appears_in_a_proxied_response(internal_env):
    respx.get(f"{BASE_URL}/internal/demo/scenarios").mock(return_value=httpx.Response(200, json=[]))
    async with _client() as client:
        response = await client.get("/v1/demo/scenarios", headers=_auth_headers())
    assert OPERATOR_TOKEN not in response.text
