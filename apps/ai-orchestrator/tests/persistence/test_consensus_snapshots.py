"""Tests for app.persistence.consensus_snapshots (Milestone 4.7)."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.persistence.consensus_snapshots import (
    ConsensusSnapshotsError,
    persist_consensus_snapshot,
    read_game_level_agent_outputs,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


# --- read_game_level_agent_outputs ---


@pytest.mark.asyncio
@respx.mock
async def test_read_game_level_agent_outputs_flattens_embedded_agent():
    row = {
        "raw_output": {
            "agent_name": "injury_intelligence_agent",
            "finding": "finding",
            "directional_lean": "home",
            "evidence_classification": "data_backed",
        },
        "agent_confidence": 0.6,
        "weight_applied": 1.05,
        "agents": {"name": "injury_intelligence_agent", "category": "context"},
    }
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=[row]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_game_level_agent_outputs(client, _headers(), recommendation_id="r1")
    assert result == [
        {
            "agent_name": "injury_intelligence_agent",
            "category": "context",
            "finding": "finding",
            "confidence": 0.6,
            "directional_lean": "home",
            "evidence_classification": "data_backed",
            "weight_applied": 1.05,
        }
    ]


@pytest.mark.asyncio
@respx.mock
async def test_read_game_level_agent_outputs_filters_candidate_key_is_null():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await read_game_level_agent_outputs(client, _headers(), recommendation_id="r1")
    assert route.calls.last.request.url.params["candidate_key"] == "is.null"


@pytest.mark.asyncio
@respx.mock
async def test_read_game_level_agent_outputs_empty_list_when_none():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_game_level_agent_outputs(client, _headers(), recommendation_id="r1")
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_read_game_level_agent_outputs_raises_on_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ConsensusSnapshotsError):
            await read_game_level_agent_outputs(client, _headers(), recommendation_id="r1")


# --- persist_consensus_snapshot ---


@pytest.mark.asyncio
@respx.mock
async def test_persist_consensus_snapshot_sends_all_fields():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(
        return_value=httpx.Response(201, json=[{"id": "snap-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        snapshot_id = await persist_consensus_snapshot(
            client,
            _headers(),
            recommendation_id="r1",
            candidate_key="g1:DraftKings:moneyline:KC:none",
            aggregate_confidence=0.596,
            final_aggregate_confidence=0.55,
            agreement_variance=0.1225,
            below_confidence_floor=False,
            participation_metadata={"fan_out_status": "full"},
            model_routing_used={"meta_agent": "claude-sonnet-5"},
            second_pass_triggered=False,
        )
    assert snapshot_id == "snap-1"
    assert route.calls.last.request.headers["Prefer"] == "return=representation"
    sent = json.loads(route.calls.last.request.content)
    assert sent["recommendation_id"] == "r1"
    assert sent["candidate_key"] == "g1:DraftKings:moneyline:KC:none"
    assert sent["aggregate_confidence"] == 0.596
    assert sent["final_aggregate_confidence"] == 0.55
    assert sent["agreement_variance"] == 0.1225
    assert sent["below_confidence_floor"] is False
    assert sent["participation_metadata"] == {"fan_out_status": "full"}
    assert sent["second_pass_triggered"] is False


@pytest.mark.asyncio
@respx.mock
async def test_persist_consensus_snapshot_raises_on_error():
    respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ConsensusSnapshotsError):
            await persist_consensus_snapshot(
                client,
                _headers(),
                recommendation_id="r1",
                candidate_key="key",
                aggregate_confidence=0.6,
                final_aggregate_confidence=0.6,
                agreement_variance=0.0,
                below_confidence_floor=False,
                participation_metadata={},
                model_routing_used={},
                second_pass_triggered=False,
            )
