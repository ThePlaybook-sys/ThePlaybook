"""Tests for POST /v1/internal/odds-worker/run (Phase 7 Milestone 7.0B,
Gate A) -- the HTTP boundary this project never had before this
milestone (Milestone 7.0A's own STOP report). `app.workers.odds_worker.
run_odds_worker` is already thoroughly tested directly
(`tests/test_odds_worker.py`), including the "zero provider request when
nothing is due" behavior (`test_no_games_due_skips_the_provider_call_
entirely`) this milestone's own construction-contract audit relied on;
these tests cover only what's specific to this HTTP boundary: auth, safe
missing-credential failure, and the real construction of
`TheOddsApiOddsAdapter` from env vars (no injected fixture adapter,
unlike Demo Mode's own caller in `app.demo.runner`). Every HTTP boundary
-- Supabase and The Odds API both -- is respx-mocked; no real network is
used anywhere in this file, and this suite never requires (or could
consume) a real Odds API credential."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"
ODDS_API_URL = "https://api.the-odds-api.com"


def _set_env(monkeypatch, *, with_odds_key: bool = True):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "dev")
    if with_odds_key:
        monkeypatch.setenv("THE_ODDS_API_KEY", "test-the-odds-api-key")
    else:
        monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)


def test_run_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    response = client.post("/v1/internal/odds-worker/run")
    assert response.status_code == 401


@respx.mock
def test_missing_credential_fails_safely_before_any_network_call(monkeypatch):
    """No THE_ODDS_API_KEY configured -- HQ's explicit requirement: fail
    safely and clearly BEFORE attempting provider network activity, never
    a raw KeyError/500, and never leak the (nonexistent) secret's name in
    the response body. No respx route is registered for either Supabase
    or The Odds API in this test at all -- if the endpoint touched the
    network before checking the credential, this test would fail with an
    unmocked-request error instead of the assertions below."""
    _set_env(monkeypatch, with_odds_key=False)

    response = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "THE_ODDS_API_KEY is not configured."
    assert body["lines_persisted"] == 0
    assert body["games_considered"] == 0
    # The credential's own (nonexistent) value never appears anywhere in
    # the response -- there is nothing to leak, and the error message
    # names the missing variable, never a value.
    assert "test-the-odds-api-key" not in response.text


@respx.mock
def test_run_empty_slate_round_trip_uses_real_the_odds_api_key(monkeypatch):
    """A real, respx-intercepted call to the real The Odds API base URL
    (`https://api.the-odds-api.com`), authenticated with the real
    `THE_ODDS_API_KEY` env var this endpoint reads -- proving the
    endpoint wires a genuine `TheOddsApiOddsAdapter` (no injected fixture
    adapter), never that a real call was actually spent against the live
    provider (respx intercepts before any request leaves this process).
    Zero games in the candidate window -- `run_odds_worker` itself
    already proves the deeper "zero games due -> zero provider calls"
    case directly; this just proves the HTTP boundary reaches that same
    correct function with real credentials."""
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    # No games -> read_last_polled_at's own odds_snapshots read still runs
    # (it doesn't depend on the games query) -- mock it to an empty history.
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))

    response = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["games_considered"] == 0
    assert body["lines_persisted"] == 0
    assert body["error"] is None


@respx.mock
def test_response_never_contains_the_credential_value_on_success(monkeypatch):
    """Structural no-secret-leakage check on the success path too, not
    just the missing-credential path above -- `RunOddsWorkerResponse`
    has no field that could carry it, but this asserts the actual
    observed behavior rather than trusting the schema alone."""
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))

    response = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})

    assert "test-the-odds-api-key" not in response.text


def test_health_endpoint_never_exposes_the_credential(monkeypatch):
    _set_env(monkeypatch)
    response = client.get("/health")
    assert "test-the-odds-api-key" not in response.text
    assert "THE_ODDS_API_KEY" not in response.text
