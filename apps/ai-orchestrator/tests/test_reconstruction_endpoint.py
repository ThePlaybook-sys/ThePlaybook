"""Tests for GET /v1/internal/reconstruction/{id} (Phase 6 Milestone 2)
-- the HTTP boundary only (auth, 404-on-missing, serialization shape).
The reconstruction logic itself is covered directly in
`tests/orchestration/test_reconstruction.py`; this endpoint is a thin
`dataclasses.asdict` wrapper around it, per that module's own
docstring."""
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


def _mock_empty_downstream_evidence() -> None:
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_postgame_reviews").mock(return_value=httpx.Response(200, json=[]))


def test_reconstruction_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    response = client.get("/v1/internal/reconstruction/prod-1")
    assert response.status_code == 401


@respx.mock
def test_reconstruction_returns_404_when_product_missing(monkeypatch):
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(200, json=[]))

    response = client.get(
        "/v1/internal/reconstruction/nonexistent", headers={"X-Internal-Token": "correct-token"}
    )

    assert response.status_code == 404


@respx.mock
def test_reconstruction_returns_serialized_shape_for_no_bet_product(monkeypatch):
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-nobet", "recommendation_type": "no_bet"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": "expl-1"}],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(200, json=[{"id": "expl-1", "why_this_shape": "no candidate qualified"}])
    )
    _mock_empty_downstream_evidence()

    response = client.get(
        "/v1/internal/reconstruction/prod-nobet", headers={"X-Internal-Token": "correct-token"}
    )

    assert response.status_code == 200
    body = response.json()
    # Confirms this is a faithful serialization of ReconstructedProduct,
    # not a re-derived/narrowed shape -- every top-level field the
    # dataclass defines must survive dataclasses.asdict() untouched.
    assert body["strategy_version"] == "v1"
    assert body["product_explanation"]["why_this_shape"] == "no candidate qualified"
    assert body["legs"] == []
    assert body["source_products"] == []
    assert body["lifecycle_events"] == []
    assert body["product_grade_history"] == []
    assert body["current_product_grade"] is None
    assert body["postgame_reviews"] == []
    assert body["user_selection"] is None
