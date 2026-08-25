"""Tests for app.orchestration.recommendation_worker (Milestone 4.9) --
the top-level per-game entry point tying game-level fan-out, candidate
generation, the shared chain, consensus, Elite reconciliation, and
per-subscriber Bankroll Coach together."""
from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest
import respx

from app.models.fake_adapter import FakeModelAdapter, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.orchestration import consensus as consensus_module
from app.orchestration import recommendation_worker as worker_module
from app.orchestration.recommendation_worker import RecommendationWorkerError, run_game_recommendation
from app.features.consensus import ConsensusResult
from tests.conftest import mock_prompt_registry_route

SUPABASE_URL = "https://test-project.supabase.co"

GAME_LEVEL_AGENT_NAMES = (
    "injury_intelligence_agent",
    "weather_agent",
    "vegas_line_agent",
    "closing_line_movement_agent",
    "travel_fatigue_agent",
    "rest_days_agent",
)

TASK_TYPES = (
    "injury_analysis", "weather_analysis", "vegas_line_analysis", "closing_line_movement_analysis",
    "travel_fatigue_analysis", "rest_days_analysis", "probability_modeling_analysis", "expected_value_analysis",
    "risk_manager_analysis", "bankroll_coach_analysis", "meta_agent_review", "consensus_reconciliation",
)


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _routing_rules() -> dict[str, dict]:
    return {t: {"task_type": t, "primary_model": "claude-sonnet-5", "fallback_model": None} for t in TASK_TYPES}


def _game_row(**overrides) -> dict:
    base = dict(
        id="g1", status="scheduled", scheduled_start="2026-09-21T20:00:00+00:00",
        home_team="KC", away_team="BAL", season_type="regular", week=3,
        venue_lat=None, venue_long=None, stadium=None, venue_type=None,
    )
    base.update(overrides)
    return base


def _agent_output_json(agent_name: str) -> str:
    return json.dumps({
        "agent_name": agent_name, "finding": "finding", "supporting_evidence": [],
        "evidence_classification": "data_backed", "directional_lean": "none", "confidence": 0.6,
        "would_change_mind_if": "x",
    })


def _probability_json(candidate_key: str, selection: str) -> str:
    return json.dumps({
        "agent_name": "probability_modeling_agent", "candidate_key": candidate_key, "selection": selection,
        "modeled_probability": 0.6, "confidence_in_probability": 0.7, "reasoning": "r",
        "supporting_evidence": [], "would_change_mind_if": "x",
    })


def _meta_json(adjustment: float = -0.02) -> str:
    return json.dumps({
        "agent_name": "meta_agent", "polarization_score": 0.1, "uncertainty_flag": False,
        "confidence_adjustment": adjustment, "reasoning": "r",
    })


def _elite_json(adjustment: float = -0.05) -> str:
    return json.dumps({
        "agent_name": "consensus_reconciliation_agent", "candidate_key": "k", "reasoning": "r",
        "confidence_adjustment": adjustment, "supporting_evidence": [], "would_change_mind_if": "x",
    })


def _mock_common(*, game: dict | None = None, odds_rows: list | None = None, subscribers: list | None = None):
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games", params={"status": "eq.final"}).mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[game] if game else []))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=odds_rows or []))
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(200, json=subscribers or []))
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(return_value=httpx.Response(200, json=[]))
    mock_prompt_registry_route(SUPABASE_URL)


@pytest.mark.asyncio
@respx.mock
async def test_game_not_found_raises_error(monkeypatch):
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings")
    _mock_common(game=None)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationWorkerError):
            await run_game_recommendation(
                client, _headers(), game_id="ghost", correlation_id="corr-1", prompt_version="v1", agent_version="v1",
                routing_rules=_routing_rules(), adapter_registry=AdapterRegistry(adapters={}),
            )


