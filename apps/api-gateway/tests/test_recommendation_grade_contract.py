"""Milestone 2.1 -- additive product grade contract (HQ-authorized
correction to Milestone 2's read routes, Volume 5 v5.0.2 §11). Exercises
`/today`, `/recommendations` (list), and `/recommendations/{display_id}`
for every real outcome `recommendation_product_grade_events` can hold,
the append-only correction chain's current-outcome resolution, and that
`recommendation_products.status` is never mutated into a `'graded'`
value -- grade state is a separate, additive dimension."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"
AUTH_URL = f"{SUPABASE_URL}/auth/v1/user"
USER_ID = "22222222-2222-2222-2222-222222222222"


def _mock_authenticated_user(*, tier: str | None = None) -> None:
    respx.get(AUTH_URL).mock(return_value=httpx.Response(200, json={"id": USER_ID}))
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(
        return_value=httpx.Response(200, json=[{"id": USER_ID, "jurisdiction_state": "NJ"}])
    )
    subscription_rows = [{"tier": tier}] if tier else []
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(
        return_value=httpx.Response(200, json=subscription_rows)
    )


def _product(**overrides) -> dict:
    base = {
        "id": "prod-grade-1",
        "display_id": "2026-00100",
        "recommendation_type": "single",
        "scope": "game",
        "game_id": None,
        "status": "active",
        "min_required_tier": "free",
        "withdrawn_at": None,
        "withdrawal_reason": None,
        "created_at": "2026-08-28T06:00:00Z",
    }
    base.update(overrides)
    return base


def _grade_event(*, outcome: str, computed_at: str, is_correction: bool = False) -> dict:
    return {
        "recommendation_product_id": "prod-grade-1",
        "outcome": outcome,
        "is_correction": is_correction,
        "computed_at": computed_at,
    }


def _mock_detail_reads(product: dict, *, grade_events: list[dict] | None = None) -> None:
    """Mocks every table the detail route reads for a leg-less product --
    game_id is deliberately left unset on `_product()` so `_read_game`
    is never called (Layer 2-4 leg serialization is exercised separately
    by test_recommendation_detail.py; this file's only concern is the
    additive `grade` field)."""
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[product])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(200, json=grade_events or [])
    )


@respx.mock
def test_grade_is_null_for_ungraded_product():
    _mock_authenticated_user()
    _mock_detail_reads(_product(), grade_events=[])

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    assert response.json()["grade"] is None


@respx.mock
def test_grade_win():
    _mock_authenticated_user()
    _mock_detail_reads(
        _product(),
        grade_events=[_grade_event(outcome="WIN", computed_at="2026-08-29T02:00:00Z")],
    )

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    assert response.json()["grade"] == {
        "outcome": "WIN",
        "gradedAt": "2026-08-29T02:00:00Z",
        "isCorrection": False,
        "correctedAt": None,
    }


@respx.mock
def test_grade_loss():
    _mock_authenticated_user()
    _mock_detail_reads(
        _product(),
        grade_events=[_grade_event(outcome="LOSS", computed_at="2026-08-29T02:00:00Z")],
    )

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    assert response.json()["grade"]["outcome"] == "LOSS"


@respx.mock
def test_grade_push():
    _mock_authenticated_user()
    _mock_detail_reads(
        _product(),
        grade_events=[_grade_event(outcome="PUSH", computed_at="2026-08-29T02:00:00Z")],
    )

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    assert response.json()["grade"]["outcome"] == "PUSH"


@respx.mock
def test_grade_void_no_action():
    _mock_authenticated_user()
    _mock_detail_reads(
        _product(),
        grade_events=[_grade_event(outcome="VOID_NO_ACTION", computed_at="2026-08-29T02:00:00Z")],
    )

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    assert response.json()["grade"]["outcome"] == "VOID_NO_ACTION"


@respx.mock
def test_grade_mixed_settled_is_the_authoritative_product_level_value():
    """MIXED_SETTLED is already the real, wired rollup outcome
    (`app.features.grading.rollup_product_outcome`, ai-orchestrator) --
    this route must pass it through verbatim, never derive it from legs
    itself (HQ's explicit M2.1 instruction)."""
    _mock_authenticated_user()
    _mock_detail_reads(
        _product(recommendation_type="multiple_singles"),
        grade_events=[_grade_event(outcome="MIXED_SETTLED", computed_at="2026-08-29T02:00:00Z")],
    )

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    assert response.json()["grade"]["outcome"] == "MIXED_SETTLED"


@respx.mock
def test_grade_not_applicable_for_no_bet_never_becomes_win_loss_push():
    _mock_authenticated_user()
    _mock_detail_reads(
        _product(recommendation_type="no_bet"),
        grade_events=[_grade_event(outcome="NOT_APPLICABLE", computed_at="2026-08-28T20:00:00Z")],
    )

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    grade = response.json()["grade"]
    assert grade["outcome"] == "NOT_APPLICABLE"
    assert grade["outcome"] not in ("WIN", "LOSS", "PUSH")


@respx.mock
def test_grade_correction_reflects_current_outcome_and_preserves_original_graded_at():
    """The append-only correction chain: an original WIN row followed by
    a later correction row (LOSS). The API must expose the CURRENT
    (corrected) outcome as `grade.outcome`, the ORIGINAL grading time as
    `gradedAt`, and the correction's own time as `correctedAt` -- so the
    frontend can render "result corrected [date]" without reconstructing
    the chain itself."""
    _mock_authenticated_user()
    _mock_detail_reads(
        _product(),
        grade_events=[
            _grade_event(outcome="WIN", computed_at="2026-08-29T02:00:00Z", is_correction=False),
            _grade_event(outcome="LOSS", computed_at="2026-08-30T09:00:00Z", is_correction=True),
        ],
    )

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    assert response.json()["grade"] == {
        "outcome": "LOSS",
        "gradedAt": "2026-08-29T02:00:00Z",
        "isCorrection": True,
        "correctedAt": "2026-08-30T09:00:00Z",
    }


@respx.mock
def test_lifecycle_status_is_never_mutated_into_graded():
    _mock_authenticated_user()
    _mock_detail_reads(
        _product(status="active"),
        grade_events=[_grade_event(outcome="WIN", computed_at="2026-08-29T02:00:00Z")],
    )

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    body = response.json()
    assert body["status"] == "active"
    assert body["status"] != "graded"
    assert body["grade"]["outcome"] == "WIN"


@respx.mock
def test_withdrawn_status_and_grade_are_independent_dimensions():
    _mock_authenticated_user()
    _mock_detail_reads(
        _product(status="withdrawn", withdrawn_at="2026-08-28T10:00:00Z", withdrawal_reason="line moved"),
        grade_events=[],
    )

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    body = response.json()
    assert body["status"] == "withdrawn"
    assert body["withdrawnAt"] == "2026-08-28T10:00:00Z"
    assert body["grade"] is None


@respx.mock
def test_tier_gated_product_still_404s_grade_not_leaked():
    """Unauthorized/tier-gated behavior is unchanged by M2.1 -- the
    authorization check in `_authorize_product_for_display_id` still
    short-circuits to 404 before any grade read happens, exactly as it
    did before this milestone (mirrors
    test_recommendation_detail.test_detail_hides_tier_gated_product)."""
    _mock_authenticated_user(tier=None)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[_product(min_required_tier="elite")])
    )

    response = client.get("/v1/recommendations/2026-00100", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 404


@respx.mock
def test_list_route_includes_grade_field_and_stays_backward_compatible():
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[_product()])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(200, json=[_grade_event(outcome="PUSH", computed_at="2026-08-29T02:00:00Z")])
    )

    response = client.get("/v1/recommendations", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    card = response.json()[0]
    assert card["grade"]["outcome"] == "PUSH"
    for field in (
        "displayId", "recommendationType", "scope", "status", "minRequiredTier",
        "withdrawnAt", "withdrawalReason", "decidedAt", "game", "oneLineSummary", "legs",
    ):
        assert field in card


@respx.mock
def test_today_route_includes_grade_field():
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200, json=[_product(scope="slate", recommendation_type="bankroll_preservation")]
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(
            200, json=[_grade_event(outcome="NOT_APPLICABLE", computed_at="2026-08-29T02:00:00Z")]
        )
    )

    response = client.get("/v1/recommendations/today", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    assert response.json()[0]["grade"]["outcome"] == "NOT_APPLICABLE"
