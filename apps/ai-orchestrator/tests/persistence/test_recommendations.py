"""Tests for app.persistence.recommendations (Milestone 4.5)."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.agents.contract import AgentOutput
from app.persistence.recommendations import (
    AgentConfigError,
    RecommendationsError,
    create_recommendation_cycle,
    persist_agent_output,
    persist_candidate_agent_output,
    resolve_agent,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _output(agent_name: str = "vegas_line_agent", confidence: float = 0.6) -> AgentOutput:
    return AgentOutput(
        agent_name=agent_name,
        finding="finding",
        supporting_evidence=["evidence"],
        evidence_classification="data_backed",
        directional_lean="home",
        confidence=confidence,
        would_change_mind_if="condition",
    )


# --- create_recommendation_cycle: exact fields at creation (Option C / Decision B) ---


@pytest.mark.asyncio
@respx.mock
async def test_create_recommendation_cycle_sends_only_phase4_owned_fields():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(
        return_value=httpx.Response(201, json=[{"id": "r1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        recommendation_id = await create_recommendation_cycle(
            client, _headers(), game_id="g1", prompt_version="v1", agent_version="v1"
        )
    assert recommendation_id == "r1"
    sent = json.loads(route.calls.last.request.content)
    assert sent == {
        "game_id": "g1",
        "prompt_version": "v1",
        "agent_version": "v1",
        "user_facing": False,
        "status": None,
    }
    # Never any Phase-5-owned field:
    for field in ("recommendation_type", "bet_details", "confidence_score", "expected_value", "risk_level", "display_id"):
        assert field not in sent


@pytest.mark.asyncio
@respx.mock
async def test_create_recommendation_cycle_uses_return_representation():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(
        return_value=httpx.Response(201, json=[{"id": "r1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await create_recommendation_cycle(client, _headers(), game_id="g1", prompt_version="v1", agent_version="v1")
    assert route.calls.last.request.headers["Prefer"] == "return=representation"


@pytest.mark.asyncio
@respx.mock
async def test_create_recommendation_cycle_raises_on_error():
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationsError):
            await create_recommendation_cycle(client, _headers(), game_id="g1", prompt_version="v1", agent_version="v1")


@pytest.mark.asyncio
@respx.mock
async def test_create_recommendation_cycle_raises_on_empty_return():
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationsError):
            await create_recommendation_cycle(client, _headers(), game_id="g1", prompt_version="v1", agent_version="v1")


# --- resolve_agent: fail clearly, never silently skip ---


@pytest.mark.asyncio
@respx.mock
async def test_resolve_agent_returns_id_and_weight():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.05}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        agent = await resolve_agent(client, _headers(), agent_name="injury_intelligence_agent")
    assert agent == {"id": "a1", "current_weight": 1.05}


@pytest.mark.asyncio
@respx.mock
async def test_resolve_agent_missing_name_fails_clearly():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(AgentConfigError, match="unknown_agent_slug"):
            await resolve_agent(client, _headers(), agent_name="unknown_agent_slug")


@pytest.mark.asyncio
@respx.mock
async def test_resolve_agent_raises_recommendations_error_on_supabase_failure():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationsError):
            await resolve_agent(client, _headers(), agent_name="injury_intelligence_agent")


# --- persist_agent_output: frozen weight_applied (Decision C) ---


@pytest.mark.asyncio
@respx.mock
async def test_persist_agent_output_sends_frozen_weight_and_confidence():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.05}])
    )
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await persist_agent_output(
            client, _headers(), recommendation_id="r1", agent_name="vegas_line_agent", output=_output(confidence=0.72)
        )
    sent = json.loads(route.calls.last.request.content)
    assert sent["recommendation_id"] == "r1"
    assert sent["agent_id"] == "a1"
    assert sent["agent_confidence"] == 0.72
    assert sent["weight_applied"] == 1.05
    assert sent["raw_output"]["agent_name"] == "vegas_line_agent"


@pytest.mark.asyncio
@respx.mock
async def test_persist_agent_output_weight_reflects_value_at_write_time_not_a_later_change():
    # Two separate calls, two different current_weight values at the
    # moment each is resolved -- proves weight_applied is a frozen copy
    # taken at write time, not re-derived through a later live join.
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        side_effect=[
            httpx.Response(200, json=[{"id": "a1", "current_weight": 1.00}]),
            httpx.Response(200, json=[{"id": "a1", "current_weight": 1.50}]),
        ]
    )
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await persist_agent_output(client, _headers(), recommendation_id="r1", agent_name="vegas_line_agent", output=_output())
        await persist_agent_output(client, _headers(), recommendation_id="r2", agent_name="vegas_line_agent", output=_output())
    first_sent = json.loads(route.calls[0].request.content)
    second_sent = json.loads(route.calls[1].request.content)
    assert first_sent["weight_applied"] == 1.00
    assert second_sent["weight_applied"] == 1.50  # agents.current_weight changed between calls, each output kept its own


@pytest.mark.asyncio
@respx.mock
async def test_persist_agent_output_missing_agent_fails_clearly_not_silently_skipped():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(AgentConfigError):
            await persist_agent_output(
                client, _headers(), recommendation_id="r1", agent_name="nonexistent_agent", output=_output()
            )


@pytest.mark.asyncio
@respx.mock
async def test_persist_agent_output_raises_on_insert_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationsError):
            await persist_agent_output(
                client, _headers(), recommendation_id="r1", agent_name="vegas_line_agent", output=_output()
            )


# --- persist_candidate_agent_output: candidate_key is first-class (Milestone 4.6, Decision G) ---


@pytest.mark.asyncio
@respx.mock
async def test_persist_candidate_agent_output_sends_candidate_key_as_a_column():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}])
    )
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await persist_candidate_agent_output(
            client,
            _headers(),
            recommendation_id="r1",
            agent_name="probability_modeling_agent",
            candidate_key="g1:DraftKings:moneyline:KC:none",
            raw_output={"probability_output": {"modeled_probability": 0.57}},
            agent_confidence=0.72,
        )
    sent = json.loads(route.calls.last.request.content)
    assert sent["candidate_key"] == "g1:DraftKings:moneyline:KC:none"
    assert sent["recommendation_id"] == "r1"
    assert sent["agent_id"] == "a1"
    assert sent["agent_confidence"] == 0.72
    assert sent["weight_applied"] == 1.0
    assert sent["raw_output"] == {"probability_output": {"modeled_probability": 0.57}}


@pytest.mark.asyncio
@respx.mock
async def test_persist_candidate_agent_output_preserves_composed_deterministic_payload():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}])
    )
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    raw_output = {
        "agent_output": {"agent_name": "expected_value_agent", "confidence": 0.6},
        "deterministic": {"decimal_odds": 1.8, "ev_per_dollar": 0.026},
    }
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await persist_candidate_agent_output(
            client,
            _headers(),
            recommendation_id="r1",
            agent_name="expected_value_agent",
            candidate_key="g1:DraftKings:moneyline:KC:none",
            raw_output=raw_output,
            agent_confidence=0.6,
        )
    sent = json.loads(route.calls.last.request.content)
    assert sent["raw_output"]["agent_output"]["agent_name"] == "expected_value_agent"
    assert sent["raw_output"]["deterministic"]["ev_per_dollar"] == 0.026


@pytest.mark.asyncio
@respx.mock
async def test_persist_candidate_agent_output_missing_agent_fails_clearly():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(AgentConfigError):
            await persist_candidate_agent_output(
                client,
                _headers(),
                recommendation_id="r1",
                agent_name="nonexistent_agent",
                candidate_key="g1:DraftKings:moneyline:KC:none",
                raw_output={},
                agent_confidence=0.5,
            )


@pytest.mark.asyncio
@respx.mock
async def test_persist_candidate_agent_output_raises_on_insert_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationsError):
            await persist_candidate_agent_output(
                client,
                _headers(),
                recommendation_id="r1",
                agent_name="probability_modeling_agent",
                candidate_key="g1:DraftKings:moneyline:KC:none",
                raw_output={},
                agent_confidence=0.5,
            )