@pytest.mark.asyncio
@respx.mock
async def test_game_skipped_when_no_odds_zero_candidates_and_no_downstream_persistence(monkeypatch):
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings")
    _mock_common(game=_game_row(), odds_rows=[])
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    snapshot_route = respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "snap-test-1"}]))
    adapter = FakeModelAdapter(provider="anthropic", script=[])  # never called -- prompt_registry mock lets it isolate cleanly
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_game_recommendation(
            client, _headers(), game_id="g1", correlation_id="corr-1", prompt_version="v1", agent_version="v1",
            routing_rules=_routing_rules(), adapter_registry=registry,
        )

    assert result.game_skipped_reason == "no_configured_sportsbook_has_fresh_data"
    assert result.candidates == []
    assert snapshot_route.call_count == 0  # no candidate ever reached consensus
    # game-level fan-out still ran (6 agents), but every one failed cleanly
    # (empty script -> FakeAdapterExhausted, isolated) -- zero outputs persisted:
    assert output_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_full_wiring_one_candidate_consensus_and_bankroll_coach_per_subscriber(monkeypatch):
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings")
    now_iso = "2026-09-21T17:00:00+00:00"
    game = _game_row(scheduled_start="2026-09-21T20:00:00+00:00")
    odds_rows = [{
        "sportsbook": "draftkings", "market_type": "moneyline",
        "line_data": {"outcomes": [{"name": "KC", "price": -150}]}, "captured_at": now_iso,
    }]
    subscribers = [
        {"user_id": "u_elite", "tier": "elite", "created_at": "2026-08-01T00:00:00+00:00"},
        {"user_id": "u_free", "tier": "free", "created_at": "2026-08-01T00:00:00+00:00"},
    ]
    _mock_common(game=game, odds_rows=odds_rows, subscribers=subscribers)
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(200, json=[{
            "raw_output": {"agent_name": "injury_intelligence_agent", "finding": "f", "supporting_evidence": [],
                            "evidence_classification": "data_backed", "directional_lean": "home", "confidence": 0.6, "would_change_mind_if": "x"},
            "agent_confidence": 0.6, "weight_applied": 1.0, "agents": {"name": "injury_intelligence_agent", "category": "context"},
        }])
    )
    snapshot_route = respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "snap-test-1"}]))

    candidate_key = "g1:draftkings:moneyline:KC:none"
    script = (
        [ScriptedSuccess(raw_text=_agent_output_json(name)) for name in GAME_LEVEL_AGENT_NAMES]
        + [ScriptedSuccess(raw_text=_probability_json(candidate_key, "KC"))]
        + [ScriptedSuccess(raw_text=_agent_output_json("expected_value_agent"))]
        + [ScriptedSuccess(raw_text=_agent_output_json("risk_manager_agent"))]
        + [ScriptedSuccess(raw_text=_meta_json())]
        + [ScriptedSuccess(raw_text=_agent_output_json("bankroll_coach_agent")) for _ in subscribers]
    )
    adapter = FakeModelAdapter(provider="anthropic", script=script)
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_game_recommendation(
            client, _headers(), game_id="g1", correlation_id="corr-1", prompt_version="v1", agent_version="v1",
            routing_rules=_routing_rules(), adapter_registry=registry, now=datetime.fromisoformat(now_iso),
        )

    assert result.sportsbook_used == "draftkings"
    assert result.game_skipped_reason is None
    assert len(result.candidates) == 1
    candidate_result = result.candidates[0]
    assert candidate_result.status == "evaluated"
    assert candidate_result.shared_chain_status == "full"
    assert candidate_result.consensus_status == "computed"
    assert candidate_result.second_pass_triggered is False  # real variance never exceeds the threshold here
    assert candidate_result.bankroll_coach_user_count == 2  # both subscribers, elite and free alike
    assert snapshot_route.call_count == 1  # exactly one persist per candidate
    assert output_route.call_count == 6 + 3 + 2  # game-level + shared chain + 2 bankroll coach rows

    # Milestone 5.1: a computed-consensus candidate with a priced
    # (american_odds is not None) EV yields a strategy_input carrying the
    # SAME frozen market fields/EV/confidence this cycle just computed --
    # never re-read back from persistence.
    strategy_input = candidate_result.strategy_input
    assert strategy_input is not None
    assert strategy_input.game_id == "g1"
    assert strategy_input.recommendation_id == "r1"
    assert strategy_input.consensus_snapshot_id == "snap-test-1"
    assert strategy_input.candidate_key == candidate_key
    assert strategy_input.market_type == "moneyline"
    assert strategy_input.selection == "KC"
    assert strategy_input.american_odds == -150
    assert strategy_input.final_aggregate_confidence is not None
    assert strategy_input.ev_per_dollar is not None


