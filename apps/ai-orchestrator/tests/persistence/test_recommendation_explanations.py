"""Tests for app.persistence.recommendation_explanations (Milestone 5.2)."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.persistence.recommendation_explanations import (
    RecommendationExplanationsError,
    persist_leg_explanation,
    persist_product_explanation,
    read_candidate_level_agent_output,
    read_legs_for_product,
    read_participation_metadata,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


# --- read_candidate_level_agent_output ---


@pytest.mark.asyncio
@respx.mock
async def test_read_candidate_level_agent_output_filters_by_agent_name():
    rows = [
        {"raw_output": {"deterministic": {"bernoulli_outcome_variance": 0.1}}, "agents": {"name": "expected_value_agent"}},
        {"raw_output": {"deterministic": {"bernoulli_outcome_variance": 0.24}}, "agents": {"name": "risk_manager_agent"}},
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=rows))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_candidate_level_agent_output(
            client, _headers(), recommendation_id="r1", candidate_key="ck", agent_name="risk_manager_agent"
        )
    assert result == {"deterministic": {"bernoulli_outcome_variance": 0.24}}


@pytest.mark.asyncio
@respx.mock
async def test_read_candidate_level_agent_output_none_when_agent_never_participated():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_candidate_level_agent_output(
            client, _headers(), recommendation_id="r1", candidate_key="ck", agent_name="risk_manager_agent"
        )
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_read_candidate_level_agent_output_raises_on_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationExplanationsError):
            await read_candidate_level_agent_output(
                client, _headers(), recommendation_id="r1", candidate_key="ck", agent_name="risk_manager_agent"
            )


# --- read_legs_for_product ---


@pytest.mark.asyncio
@respx.mock
async def test_read_legs_for_product_returns_id_and_candidate_key():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": "ck-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_legs_for_product(client, _headers(), recommendation_product_id="prod-1")
    assert result == [{"id": "leg-1", "candidate_key": "ck-1"}]


@pytest.mark.asyncio
@respx.mock
async def test_read_legs_for_product_raises_on_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationExplanationsError):
            await read_legs_for_product(client, _headers(), recommendation_product_id="prod-1")


# --- read_participation_metadata ---


@pytest.mark.asyncio
@respx.mock
async def test_read_participation_metadata_returns_first_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(
        return_value=httpx.Response(200, json=[{"participation_metadata": {"fan_out_status": "full"}}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_participation_metadata(client, _headers(), recommendation_id="r1")
    assert result == {"fan_out_status": "full"}


@pytest.mark.asyncio
@respx.mock
async def test_read_participation_metadata_none_when_no_snapshot_exists():
    respx.get(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_participation_metadata(client, _headers(), recommendation_id="r1")
    assert result is None


# --- persist_product_explanation ---


@pytest.mark.asyncio
@respx.mock
async def test_persist_product_explanation_sends_all_fields_and_returns_id():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(201, json=[{"id": "expl-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        explanation_id = await persist_product_explanation(
            client,
            _headers(),
            recommendation_product_id="prod-1",
            why_this_shape="shape reason",
            why_not_other_shapes="not other reason",
            rejected_alternatives=[{"candidate_key": "ck"}],
            data_limitations="limitations",
            explainability_version="v1",
        )
    assert explanation_id == "expl-1"
    sent = json.loads(route.calls.last.request.content)
    assert sent["recommendation_product_id"] == "prod-1"
    assert sent["why_this_shape"] == "shape reason"
    assert sent["rejected_alternatives"] == [{"candidate_key": "ck"}]
    assert sent["explainability_version"] == "v1"
    assert "narrative_summary" not in sent


@pytest.mark.asyncio
@respx.mock
async def test_persist_product_explanation_raises_on_error():
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(500, text="db error")
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationExplanationsError):
            await persist_product_explanation(
                client,
                _headers(),
                recommendation_product_id="prod-1",
                why_this_shape="x",
                why_not_other_shapes=None,
                rejected_alternatives=[],
                data_limitations=None,
                explainability_version="v1",
            )


# --- persist_leg_explanation ---


@pytest.mark.asyncio
@respx.mock
async def test_persist_leg_explanation_sends_all_fields_and_returns_id():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(
        return_value=httpx.Response(201, json=[{"id": "leg-expl-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        explanation_id = await persist_leg_explanation(
            client,
            _headers(),
            recommendation_leg_id="leg-1",
            why_selected="selected reason",
            strongest_evidence="evidence",
            contributing_agents=[{"agent_name": "a"}],
            biggest_risks="risks",
            rejected_alternatives=[],
            would_change_mind_if=None,
            explainability_version="v1",
        )
    assert explanation_id == "leg-expl-1"
    sent = json.loads(route.calls.last.request.content)
    assert sent["recommendation_leg_id"] == "leg-1"
    assert sent["contributing_agents"] == [{"agent_name": "a"}]
    assert sent["would_change_mind_if"] is None
    assert sent["explainability_version"] == "v1"


@pytest.mark.asyncio
@respx.mock
async def test_persist_leg_explanation_raises_on_error():
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(
        return_value=httpx.Response(500, text="db error")
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationExplanationsError):
            await persist_leg_explanation(
                client,
                _headers(),
                recommendation_leg_id="leg-1",
                why_selected="x",
                strongest_evidence="x",
                contributing_agents=[],
                biggest_risks="x",
                rejected_alternatives=[],
                would_change_mind_if=None,
                explainability_version="v1",
            )
