"""Tests for POST /v1/internal/recommendation-worker/run (Milestone 4.9)
-- the trigger surface something external to this application (a
Railway Cron Job or external scheduler) calls on a schedule."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"
AI_ORCHESTRATOR_URL = "https://ai-orchestrator.test"


def _set_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("RAILWAY_SERVICE_AI_ORCHESTRATOR_URL", AI_ORCHESTRATOR_URL)


def test_run_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    response = client.post("/v1/internal/recommendation-worker/run")
    assert response.status_code == 401


@respx.mock
def test_run_returns_no_eligible_run_when_master_refresh_never_completed(monkeypatch):
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[]))

    response = client.post("/v1/internal/recommendation-worker/run", headers={"X-Internal-Token": "correct-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_eligible_run"
    assert body["run_id"] is None
    assert body["games"] == []


@respx.mock
def test_run_dispatches_eligible_games(monkeypatch):
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[{"id": "run-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}]))
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r1", "candidates": []})
    )

    response = client.post("/v1/internal/recommendation-worker/run", headers={"X-Internal-Token": "correct-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["run_id"] == "run-1"
    assert body["games"] == [{"game_id": "g1", "correlation_id": "run-1:g1", "status": "dispatched", "error": None}]