@pytest.mark.asyncio
@respx.mock
async def test_elite_reconciliation_triggered_once_and_reused_never_per_subscriber(monkeypatch):
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings")
    fabricated_high_variance = ConsensusResult(aggregate_confidence=0.7, agreement_variance=0.5, voting_agent_count=2, non_voting_agent_count=0)
    monkeypatch.setattr(consensus_module, "compute_consensus", lambda *a, **k: fabricated_high_variance)

    now_iso = "2026-09-21T17:00:00+00:00"
    game = _game_row(scheduled_start="2026-09-21T20:00:00+00:00")
    odds_rows = [{
        "sportsbook": "draftkings", "market_type": "moneyline",
        "line_data": {"outcomes": [{"name": "KC", "price": -150}]}, "captured_at": now_iso,
    }]
    # Two Elite subscribers -- proves Elite reconciliation is computed
    # ONCE per candidate, reused for both, never once per Elite user:
    subscribers = [
        {"user_id": "u_elite_1", "tier": "elite", "created_at": "2026-08-01T00:00:00+00:00"},
        {"user_id": "u_elite_2", "tier": "elite", "created_at": "2026-08-02T00:00:00+00:00"},
    ]
    _mock_common(game=game, odds_rows=odds_rows, subscribers=subscribers)
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(200, json=[{
            "raw_output": {"agent_name": "injury_intelligence_agent", "finding": "f", "supporting_evidence": [],
                            "evidence_classification": "data_backed", "directional_lean": "home", "confidence": 0.6, "would_change_mind_if": "x"},
            "agent_confidence": 0.6, "weight_applied": 1.0, "agents": {"name": "injury_intelligence_agent", "category": "context"},
        }])
    )
    snapshot_route = respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "snap-test-1"}]))

    candidate_key = "g1:draftkings:moneyline:KC:none"
    script = (
        [ScriptedSuccess(raw_text=_agent_output_json(name)) for name in GAME_LEVEL_AGENT_NAMES]
        + [ScriptedSuccess(raw_text=_probability_json(candidate_key, "KC"))]
        + [ScriptedSuccess(raw_text=_agent_output_json("expected_value_agent"))]
        + [ScriptedSuccess(raw_text=_agent_output_json("risk_manager_agent"))]
        + [ScriptedSuccess(raw_text=_meta_json())]
        + [ScriptedSuccess(raw_text=_elite_json())]  # exactly one Elite call, not two
        + [ScriptedSuccess(raw_text=_agent_output_json("bankroll_coach_agent")) for _ in subscribers]
    )
    adapter = FakeModelAdapter(provider="anthropic", script=script)
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_game_recommendation(
            client, _headers(), game_id="g1", correlation_id="corr-1", prompt_version="v1", agent_version="v1",
            routing_rules=_routing_rules(), adapter_registry=registry, now=datetime.fromisoformat(now_iso),
        )

    candidate_result = result.candidates[0]
    assert candidate_result.second_pass_triggered is True
    assert candidate_result.bankroll_coach_user_count == 2
    sent = json.loads(snapshot_route.calls.last.request.content)
    assert sent["second_pass_triggered"] is True
    # FakeModelAdapter's script (exactly one _elite_json entry) being fully
    # consumed without FakeAdapterExhausted already proves Elite ran exactly
    # once -- an extra call would have raised.


