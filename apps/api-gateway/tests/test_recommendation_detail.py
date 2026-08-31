"""Tests for GET /v1/recommendations/{display_id} (Phase 6 Milestone 2)
-- Layers 1-4 detail. Covers graded and corrected-result history
serialization, which /today and the feed route don't exercise."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"
AUTH_URL = f"{SUPABASE_URL}/auth/v1/user"
USER_ID = "22222222-2222-2222-2222-222222222222"


def _mock_authenticated_user() -> None:
    respx.get(AUTH_URL).mock(return_value=httpx.Response(200, json={"id": USER_ID}))
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(
        return_value=httpx.Response(200, json=[{"id": USER_ID, "jurisdiction_state": "NJ"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(200, json=[]))


_PRODUCT = {
    "id": "prod-1",
    "display_id": "2026-00010",
    "recommendation_type": "single",
    "scope": "game",
    "game_id": "game-1",
    "status": "active",
    "min_required_tier": "free",
    "withdrawn_at": None,
    "withdrawal_reason": None,
    "created_at": "2026-08-28T06:00:00Z",
}

_LEG = {
    "id": "leg-1",
    "recommendation_product_id": "prod-1",
    "recommendation_id": "rec-1",
    "consensus_snapshot_id": "consensus-1",
    "candidate_key": "KC-ML",
    "market_type": "moneyline",
    "selection": "Chiefs",
    "sportsbook": "book",
    "american_odds": -135,
    "point": None,
    "decimal_odds": 1.74,
    "ev_per_dollar": 0.063,
    "final_aggregate_confidence": 0.89,
    "leg_order": 1,
}


def _mock_common(*, agent_outputs: list[dict] | None = None) -> None:
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[_PRODUCT])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "game-1", "home_team": "Chiefs", "away_team": "Bills", "scheduled_start": "2026-08-28T18:00:00Z", "status": "scheduled"}],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"recommendation_product_id": "prod-1", "activated_at": "2026-08-28T06:00:30Z"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "recommendation_product_id": "prod-1",
                    "why_this_shape": "highest-ranked qualifying candidate",
                    "why_not_other_shapes": "no other candidate cleared the confidence floor",
                    "rejected_alternatives": [],
                    "data_limitations": "Sharp money and public betting data are not yet available.",
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=[_LEG]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "recommendation_leg_id": "leg-1",
                    "why_selected": "top-ranked qualifying candidate",
                    "strongest_evidence": "Injury Intelligence, Weather",
                    "contributing_agents": [{"name": "injury_intelligence_agent", "weight": 0.4}],
                    "biggest_risks": "elevated outcome variance",
                    "rejected_alternatives": [],
                    "would_change_mind_if": "a key starter is ruled out pregame",
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(200, json=agent_outputs or [])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "agent-1", "name": "injury_intelligence_agent"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "aggregate_confidence": 0.87,
                    "agreement_variance": 0.03,
                    "final_aggregate_confidence": 0.89,
                    "below_confidence_floor": False,
                }
            ],
        )
    )


@respx.mock
def test_detail_requires_authentication():
    response = client.get("/v1/recommendations/2026-00010")
    assert response.status_code == 401


@respx.mock
def test_detail_returns_404_for_unknown_display_id():
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(200, json=[]))

    response = client.get("/v1/recommendations/nonexistent", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 404


@respx.mock
def test_detail_serializes_all_four_layers():
    _mock_authenticated_user()
    _mock_common(
        agent_outputs=[
            {
                "agent_id": "agent-1",
                "candidate_key": "KC-ML",
                "agent_confidence": 0.9,
                "weight_applied": 1.05,
                "raw_output": {"directional_lean": "home"},
                "model_name": "claude-sonnet-5",
                "provider": "anthropic",
                "used_fallback": False,
                "prompt_name": "injury_intelligence_agent",
                "prompt_version": 1,
            }
        ]
    )

    response = client.get("/v1/recommendations/2026-00010", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    body = response.json()
    # Layer 1
    assert body["displayId"] == "2026-00010"
    assert body["grade"] is None
    # Layer 2
    leg = body["legs"][0]
    assert leg["strongestEvidence"] == "Injury Intelligence, Weather"
    assert leg["contributingAgents"] == [{"name": "injury_intelligence_agent", "weight": 0.4}]
    # Layer 3
    assert body["whyNotOtherShapes"] == "no other candidate cleared the confidence floor"
    assert leg["wouldChangeMindIf"] == "a key starter is ruled out pregame"
    # Layer 4 -- provenance and consensus, never shown at Layers 1-3
    assert leg["agentContributions"][0]["agentName"] == "injury_intelligence_agent"
    assert leg["agentContributions"][0]["directionalLean"] == "home"
    assert leg["agentContributions"][0]["modelName"] == "claude-sonnet-5"
    assert leg["consensus"]["agreementVariance"] == 0.03


@respx.mock
def test_detail_hides_tier_gated_product():
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{**_PRODUCT, "min_required_tier": "elite"}])
    )

    response = client.get("/v1/recommendations/2026-00010", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 404
