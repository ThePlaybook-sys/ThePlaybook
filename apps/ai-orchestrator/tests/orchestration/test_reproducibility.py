"""THE reproducibility test (Milestone 5.3, Decision BD) -- the roadmap's
own acceptance criterion, named there as "the single most important
acceptance test in the entire roadmap": activate a recommendation
product, mutate live/current configuration, then confirm reconstruction
still shows the ORIGINAL frozen facts, never the current ones.

Runs the real pipeline end to end (`finalize_slate_strategy`:
`app.features.strategy` -> `app.persistence.recommendation_products` ->
`app.orchestration.explainability` -> `app.orchestration.time_machine`),
then `app.orchestration.reconstruction.reconstruct_recommendation_product`
against the result -- proving reconstruction is possible from the real
persisted rows, not asserted against a hand-built fixture.

**How "never reads live/mutable state" is proven, not just claimed:**
`/rest/v1/agents`, `/rest/v1/prompt_registry`, `/rest/v1/model_routing_rules`,
`/rest/v1/odds_snapshots`, and `/rest/v1/user_profiles` are deliberately
mocked here to return DIFFERENT ("mutated") values than what was in
effect at activation time -- and reconstruction still returns the
ORIGINAL frozen values, because `app.orchestration.reconstruction` has no
code path that queries any of those tables at all. If reconstruction ever
gained a call to one of them, this test would start reflecting the
mutated value and fail."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.features.strategy import EvaluatedCandidate, GameCandidates
from app.orchestration.reconstruction import reconstruct_recommendation_product
from app.orchestration.strategy_finalize import finalize_slate_strategy

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _candidate() -> EvaluatedCandidate:
    return EvaluatedCandidate(
        game_id="g1",
        recommendation_id="rec-1",
        consensus_snapshot_id="snap-1",
        candidate_key="g1:draftkings:moneyline:Home Team:none",
        market_type="moneyline",
        selection="Home Team",
        sportsbook="draftkings",
        american_odds=-110,
        point=None,
        decimal_odds=1.909,
        ev_per_dollar=0.05,
        final_aggregate_confidence=0.71,
    )


@pytest.mark.asyncio
@respx.mock
async def test_reconstruction_is_unaffected_by_live_mutations_after_activation():
    # --- Step 1: activate a `single` product through the real pipeline. ---
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(201, json=[{"id": "prod-1"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(201, json=[{"id": "leg-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g1", "home_team": "Home Team", "away_team": "Away Team"}])
    )
    # The ONE game-level committee agent that voted, at ACTIVATION-TIME
    # weight 1.0 -- this is what gets frozen into the leg explanation's
    # `contributing_agents` JSON.
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "agent_name": "vegas_line_agent",
                    "directional_lean": "home",
                    "confidence": 0.8,
                    "evidence_classification": "data_backed",
                    "weight_applied": 1.0,
                    "would_change_mind_if": "line moves 3+ points",
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(201, json=[{"id": "prod-expl-1"}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(
        return_value=httpx.Response(201, json=[{"id": "leg-expl-1"}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(201, json=[{"id": "snap-1"}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(
        return_value=httpx.Response(201, json=[{"id": "event-1"}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(201, json=[{"id": "snap-leg-1"}])
    )
    # Read back during activation -- both Explainability (leg
    # correlation, Milestone 5.2) and Time Machine (leg-order freezing,
    # Milestone 5.3) discover `recommendation_legs.id` by `candidate_key`
    # match this same way.
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": "g1:draftkings:moneyline:Home Team:none"}])
    )

    games = [GameCandidates(game_id="g1", recommendation_id="rec-1", candidates=(_candidate(),))]
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        decision, created_ids, explainability_result, time_machine_result = await finalize_slate_strategy(
            client, _headers(), master_refresh_run_id="run-1", games=games
        )

    assert decision.outcome == "single"
    assert time_machine_result.snapshots[0].status == "generated"
    assert time_machine_result.legs[0].status == "generated"

    # --- Step 2: mock every live/mutable-source table to return
    # DIFFERENT ("mutated") values than were in effect at activation --
    # if reconstruction ever queries any of these, the test below fails. ---
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"name": "vegas_line_agent", "current_weight": 999.0}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(
        return_value=httpx.Response(200, json=[{"prompt_name": "vegas_line_agent", "version": 999, "prompt_text": "MUTATED PROMPT"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/model_routing_rules").mock(
        return_value=httpx.Response(200, json=[{"task_type": "vegas_line", "primary_model": "some-future-model"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(
        return_value=httpx.Response(200, json=[{"game_id": "g1", "american_odds": +250, "captured_at": "2099-01-01T00:00:00Z"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(
        return_value=httpx.Response(200, json=[{"user_id": "user-1", "risk_tolerance": "aggressive"}])
    )

    # --- Step 3: mock the frozen reads reconstruction is ALLOWED to use,
    # returning the ORIGINAL activation-time values. ---
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-1", "recommendation_type": "single"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": "prod-expl-1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(200, json=[{"recommendation_leg_id": "leg-1", "leg_order": 1}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "leg-1",
                    "candidate_key": "g1:draftkings:moneyline:Home Team:none",
                    "american_odds": -110,
                    "decimal_odds": 1.909,
                    "ev_per_dollar": 0.05,
                    "final_aggregate_confidence": 0.71,
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "leg-expl-1",
                    "recommendation_leg_id": "leg-1",
                    "contributing_agents": [{"agent_name": "vegas_line_agent", "weight_applied": 1.0, "confidence": 0.8}],
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-expl-1", "why_this_shape": "exactly one candidate qualified"}])
    )
    # Downstream evidence (Pre-Phase-6 Operational Readiness Gate, Section
    # 9) -- none exists yet for a just-activated product; reconstruction
    # must read these and correctly find nothing, not skip reading them.
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_postgame_reviews").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=[]))

    # --- Step 4: reconstruct. Never touches the mutated tables above. ---
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        reconstructed = await reconstruct_recommendation_product(
            client, _headers(), recommendation_product_id=created_ids[0]
        )

    # Original activation-time facts, unaffected by the "current" mutated
    # weight/prompt/model/odds/risk-tolerance mocked above:
    assert reconstructed.strategy_version == "v1"
    assert reconstructed.product_explanation["why_this_shape"] == "exactly one candidate qualified"
    assert len(reconstructed.legs) == 1
    leg = reconstructed.legs[0]
    assert leg.leg["american_odds"] == -110  # NOT the mutated +250
    assert leg.leg["ev_per_dollar"] == 0.05
    assert leg.leg["final_aggregate_confidence"] == 0.71
    assert leg.explanation["contributing_agents"][0]["weight_applied"] == 1.0  # NOT the mutated 999.0
