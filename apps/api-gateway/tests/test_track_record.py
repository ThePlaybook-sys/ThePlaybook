"""Tests for GET /v1/track-record (Phase 6 Milestone 2). Covers the
product-level-not-leg-level denominator rule (HQ Final Decision 2), the
zero-sample honest contract, MIXED_SETTLED handled as its own bucket
(never folded into win/loss), correction-chain de-duplication, and the
absence of every Category C metric."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"
AUTH_URL = f"{SUPABASE_URL}/auth/v1/user"
USER_ID = "22222222-2222-2222-2222-222222222222"

_CATEGORY_C_KEYS = {
    "units",
    "roi",
    "ev",
    "expectedValue",
    "clv",
    "calibration",
    "projectedPerformance",
    "verifiedPerformance",
}


def _mock_authenticated_user() -> None:
    respx.get(AUTH_URL).mock(return_value=httpx.Response(200, json={"id": USER_ID}))
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(
        return_value=httpx.Response(200, json=[{"id": USER_ID, "jurisdiction_state": "NJ"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(200, json=[]))


def _grade_event_row(product_id: str, outcome: str, computed_at: str, *, rtype: str = "single", tier: str = "free") -> dict:
    return {
        "recommendation_product_id": product_id,
        "outcome": outcome,
        "computed_at": computed_at,
        "recommendation_products": {
            "recommendation_type": rtype,
            "min_required_tier": tier,
            "deleted_at": None,
        },
    }


@respx.mock
def test_track_record_requires_authentication():
    response = client.get("/v1/track-record")
    assert response.status_code == 401


@respx.mock
def test_zero_sample_honest_contract():
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(200, json=[])
    )

    response = client.get("/v1/track-record", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["sampleSize"] == 0
    assert body["sampleStatus"] == "zero"
    assert body["record"] == {"win": 0, "loss": 0, "push": 0, "voidNoAction": 0, "mixedSettled": 0}
    assert not (set(body.keys()) & _CATEGORY_C_KEYS)
    assert not (set(body["record"].keys()) & _CATEGORY_C_KEYS)


@respx.mock
def test_multiple_singles_counts_once_not_per_leg():
    """HQ Final Decision 2 -- the product-level MIXED_SETTLED outcome
    is one observation, regardless of how many legs the product has."""
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(
            200,
            json=[
                _grade_event_row("prod-multi", "MIXED_SETTLED", "2026-08-28T12:00:00Z", rtype="multiple_singles"),
            ],
        )
    )

    response = client.get("/v1/track-record", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["sampleSize"] == 1
    assert body["record"]["mixedSettled"] == 1
    # Never folded into win or loss -- it is neither.
    assert body["record"]["win"] == 0
    assert body["record"]["loss"] == 0
    assert body["byRecommendationType"]["multiple_singles"]["mixedSettled"] == 1


@respx.mock
def test_not_applicable_and_pending_excluded_from_sample():
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(
            200,
            json=[
                _grade_event_row("prod-nobet", "NOT_APPLICABLE", "2026-08-28T12:00:00Z", rtype="no_bet"),
                _grade_event_row("prod-pending", "PENDING_MISSING_DATA", "2026-08-28T12:00:00Z"),
                _grade_event_row("prod-win", "WIN", "2026-08-28T12:00:00Z"),
            ],
        )
    )

    response = client.get("/v1/track-record", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["sampleSize"] == 1
    assert body["record"]["win"] == 1


@respx.mock
def test_correction_chain_uses_latest_outcome_only():
    """Same product, corrected once -- must count as ONE observation
    using the most recent (corrected) outcome, never both."""
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(
            200,
            # order=computed_at.desc -- the corrected row comes first.
            json=[
                _grade_event_row("prod-corrected", "LOSS", "2026-08-29T00:00:00Z"),
                _grade_event_row("prod-corrected", "WIN", "2026-08-28T12:00:00Z"),
            ],
        )
    )

    response = client.get("/v1/track-record", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["sampleSize"] == 1
    assert body["record"]["loss"] == 1
    assert body["record"]["win"] == 0


@respx.mock
def test_tier_gated_product_excluded_from_free_users_aggregate():
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(
            200,
            json=[_grade_event_row("prod-elite", "WIN", "2026-08-28T12:00:00Z", tier="elite")],
        )
    )

    response = client.get("/v1/track-record", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    assert response.json()["sampleSize"] == 0


@respx.mock
def test_deleted_product_excluded():
    _mock_authenticated_user()
    row = _grade_event_row("prod-deleted", "WIN", "2026-08-28T12:00:00Z")
    row["recommendation_products"]["deleted_at"] = "2026-08-28T13:00:00Z"
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(200, json=[row])
    )

    response = client.get("/v1/track-record", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    assert response.json()["sampleSize"] == 0
