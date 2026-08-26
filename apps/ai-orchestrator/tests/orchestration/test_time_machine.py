"""Tests for app.orchestration.time_machine (Milestone 5.3) -- the
correlation/orchestration layer generating activation snapshots/leg
membership/source-product membership/lifecycle events from an already-
persisted SlateStrategyResult + ExplainabilityResult."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.features.strategy import EvaluatedCandidate, GameDecision, SlateStrategyResult
from app.orchestration.explainability import ExplainabilityResult, ProductExplanationResult
from app.orchestration.time_machine import generate_activation_snapshots

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


def _mock_snapshot_writes(*, snapshot_id: str = "snap-1", leg_row_id: str = "snap-leg-1", source_row_id: str = "snap-src-1", event_id: str = "event-1"):
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(201, json=[{"id": snapshot_id}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(
        return_value=httpx.Response(201, json=[{"id": event_id}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(201, json=[{"id": leg_row_id}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_source_products").mock(
        return_value=httpx.Response(201, json=[{"id": source_row_id}])
    )


@pytest.mark.asyncio
@respx.mock
async def test_no_bet_product_gets_a_snapshot_with_no_legs_and_an_activated_event():
    _mock_snapshot_writes()
    decision = SlateStrategyResult(
        outcome="bankroll_preservation",
        game_decisions=(GameDecision(game_id="g1", recommendation_id="rec-1", outcome="no_bet", legs=()),),
        legs=(),
    )
    explainability_result = ExplainabilityResult(products=[ProductExplanationResult(product_id="prod-nobet", recommendation_type="no_bet", status="generated", explanation_id="expl-nobet")])

    async with _client() as client:
        result = await generate_activation_snapshots(
            client, _headers(), decision=decision, created_product_ids=["prod-nobet", "prod-bp"], explainability_result=explainability_result
        )

    assert [s.status for s in result.snapshots] == ["generated", "generated"]
    assert result.legs == []


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=SUPABASE_URL)


@pytest.mark.asyncio
@respx.mock
async def test_no_bet_snapshot_references_its_own_explanation_id():
    captured = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(201, json=[{"id": f"snap-{len(captured)}"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(side_effect=_capture)
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(return_value=httpx.Response(201, json=[{"id": "event-1"}]))

    decision = SlateStrategyResult(
        outcome="bankroll_preservation",
        game_decisions=(GameDecision(game_id="g1", recommendation_id="rec-1", outcome="no_bet", legs=()),),
        legs=(),
    )
    explainability_result = ExplainabilityResult(
        products=[
            ProductExplanationResult(product_id="prod-nobet", recommendation_type="no_bet", status="generated", explanation_id="expl-nobet"),
            ProductExplanationResult(product_id="prod-bp", recommendation_type="bankroll_preservation", status="generated", explanation_id="expl-bp"),
        ]
    )

    async with _client() as client:
        await generate_activation_snapshots(
            client, _headers(), decision=decision, created_product_ids=["prod-nobet", "prod-bp"], explainability_result=explainability_result
        )

    nobet_payload = next(c for c in captured if c["recommendation_product_id"] == "prod-nobet")
    bp_payload = next(c for c in captured if c["recommendation_product_id"] == "prod-bp")
    assert nobet_payload["recommendation_product_explanation_id"] == "expl-nobet"
    assert bp_payload["recommendation_product_explanation_id"] == "expl-bp"


@pytest.mark.asyncio
@respx.mock
async def test_bankroll_preservation_records_source_products_for_each_no_bet_product():
    captured_sources = []

    def _capture_source(request: httpx.Request) -> httpx.Response:
        captured_sources.append(json.loads(request.content))
        return httpx.Response(201, json=[{"id": f"src-{len(captured_sources)}"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "snap-bp"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_lifecycle_events").mock(return_value=httpx.Response(201, json=[{"id": "event-1"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_source_products").mock(side_effect=_capture_source)

    decision = SlateStrategyResult(
        outcome="bankroll_preservation",
        game_decisions=(
            GameDecision(game_id="g1", recommendation_id="rec-1", outcome="no_bet", legs=()),
            GameDecision(game_id="g2", recommendation_id="rec-2", outcome="no_bet", legs=()),
        ),
        legs=(),
    )
    explainability_result = ExplainabilityResult()

    async with _client() as client:
        result = await generate_activation_snapshots(
            client, _headers(), decision=decision, created_product_ids=["prod-g1", "prod-g2", "prod-bp"], explainability_result=explainability_result
        )

    source_product_ids = {c["source_recommendation_product_id"] for c in captured_sources}
    assert source_product_ids == {"prod-g1", "prod-g2"}
    assert all(c["activation_snapshot_id"] == "snap-bp" for c in captured_sources)
    # bankroll_preservation itself carries no legs.
    assert result.legs == []


@pytest.mark.asyncio
@respx.mock
async def test_multiple_singles_freezes_leg_order_matching_decision_legs_order():
    _mock_snapshot_writes(snapshot_id="snap-ms")
    captured_legs = []

    def _capture_leg(request: httpx.Request) -> httpx.Response:
        captured_legs.append(json.loads(request.content))
        return httpx.Response(201, json=[{"id": f"snap-leg-{len(captured_legs)}"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(side_effect=_capture_leg)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-strong", "candidate_key": "strong"}, {"id": "leg-weak", "candidate_key": "weak"}])
    )

    strong = _candidate(candidate_key="strong", game_id="g1", recommendation_id="rec-1")
    weak = _candidate(candidate_key="weak", game_id="g2", recommendation_id="rec-2")
    decision = SlateStrategyResult(
        outcome="multiple_singles",
        game_decisions=(
            GameDecision(game_id="g1", recommendation_id="rec-1", outcome="qualified", legs=(strong,)),
            GameDecision(game_id="g2", recommendation_id="rec-2", outcome="qualified", legs=(weak,)),
        ),
        legs=(strong, weak),  # already ranked: strong first
    )
    explainability_result = ExplainabilityResult()

    async with _client() as client:
        result = await generate_activation_snapshots(
            client, _headers(), decision=decision, created_product_ids=["prod-ms"], explainability_result=explainability_result
        )

    assert len(result.legs) == 2
    assert all(leg.status == "generated" for leg in result.legs)
    strong_row = next(c for c in captured_legs if c["recommendation_leg_id"] == "leg-strong")
    weak_row = next(c for c in captured_legs if c["recommendation_leg_id"] == "leg-weak")
    assert strong_row["leg_order"] == 1
    assert weak_row["leg_order"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_single_product_snapshot_has_exactly_one_leg_row():
    _mock_snapshot_writes()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": "only"}])
    )
    only = _candidate(candidate_key="only")
    decision = SlateStrategyResult(
        outcome="single",
        game_decisions=(GameDecision(game_id="g1", recommendation_id="rec-1", outcome="qualified", legs=(only,)),),
        legs=(only,),
    )
    explainability_result = ExplainabilityResult()

    async with _client() as client:
        result = await generate_activation_snapshots(
            client, _headers(), decision=decision, created_product_ids=["prod-single"], explainability_result=explainability_result
        )

    assert len(result.snapshots) == 1
    assert result.snapshots[0].status == "generated"
    assert len(result.legs) == 1
    assert result.legs[0].status == "generated"


@pytest.mark.asyncio
@respx.mock
async def test_one_legs_missing_row_is_isolated_from_the_other_leg():
    _mock_snapshot_writes()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        # Only "weak" comes back -- "strong" is missing (defensive case, should never happen given
        # Milestone 5.1's own write-order contract, but must never silently corrupt the other leg).
        return_value=httpx.Response(200, json=[{"id": "leg-weak", "candidate_key": "weak"}])
    )
    strong = _candidate(candidate_key="strong", game_id="g1", recommendation_id="rec-1")
    weak = _candidate(candidate_key="weak", game_id="g2", recommendation_id="rec-2")
    decision = SlateStrategyResult(
        outcome="multiple_singles",
        game_decisions=(
            GameDecision(game_id="g1", recommendation_id="rec-1", outcome="qualified", legs=(strong,)),
            GameDecision(game_id="g2", recommendation_id="rec-2", outcome="qualified", legs=(weak,)),
        ),
        legs=(strong, weak),
    )
    explainability_result = ExplainabilityResult()

    async with _client() as client:
        result = await generate_activation_snapshots(
            client, _headers(), decision=decision, created_product_ids=["prod-ms"], explainability_result=explainability_result
        )

    by_key = {leg.candidate_key: leg for leg in result.legs}
    assert by_key["strong"].status == "failed"
    assert by_key["weak"].status == "generated"


@pytest.mark.asyncio
@respx.mock
async def test_activation_snapshot_failure_is_isolated_per_product():
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(return_value=httpx.Response(500, text="db error"))
    decision = SlateStrategyResult(
        outcome="bankroll_preservation",
        game_decisions=(GameDecision(game_id="g1", recommendation_id="rec-1", outcome="no_bet", legs=()),),
        legs=(),
    )
    explainability_result = ExplainabilityResult()

    async with _client() as client:
        result = await generate_activation_snapshots(
            client, _headers(), decision=decision, created_product_ids=["prod-nobet", "prod-bp"], explainability_result=explainability_result
        )

    assert [s.status for s in result.snapshots] == ["failed", "failed"]
    assert all(s.error for s in result.snapshots)