@pytest.mark.asyncio
@respx.mock
async def test_one_candidate_failure_is_isolated_from_the_others(monkeypatch):
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings")
    now_iso = "2026-09-21T17:00:00+00:00"
    game = _game_row(scheduled_start="2026-09-21T20:00:00+00:00")
    # Two outcomes -> two independent moneyline candidates (KC, BAL):
    odds_rows = [{
        "sportsbook": "draftkings", "market_type": "moneyline",
        "line_data": {"outcomes": [{"name": "KC", "price": -150}, {"name": "BAL", "price": 130}]}, "captured_at": now_iso,
    }]
    _mock_common(game=game, odds_rows=odds_rows, subscribers=[])
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "snap-test-1"}]))

    call_count = {"n": 0}
    real_evaluate = worker_module._evaluate_one_candidate

    async def _flaky_evaluate(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated persistence failure for the first candidate")
        return await real_evaluate(*args, **kwargs)

    monkeypatch.setattr(worker_module, "_evaluate_one_candidate", _flaky_evaluate)
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_agent_output_json(n)) for n in GAME_LEVEL_AGENT_NAMES])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_game_recommendation(
            client, _headers(), game_id="g1", correlation_id="corr-1", prompt_version="v1", agent_version="v1",
            routing_rules=_routing_rules(), adapter_registry=registry, now=datetime.fromisoformat(now_iso),
        )

    assert len(result.candidates) == 2
    statuses = {c.status for c in result.candidates}
    assert statuses == {"failed", "evaluated"}
    failed = next(c for c in result.candidates if c.status == "failed")
    assert "simulated persistence failure" in failed.error


@pytest.mark.asyncio
@respx.mock
async def test_one_subscriber_bankroll_coach_failure_does_not_block_the_next(monkeypatch):
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings")
    now_iso = "2026-09-21T17:00:00+00:00"
    game = _game_row(scheduled_start="2026-09-21T20:00:00+00:00")
    odds_rows = [{
        "sportsbook": "draftkings", "market_type": "moneyline",
        "line_data": {"outcomes": [{"name": "KC", "price": -150}]}, "captured_at": now_iso,
    }]
    subscribers = [
        {"user_id": "u_broken", "tier": "free", "created_at": "2026-08-01T00:00:00+00:00"},
        {"user_id": "u_ok", "tier": "free", "created_at": "2026-08-02T00:00:00+00:00"},
    ]
    _mock_common(game=game, odds_rows=odds_rows, subscribers=subscribers)
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "snap-test-1"}]))

    real_bankroll = worker_module.run_bankroll_coach_evaluation

    async def _flaky_bankroll(*args, **kwargs):
        if kwargs.get("user_id") == "u_broken":
            raise RuntimeError("simulated persistence failure for this user")
        return await real_bankroll(*args, **kwargs)

    monkeypatch.setattr(worker_module, "run_bankroll_coach_evaluation", _flaky_bankroll)

    candidate_key = "g1:draftkings:moneyline:KC:none"
    script = (
        [ScriptedSuccess(raw_text=_agent_output_json(name)) for name in GAME_LEVEL_AGENT_NAMES]
        + [ScriptedSuccess(raw_text=_probability_json(candidate_key, "KC"))]
        + [ScriptedSuccess(raw_text=_agent_output_json("expected_value_agent"))]
        + [ScriptedSuccess(raw_text=_agent_output_json("risk_manager_agent"))]
        + [ScriptedSuccess(raw_text=_meta_json())]
        + [ScriptedSuccess(raw_text=_agent_output_json("bankroll_coach_agent"))]  # only u_ok reaches a real call
    )
    adapter = FakeModelAdapter(provider="anthropic", script=script)
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_game_recommendation(
            client, _headers(), game_id="g1", correlation_id="corr-1", prompt_version="v1", agent_version="v1",
            routing_rules=_routing_rules(), adapter_registry=registry, now=datetime.fromisoformat(now_iso),
        )

    candidate_result = result.candidates[0]
    assert candidate_result.status == "evaluated"
    assert candidate_result.bankroll_coach_user_count == 1  # u_broken's failure isolated, u_ok still counted
