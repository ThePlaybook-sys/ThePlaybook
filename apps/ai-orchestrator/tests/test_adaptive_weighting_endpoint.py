"""Tests for POST /v1/internal/adaptive-weighting/run (Milestone 5.5) --
the HTTP boundary only (auth, request/response shape, window-guardrail
wiring). The evaluation logic itself is covered directly in
`tests/orchestration/test_adaptive_weighting.py`."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"


def _set_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def test_adaptive_weighting_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    response = client.post("/v1/internal/adaptive-weighting/run", json={})
    assert response.status_code == 401


@respx.mock
def test_adaptive_weighting_default_window_with_zero_evidence(monkeypatch):
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "agent-1", "name": "sharp_money_agent", "category": "market", "current_weight": "1.0"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(201, json=[{"id": "prop-1"}]))

    response = client.post(
        "/v1/internal/adaptive-weighting/run", json={}, headers={"X-Internal-Token": "correct-token"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agents"][0]["proposal_status"] == "rejected_insufficient_sample"
    assert body["agents"][0]["sample_size"] == 0


@respx.mock
def test_adaptive_weighting_window_too_short_returns_422(monkeypatch):
    _set_env(monkeypatch)
    response = client.post(
        "/v1/internal/adaptive-weighting/run",
        json={"evaluation_window_days": 30},
        headers={"X-Internal-Token": "correct-token"},
    )
    assert response.status_code == 422
