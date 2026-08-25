"""Tests for app.orchestration.consensus (Milestone 4.7; split into
run_shared_consensus / run_elite_reconciliation / finalize_consensus in
Milestone 4.9, Decision 2)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.agents.committee_context import ParticipationMetadata
from app.features.candidate import MarketCandidate
from app.features.consensus import ConsensusResult
from app.models.fake_adapter import FakeModelAdapter, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.orchestration import consensus as consensus_module
from app.orchestration.consensus import finalize_consensus, run_elite_reconciliation, run_shared_consensus
from tests.conftest import mock_prompt_registry_route

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _candidate(**overrides) -> MarketCandidate:
    base = dict(
        game_id="g1", sportsbook="DraftKings", market_type="moneyline", selection="KC",
        american_odds=-125, point=None, observed_at=datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return MarketCandidate(**base)


def _participation() -> ParticipationMetadata:
    return ParticipationMetadata(
        configured_agents=frozenset({"injury_intelligence_agent", "weather_agent"}),
        built_agents=frozenset({"injury_intelligence_agent", "weather_agent"}),
        deferred_agents=frozenset(),
        attempted_agents=frozenset({"injury_intelligence_agent", "weather_agent"}),
        successful_agents=frozenset({"injury_intelligence_agent", "weather_agent"}),
        failed_agents=frozenset(),
        fan_out_status="full",
        committee_completeness=1.0,
    )


def _agent_output_row(agent_name: str, *, category: str, confidence: float, weight_applied: float, directional_lean: str, evidence_classification: str = "data_backed") -> dict:
    return {
        "raw_output": {
            "agent_name": agent_name, "finding": "f", "supporting_evidence": [],
            "evidence_classification": evidence_classification, "directional_lean": directional_lean, "confidence": confidence,
            "would_change_mind_if": "x",
        },
        "agent_confidence": confidence,
        "weight_applied": weight_applied,
        "agents": {"name": agent_name, "category": category},
    }


def _mock_agent_outputs(rows: list[dict]):
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=rows))


def _meta_json(adjustment: float = -0.05) -> str:
    return json.dumps({"agent_name": "meta_agent", "polarization_score": 0.2, "uncertainty_flag": False, "confidence_adjustment": adjustment, "reasoning": "r"})


def _elite_json(adjustment: float = -0.08) -> str:
    return json.dumps({
        "agent_name": "consensus_reconciliation_agent", "candidate_key": "k", "reasoning": "r",
        "confidence_adjustment": adjustment, "supporting_evidence": [], "would_change_mind_if": "x",
    })


def _routing_rules() -> dict:
    return {
        "meta_agent_review": {"task_type": "meta_agent_review", "primary_model": "claude-sonnet-5", "fallback_model": None},
        "consensus_reconciliation": {"task_type": "consensus_reconciliation", "primary_model": "claude-opus-5", "fallback_model": None},
    }


# --- run_shared_consensus: no user/tier concept, never persists ---


@pytest.mark.asyncio
@respx.mock
async def test_no_consensus_when_zero_agent_rows_and_nothing_persisted():
    _mock_agent_outputs([])
    snapshot_route = respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "snap-test-1"}]))
    registry = AdapterRegistry(adapters={"anthropic": FakeModelAdapter(provider="anthropic", script=[])})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1", candidate=_candidate(),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )

    assert result.status == "no_consensus"
    assert result.after_meta_confidence is None
    assert snapshot_route.call_count == 0  # run_shared_consensus never persists at all


@pytest.mark.asyncio
@respx.mock
async def test_no_consensus_for_prop_candidate_not_fabricated():
    _mock_agent_outputs([_agent_output_row("injury_intelligence_agent", category="context", confidence=0.7, weight_applied=1.0, directional_lean="home")])
    registry = AdapterRegistry(adapters={"anthropic": FakeModelAdapter(provider="anthropic", script=[])})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1",
            candidate=_candidate(market_type="prop", selection="Mahomes Over 1.5 TDs"),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )

    assert result.status == "no_consensus"


@pytest.mark.asyncio
@respx.mock
async def test_computed_consensus_full_flow_persists_expected_values():
    rows = [
        _agent_output_row("injury_intelligence_agent", category="context", confidence=0.7, weight_applied=1.0, directional_lean="home"),
        _agent_output_row("weather_agent", category="context", confidence=0.6, weight_applied=0.5, directional_lean="away", evidence_classification="assumption"),
    ]
    _mock_agent_outputs(rows)
    mock_prompt_registry_route(SUPABASE_URL)
    snapshot_route = respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "snap-test-1"}]))
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_meta_json(adjustment=-0.05))])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        shared = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1", candidate=_candidate(),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )
        assert snapshot_route.call_count == 0  # not yet finalized
        finalize_result = await finalize_consensus(
            client, _headers(), recommendation_id="r1", candidate=_candidate(), participation=_participation(), shared=shared,
        )

    assert shared.status == "computed"
    # aggregate = (0.7*1.0*1.0 + 0.6*0.25*0.3) / 1.25 = 0.596
    assert shared.consensus.aggregate_confidence == pytest.approx(0.596)
    assert finalize_result.final_aggregate_confidence == pytest.approx(0.596 - 0.05)
    assert finalize_result.second_pass_triggered is False
    assert finalize_result.below_confidence_floor is True  # 0.546 < 0.55

    assert snapshot_route.call_count == 1  # exactly one persist call, ever
    sent = json.loads(snapshot_route.calls.last.request.content)
    assert sent["candidate_key"] == "g1:DraftKings:moneyline:KC:none"
    assert sent["aggregate_confidence"] == pytest.approx(0.596)
    assert sent["final_aggregate_confidence"] == pytest.approx(0.546)
    assert sent["second_pass_triggered"] is False
    assert sent["participation_metadata"]["fan_out_status"] == "full"


@pytest.mark.asyncio
@respx.mock
async def test_weight_source_is_persisted_weight_applied_never_fresh_agents_query():
    rows = [_agent_output_row("injury_intelligence_agent", category="context", confidence=0.7, weight_applied=1.0, directional_lean="home")]
    _mock_agent_outputs(rows)
    mock_prompt_registry_route(SUPABASE_URL)
    agents_route = respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 99.0}]))
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_meta_json())])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        shared = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1", candidate=_candidate(),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )

    assert agents_route.call_count == 0  # never re-reads agents.current_weight
    # confirms weight_applied=1.0 (persisted), not the mocked-but-unused current_weight=99.0
    assert shared.consensus.aggregate_confidence == pytest.approx(0.7)


@pytest.mark.asyncio
@respx.mock
async def test_meta_positive_adjustment_rejected_treated_as_no_adjustment():
    rows = [_agent_output_row("injury_intelligence_agent", category="context", confidence=0.7, weight_applied=1.0, directional_lean="home")]
    _mock_agent_outputs(rows)
    mock_prompt_registry_route(SUPABASE_URL)
    malformed_meta = json.dumps({"agent_name": "meta_agent", "polarization_score": 0.2, "uncertainty_flag": False, "confidence_adjustment": 0.5, "reasoning": "r"})
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=malformed_meta)])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        shared = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1", candidate=_candidate(),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )

    assert shared.meta_result.status == "failed"  # Pydantic validator rejected the positive adjustment
    assert shared.after_meta_confidence == pytest.approx(shared.consensus.aggregate_confidence)  # no adjustment applied


@pytest.mark.asyncio
@respx.mock
async def test_final_confidence_floors_at_zero():
    rows = [_agent_output_row("injury_intelligence_agent", category="context", confidence=0.05, weight_applied=1.0, directional_lean="home")]
    _mock_agent_outputs(rows)
    mock_prompt_registry_route(SUPABASE_URL)
    respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "snap-test-1"}]))
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_meta_json(adjustment=-0.5))])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        shared = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1", candidate=_candidate(),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )
        finalize_result = await finalize_consensus(
            client, _headers(), recommendation_id="r1", candidate=_candidate(), participation=_participation(), shared=shared,
        )

    assert finalize_result.final_aggregate_confidence == 0.0
    assert finalize_result.final_aggregate_confidence <= shared.consensus.aggregate_confidence


@pytest.mark.asyncio
@respx.mock
async def test_candidate_specific_consensus_no_cross_contamination():
    rows = [
        _agent_output_row("injury_intelligence_agent", category="context", confidence=0.7, weight_applied=1.0, directional_lean="home"),
    ]
    _mock_agent_outputs(rows)
    mock_prompt_registry_route(SUPABASE_URL)
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_meta_json(adjustment=0.0)), ScriptedSuccess(raw_text=_meta_json(adjustment=0.0))])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        moneyline_result = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1",
            candidate=_candidate(market_type="moneyline", selection="KC"),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )
        totals_result = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1",
            candidate=_candidate(market_type="total", selection="Over", point=47.5),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )

    # Same underlying game-level agent output, but the "home" lean votes
    # for the moneyline candidate and does NOT vote for the totals one:
    assert moneyline_result.consensus.aggregate_confidence == pytest.approx(0.7)
    assert totals_result.consensus.aggregate_confidence is None
    assert totals_result.status == "no_consensus"


# --- run_elite_reconciliation: caller-resolved tier, at most once per candidate ---


@pytest.mark.asyncio
@respx.mock
async def test_elite_reconciliation_is_a_noop_when_shared_consensus_never_computed():
    elite_route = respx.post(f"{SUPABASE_URL}/rest/v1/consensus_reconciliation").mock(return_value=httpx.Response(201, json=[{}]))
    shared = consensus_module.SharedConsensusResult(
        status="no_consensus", consensus=None, meta_result=None, review_context=None, after_meta_confidence=None, model_routing_used={}
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_elite_reconciliation(
            shared, client, _headers(), tier="elite", routing_rules=_routing_rules(), adapter_registry=AdapterRegistry(adapters={}),
        )

    assert result.triggered is False
    assert result.elite_result is None
    assert elite_route.call_count == 0  # never reaches any I/O -- nothing to reconcile


@pytest.mark.asyncio
@respx.mock
async def test_elite_reconciliation_never_triggers_when_tier_is_none():
    rows = [_agent_output_row("injury_intelligence_agent", category="context", confidence=0.7, weight_applied=1.0, directional_lean="home")]
    _mock_agent_outputs(rows)
    mock_prompt_registry_route(SUPABASE_URL)
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_meta_json())])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        shared = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1", candidate=_candidate(),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )
        # No user resolved this cycle -- caller passes tier=None, exactly
        # as if it never even checked subscriptions:
        elite = await run_elite_reconciliation(
            shared, client, _headers(), tier=None, routing_rules=_routing_rules(), adapter_registry=registry,
        )

    assert elite.triggered is False
    assert elite.final_aggregate_confidence == pytest.approx(shared.after_meta_confidence)


@pytest.mark.asyncio
@respx.mock
async def test_elite_trigger_wiring_when_variance_exceeds_threshold_and_tier_is_elite(monkeypatch):
    """`compute_consensus` can never naturally produce agreement_variance
    > 0.1225 given the current {1.0, 0.3} lean_factor scheme (see
    `should_trigger_elite_second_pass`'s docstring for the exact
    mathematical ceiling) -- monkeypatched here SOLELY to prove the
    Elite-trigger WIRING (evidence assembly, model call, persistence)
    is correct once/if a future formula change allows the threshold to
    be reached naturally. This is flagged explicitly, not a claim that
    this scenario occurs in real usage today."""
    fabricated_high_variance_result = ConsensusResult(aggregate_confidence=0.7, agreement_variance=0.5, voting_agent_count=2, non_voting_agent_count=0)
    monkeypatch.setattr(consensus_module, "compute_consensus", lambda *a, **k: fabricated_high_variance_result)

    _mock_agent_outputs([_agent_output_row("injury_intelligence_agent", category="context", confidence=0.7, weight_applied=1.0, directional_lean="home")])
    mock_prompt_registry_route(SUPABASE_URL)
    snapshot_route = respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "snap-test-1"}]))
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_meta_json(adjustment=-0.05)), ScriptedSuccess(raw_text=_elite_json(adjustment=-0.08))])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        shared = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1", candidate=_candidate(),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )
        elite = await run_elite_reconciliation(
            shared, client, _headers(), tier="elite", routing_rules=_routing_rules(), adapter_registry=registry,
        )
        finalize_result = await finalize_consensus(
            client, _headers(), recommendation_id="r1", candidate=_candidate(), participation=_participation(), shared=shared, elite=elite,
        )

    assert elite.triggered is True
    assert elite.elite_result.status == "success"
    assert finalize_result.second_pass_triggered is True
    assert finalize_result.final_aggregate_confidence == pytest.approx(0.7 - 0.05 - 0.08)
    assert snapshot_route.call_count == 1  # exactly one persist call, even with Elite reconciliation
    sent = json.loads(snapshot_route.calls.last.request.content)
    assert sent["second_pass_triggered"] is True
    assert set(sent["model_routing_used"].keys()) == {"meta_agent", "consensus_reconciliation_agent"}


@pytest.mark.asyncio
@respx.mock
async def test_elite_not_triggered_for_free_tier_even_with_high_variance(monkeypatch):
    fabricated_high_variance_result = ConsensusResult(aggregate_confidence=0.7, agreement_variance=0.5, voting_agent_count=2, non_voting_agent_count=0)
    monkeypatch.setattr(consensus_module, "compute_consensus", lambda *a, **k: fabricated_high_variance_result)

    _mock_agent_outputs([_agent_output_row("injury_intelligence_agent", category="context", confidence=0.7, weight_applied=1.0, directional_lean="home")])
    mock_prompt_registry_route(SUPABASE_URL)
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_meta_json())])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        shared = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1", candidate=_candidate(),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )
        elite = await run_elite_reconciliation(
            shared, client, _headers(), tier="free", routing_rules=_routing_rules(), adapter_registry=registry,
        )

    assert elite.triggered is False
    assert elite.elite_result is None


@pytest.mark.asyncio
@respx.mock
async def test_elite_positive_adjustment_rejected_treated_as_no_adjustment(monkeypatch):
    fabricated_high_variance_result = ConsensusResult(aggregate_confidence=0.7, agreement_variance=0.5, voting_agent_count=2, non_voting_agent_count=0)
    monkeypatch.setattr(consensus_module, "compute_consensus", lambda *a, **k: fabricated_high_variance_result)

    _mock_agent_outputs([_agent_output_row("injury_intelligence_agent", category="context", confidence=0.7, weight_applied=1.0, directional_lean="home")])
    mock_prompt_registry_route(SUPABASE_URL)
    malformed_elite = json.dumps({"agent_name": "consensus_reconciliation_agent", "candidate_key": "k", "reasoning": "r", "confidence_adjustment": 0.2, "supporting_evidence": [], "would_change_mind_if": "x"})
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_meta_json(adjustment=-0.05)), ScriptedSuccess(raw_text=malformed_elite)])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        shared = await run_shared_consensus(
            client, _headers(), recommendation_id="r1", correlation_id="corr-1", game_id="g1", candidate=_candidate(),
            home_team="KC", away_team="BAL", participation=_participation(), routing_rules=_routing_rules(), adapter_registry=registry,
        )
        elite = await run_elite_reconciliation(
            shared, client, _headers(), tier="elite", routing_rules=_routing_rules(), adapter_registry=registry,
        )

    assert elite.elite_result.status == "failed"
    assert elite.final_aggregate_confidence == pytest.approx(0.7 - 0.05)  # only Meta's adjustment applied
