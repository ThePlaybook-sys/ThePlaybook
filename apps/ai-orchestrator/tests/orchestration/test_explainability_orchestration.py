"""Tests for app.orchestration.explainability (Milestone 5.2) -- the
correlation/orchestration layer tying the pure domain logic and
persistence together. Exercises multi-game/multi-leg correlation and
per-unit isolation that the thin HTTP-boundary tests
(`tests/test_finalize_strategy_endpoint.py`) don't cover in depth."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.features.strategy import EvaluatedCandidate, GameDecision, RejectedCandidate, RejectionReason, SlateStrategyResult
from app.orchestration.explainability import generate_and_persist_explanations

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _candidate(**overrides) -> EvaluatedCandidate:
    defaults = dict(
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
    defaults.update(overrides)
    return EvaluatedCandidate(**defaults)


def _mock_common_reads(*, game_rows: dict[str, dict] | None = None):
    game_rows = game_rows or {}

    def _games_responder(request: httpx.Request) -> httpx.Response:
        game_id = request.url.params.get("id", "").removeprefix("eq.")
        row = game_rows.get(game_id, {"id": game_id, "home_team": "Home Team", "away_team": "Away Team"})
        return httpx.Response(200, json=[row])

    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_games_responder)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(201, json=[{"id": "prod-expl"}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(
        return_value=httpx.Response(201, json=[{"id": "leg-expl"}])
    )


@pytest.mark.asyncio
@respx.mock
async def test_correlates_multiple_no_bet_products_to_the_right_game():
    _mock_common_reads()
    g1_rejected = (RejectedCandidate(candidate=_candidate(game_id="g1"), reasons=(RejectionReason.BELOW_CONFIDENCE_FLOOR,)),)
    g2_rejected = (RejectedCandidate(candidate=_candidate(game_id="g2"), reasons=(RejectionReason.NON_POSITIVE_EV,)),)
    decision = SlateStrategyResult(
        outcome="bankroll_preservation",
        game_decisions=(
            GameDecision(game_id="g1", recommendation_id="rec-1", outcome="no_bet", legs=(), rejected=g1_rejected),
            GameDecision(game_id="g2", recommendation_id="rec-2", outcome="no_bet", legs=(), rejected=g2_rejected),
        ),
        legs=(),
    )

    captured = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(201, json=[{"id": f"expl-{len(captured)}"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(side_effect=_capture)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await generate_and_persist_explanations(
            client, _headers(), decision=decision, created_product_ids=["prod-g1", "prod-g2", "prod-bp"]
        )

    assert [p.status for p in result.products] == ["generated", "generated", "generated"]
    g1_payload = next(c for c in captured if c["recommendation_product_id"] == "prod-g1")
    g2_payload = next(c for c in captured if c["recommendation_product_id"] == "prod-g2")
    assert g1_payload["rejected_alternatives"][0]["reasons"] == ["BELOW_CONFIDENCE_FLOOR"]
    assert g2_payload["rejected_alternatives"][0]["reasons"] == ["NON_POSITIVE_EV"]


@pytest.mark.asyncio
@respx.mock
async def test_multiple_singles_produces_one_leg_explanation_per_leg_with_rank_position():
    _mock_common_reads()
    strong = _candidate(game_id="g1", recommendation_id="rec-1", candidate_key="strong", ev_per_dollar=0.09)
    weak = _candidate(game_id="g2", recommendation_id="rec-2", candidate_key="weak", ev_per_dollar=0.02)
    decision = SlateStrategyResult(
        outcome="multiple_singles",
        game_decisions=(
            GameDecision(game_id="g1", recommendation_id="rec-1", outcome="qualified", legs=(strong,)),
            GameDecision(game_id="g2", recommendation_id="rec-2", outcome="qualified", legs=(weak,)),
        ),
        legs=(strong, weak),  # already ranked: strong first
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(
            200, json=[{"id": "leg-strong", "candidate_key": "strong"}, {"id": "leg-weak", "candidate_key": "weak"}]
        )
    )

    captured = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(201, json=[{"id": f"leg-expl-{len(captured)}"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(side_effect=_capture)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await generate_and_persist_explanations(
            client, _headers(), decision=decision, created_product_ids=["prod-ms"]
        )

    assert len(result.legs) == 2
    assert all(leg.status == "generated" for leg in result.legs)
    strong_payload = next(c for c in captured if c["recommendation_leg_id"] == "leg-strong")
    weak_payload = next(c for c in captured if c["recommendation_leg_id"] == "leg-weak")
    assert "#1 of 2" in strong_payload["why_selected"]
    assert "#2 of 2" in weak_payload["why_selected"]


@pytest.mark.asyncio
@respx.mock
async def test_single_leg_reports_same_market_conflict_win_in_rejected_alternatives():
    _mock_common_reads()
    winner = _candidate(candidate_key="home-ml", selection="Home Team")
    loser = RejectedCandidate(
        candidate=_candidate(candidate_key="away-ml", selection="Away Team"),
        reasons=(RejectionReason.LOST_SAME_MARKET_CONFLICT,),
    )
    decision = SlateStrategyResult(
        outcome="single",
        game_decisions=(GameDecision(game_id="g1", recommendation_id="rec-1", outcome="qualified", legs=(winner,), rejected=(loser,)),),
        legs=(winner,),
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": "home-ml"}])
    )
    captured = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(201, json=[{"id": "leg-expl-1"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(side_effect=_capture)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await generate_and_persist_explanations(
            client, _headers(), decision=decision, created_product_ids=["prod-1"]
        )

    assert result.legs[0].status == "generated"
    payload = captured[0]
    assert payload["rejected_alternatives"] == [
        {"candidate_key": "away-ml", "market_type": "moneyline", "selection": "Away Team", "reasons": ["LOST_SAME_MARKET_CONFLICT"]}
    ]
    assert "opposing side" in payload["why_selected"]


@pytest.mark.asyncio
@respx.mock
async def test_one_legs_read_failure_never_blocks_the_other_leg():
    strong = _candidate(game_id="g1", recommendation_id="rec-1", candidate_key="strong")
    weak = _candidate(game_id="g2", recommendation_id="rec-2", candidate_key="weak")
    decision = SlateStrategyResult(
        outcome="multiple_singles",
        game_decisions=(
            GameDecision(game_id="g1", recommendation_id="rec-1", outcome="qualified", legs=(strong,)),
            GameDecision(game_id="g2", recommendation_id="rec-2", outcome="qualified", legs=(weak,)),
        ),
        legs=(strong, weak),
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(
            200, json=[{"id": "leg-strong", "candidate_key": "strong"}, {"id": "leg-weak", "candidate_key": "weak"}]
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(201, json=[{"id": "prod-expl"}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(
        return_value=httpx.Response(201, json=[{"id": "leg-expl"}])
    )

    def _games_responder(request: httpx.Request) -> httpx.Response:
        game_id = request.url.params.get("id", "").removeprefix("eq.")
        if game_id == "g1":
            return httpx.Response(500, text="db error")
        return httpx.Response(200, json=[{"id": game_id, "home_team": "Home Team", "away_team": "Away Team"}])

    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_games_responder)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await generate_and_persist_explanations(
            client, _headers(), decision=decision, created_product_ids=["prod-ms"]
        )

    by_key = {leg.candidate_key: leg for leg in result.legs}
    assert by_key["strong"].status == "failed"
    assert by_key["weak"].status == "generated"
