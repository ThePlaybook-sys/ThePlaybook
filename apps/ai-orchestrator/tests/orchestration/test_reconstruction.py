"""Tests for app.orchestration.reconstruction (Milestone 5.3) -- the
internal Time Machine reconstruction function, plus the roadmap's own
named reproducibility test: mutate live state after activation, confirm
reconstruction is unaffected."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.orchestration.reconstruction import ReconstructionError, reconstruct_recommendation_product

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _mock_empty_downstream_evidence() -> None:
    """Pre-Phase-6 Operational Readiness Gate (Section 9) -- every
    reconstruction now unconditionally reads lifecycle events, product
    grade history, and postgame reviews. Tests that don't care about
    that evidence mock all three as empty so the pre-existing assertions
    keep working unmodified."""
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_postgame_reviews").mock(return_value=httpx.Response(200, json=[]))


def _mock_empty_leg_evidence() -> None:
    """Same idea, for the per-leg reads (grade history -> weighting
    evidence)."""
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=[]))


@pytest.mark.asyncio
@respx.mock
async def test_raises_when_product_does_not_exist():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ReconstructionError):
            await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="nonexistent")


@pytest.mark.asyncio
@respx.mock
async def test_raises_when_activation_snapshot_missing():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-1", "recommendation_type": "single"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ReconstructionError):
            await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-1")


@pytest.mark.asyncio
@respx.mock
async def test_no_bet_reconstructs_with_no_legs():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-nobet", "recommendation_type": "no_bet"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": "expl-1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(200, json=[{"id": "expl-1", "why_this_shape": "no candidate qualified"}])
    )
    _mock_empty_downstream_evidence()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-nobet")
    assert result.legs == []
    assert result.source_products == []
    assert result.product_explanation["why_this_shape"] == "no candidate qualified"
    assert result.strategy_version == "v1"
    assert result.lifecycle_events == []
    assert result.product_grade_history == []
    assert result.current_product_grade is None
    assert result.postgame_reviews == []


@pytest.mark.asyncio
@respx.mock
async def test_bankroll_preservation_reconstructs_its_source_no_bet_products():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-bp", "recommendation_type": "bankroll_preservation"}])
    )

    def _snapshot_responder(request: httpx.Request) -> httpx.Response:
        product_id = request.url.params.get("recommendation_product_id", "").removeprefix("eq.")
        snapshots = {
            "prod-bp": {"id": "snap-bp", "strategy_version": "v1", "recommendation_product_explanation_id": None},
            "prod-g1": {"id": "snap-g1", "strategy_version": "v1", "recommendation_product_explanation_id": "expl-g1"},
        }
        row = snapshots.get(product_id)
        return httpx.Response(200, json=[row] if row else [])

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(side_effect=_snapshot_responder)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_source_products").mock(
        return_value=httpx.Response(200, json=[{"source_recommendation_product_id": "prod-g1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(200, json=[{"id": "expl-g1", "why_this_shape": "g1 had no qualifying candidate"}])
    )
    _mock_empty_downstream_evidence()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-bp")

    assert len(result.source_products) == 1
    assert result.source_products[0].recommendation_product_id == "prod-g1"
    assert result.source_products[0].explanation["why_this_shape"] == "g1 had no qualifying candidate"


@pytest.mark.asyncio
@respx.mock
async def test_multiple_singles_reconstructs_legs_in_frozen_order():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-ms", "recommendation_type": "multiple_singles"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-ms", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(
            200, json=[{"recommendation_leg_id": "leg-strong", "leg_order": 1}, {"recommendation_leg_id": "leg-weak", "leg_order": 2}]
        )
    )

    def _leg_responder(request: httpx.Request) -> httpx.Response:
        leg_id = request.url.params.get("id", "").removeprefix("eq.")
        rows = {
            "leg-strong": {"id": "leg-strong", "candidate_key": "strong", "ev_per_dollar": 0.09},
            "leg-weak": {"id": "leg-weak", "candidate_key": "weak", "ev_per_dollar": 0.02},
        }
        return httpx.Response(200, json=[rows[leg_id]])

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(side_effect=_leg_responder)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(return_value=httpx.Response(200, json=[]))
    _mock_empty_downstream_evidence()
    _mock_empty_leg_evidence()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-ms")

    assert [(leg.leg_order, leg.leg["candidate_key"]) for leg in result.legs] == [(1, "strong"), (2, "weak")]
    assert all(leg.explanation is None for leg in result.legs)
    assert all(leg.grade_history == [] and leg.current_grade is None and leg.weighting_evidence == [] for leg in result.legs)


@pytest.mark.asyncio
@respx.mock
async def test_single_product_with_user_id_attaches_that_users_latest_selection():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-single", "recommendation_type": "single"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-single", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(200, json=[{"recommendation_leg_id": "leg-1", "leg_order": 1}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": "only"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(return_value=httpx.Response(200, json=[]))
    _mock_empty_downstream_evidence()
    _mock_empty_leg_evidence()
    selection_route = respx.get(f"{SUPABASE_URL}/rest/v1/user_recommendation_selections").mock(
        return_value=httpx.Response(200, json=[{"id": "sel-1", "stake": 42.0}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(
            client, _headers(), recommendation_product_id="prod-single", user_id="user-1"
        )

    assert result.user_selection["stake"] == 42.0
    assert selection_route.calls.last.request.url.params["recommendation_leg_id"] == "eq.leg-1"


@pytest.mark.asyncio
@respx.mock
async def test_no_user_id_leaves_user_selection_none():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-nobet", "recommendation_type": "no_bet"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    _mock_empty_downstream_evidence()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-nobet")
    assert result.user_selection is None


# --- Pre-Phase-6 Operational Readiness Gate (Section 9/10): downstream
# evidence composition -- lifecycle, grade history/corrections, Postgame
# Review, Adaptive Weighting evidence, prompt/model provenance. ---


@pytest.mark.asyncio
@respx.mock
async def test_reconstruction_returns_lifecycle_history_when_present():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-1", "recommendation_type": "no_bet"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"event_type": "ACTIVATED", "event_timestamp": "2026-08-01T00:00:00Z", "reason": None},
                {"event_type": "WITHDRAWN", "event_timestamp": "2026-08-02T00:00:00Z", "reason": "line moved"},
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_postgame_reviews").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-1")

    assert [e["event_type"] for e in result.lifecycle_events] == ["ACTIVATED", "WITHDRAWN"]


@pytest.mark.asyncio
@respx.mock
async def test_reconstruction_identifies_current_authoritative_grade_and_preserves_correction_history():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-1", "recommendation_type": "single"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(200, json=[{"recommendation_leg_id": "leg-1", "leg_order": 1}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": "only"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(return_value=httpx.Response(200, json=[]))
    _mock_empty_downstream_evidence()

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "grade-1", "grading_version": "v1", "outcome": "LOSS", "is_correction": False, "corrects_grade_event_id": None, "created_at": "2026-08-01T00:00:00Z"},
                {"id": "grade-2", "grading_version": "v1", "outcome": "WIN", "is_correction": True, "corrects_grade_event_id": "grade-1", "correction_source": "stat_correction", "created_at": "2026-08-02T00:00:00Z"},
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposal_observations").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-1")

    leg = result.legs[0]
    assert [g["id"] for g in leg.grade_history] == ["grade-1", "grade-2"]  # original preserved, not erased
    assert leg.current_grade["id"] == "grade-2"  # the correction is authoritative
    assert leg.current_grade["outcome"] == "WIN"
    assert leg.grade_history[0]["outcome"] == "LOSS"  # original's own outcome unchanged


@pytest.mark.asyncio
@respx.mock
async def test_reconstruction_returns_postgame_review_when_present():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-1", "recommendation_type": "no_bet"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(200, json=[{"id": "pge-1", "grading_version": "v1", "outcome": "NOT_APPLICABLE", "is_correction": False, "created_at": "2026-08-01T00:00:00Z"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_postgame_reviews").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "review-1", "postgame_review_version": "v1", "outcome_summary": "No qualifying candidate.", "generated_at": "2026-08-01T00:05:00Z"}],
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-1")

    assert result.current_product_grade["outcome"] == "NOT_APPLICABLE"
    assert result.postgame_reviews[0]["outcome_summary"] == "No qualifying candidate."


@pytest.mark.asyncio
@respx.mock
async def test_reconstruction_returns_adaptive_weighting_evidence_when_present():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-1", "recommendation_type": "single"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(200, json=[{"recommendation_leg_id": "leg-1", "leg_order": 1}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": "only"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(return_value=httpx.Response(200, json=[]))
    _mock_empty_downstream_evidence()

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(
        return_value=httpx.Response(
            200, json=[{"id": "grade-1", "grading_version": "v1", "outcome": "WIN", "is_correction": False, "created_at": "2026-08-01T00:00:00Z"}]
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposal_observations").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "obs-1", "proposal_id": "prop-1", "recommendation_leg_grade_event_id": "grade-1", "classification": "correct", "notional_pnl": 0.91}],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(
        return_value=httpx.Response(200, json=[{"id": "prop-1", "agent_id": "agent-1", "status": "proposed", "weighting_version": "v1"}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-1")

    evidence = result.legs[0].weighting_evidence
    assert len(evidence) == 1
    assert evidence[0].observation["classification"] == "correct"
    assert evidence[0].proposal["id"] == "prop-1"


@pytest.mark.asyncio
@respx.mock
async def test_reconstruction_missing_downstream_evidence_stays_absent_not_fabricated():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-1", "recommendation_type": "single"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(200, json=[{"recommendation_leg_id": "leg-1", "leg_order": 1}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": "only"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(return_value=httpx.Response(200, json=[]))
    _mock_empty_downstream_evidence()
    _mock_empty_leg_evidence()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-1")

    assert result.lifecycle_events == []
    assert result.product_grade_history == []
    assert result.current_product_grade is None
    assert result.postgame_reviews == []
    leg = result.legs[0]
    assert leg.grade_history == []
    assert leg.current_grade is None
    assert leg.weighting_evidence == []


@pytest.mark.asyncio
@respx.mock
async def test_reconstruction_surfaces_frozen_prompt_model_provenance_and_preserves_historical_null():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-1", "recommendation_type": "single"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(200, json=[{"recommendation_leg_id": "leg-1", "leg_order": 1}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": "only"}])
    )
    # A leg explanation written AFTER this gate's change -- carries full
    # provenance for one agent, and a second agent whose row predates
    # prompt/model capture (Milestone 4.8/5.3), so its provenance is
    # genuinely NULL, never inferred.
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "expl-1",
                    "recommendation_leg_id": "leg-1",
                    "contributing_agents": [
                        {
                            "agent_name": "vegas_line_agent", "weight_applied": 1.0, "confidence": 0.8,
                            "prompt_name": "vegas_line_agent", "prompt_version": 2,
                            "model_name": "claude-x", "provider": "anthropic", "used_fallback": False,
                        },
                        {
                            "agent_name": "weather_agent", "weight_applied": 0.9, "confidence": 0.6,
                            "prompt_name": None, "prompt_version": None,
                            "model_name": None, "provider": None, "used_fallback": None,
                        },
                    ],
                }
            ],
        )
    )
    _mock_empty_downstream_evidence()
    _mock_empty_leg_evidence()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-1")

    contributing = result.legs[0].explanation["contributing_agents"]
    vegas, weather = contributing[0], contributing[1]
    assert vegas["prompt_name"] == "vegas_line_agent"
    assert vegas["model_name"] == "claude-x"
    assert vegas["used_fallback"] is False
    assert weather["prompt_name"] is None
    assert weather["model_name"] is None
    assert weather["used_fallback"] is None
