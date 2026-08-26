"""Tests for POST /v1/internal/postgame-grading/run (Milestone 5.4) --
the HTTP boundary only (auth, request/response shape, wiring). The
grading/rollup/narrative logic itself is covered directly in
`tests/orchestration/test_postgame_grading.py` and
`tests/orchestration/test_postgame_review_narrative.py`."""
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


def test_postgame_grading_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    response = client.post("/v1/internal/postgame-grading/run", json={"game_ids": []})
    assert response.status_code == 401


@respx.mock
def test_postgame_grading_empty_game_ids_is_a_clean_no_op(monkeypatch):
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/model_routing_rules").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/model_registry").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(200, json=[]))

    response = client.post(
        "/v1/internal/postgame-grading/run",
        json={"game_ids": []},
        headers={"X-Internal-Token": "correct-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["games"] == []
    assert body["bankroll_preservation_products"] == []
    assert body["postgame_reviews_generated"] == 0
    assert body["postgame_reviews_failed"] == 0
    assert body["postgame_reviews_skipped"] == 0


@respx.mock
def test_postgame_grading_game_not_found_is_reported_not_a_500(monkeypatch):
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/model_routing_rules").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/model_registry").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(200, json=[]))

    response = client.post(
        "/v1/internal/postgame-grading/run",
        json={"game_ids": ["ghost-game"]},
        headers={"X-Internal-Token": "correct-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["games"][0]["status"] == "game_not_found"
