"""Tests for app.persistence.adaptive_weighting (Milestone 5.5) -- the
create-or-correct-or-noop idempotency logic for weighting proposals."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.adaptive_weighting import persist_proposal, persist_proposal_observation

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _proposal_kwargs(**overrides):
    kwargs = dict(
        agent_id="agent-1", previous_weight=1.0, raw_proposed_weight=1.05, guardrail_adjusted_proposed_weight=1.05,
        evaluation_window_start="2026-05-01", evaluation_window_end="2026-08-01", sample_size=210, roi=0.05,
        committee_average_roi=0.0, performance_delta=0.05, learning_rate=0.25, weighting_version="v1",
        status="proposed", rejection_reason=None,
    )
    kwargs.update(overrides)
    return kwargs


@pytest.mark.asyncio
@respx.mock
async def test_persist_proposal_creates_when_no_existing_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(201, json=[{"id": "prop-1"}]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        status, proposal_id = await persist_proposal(client, _headers(), **_proposal_kwargs())
    assert status == "created"
    assert proposal_id == "prop-1"


@pytest.mark.asyncio
@respx.mock
async def test_persist_proposal_is_idempotent_on_retry():
    existing = {"id": "prop-1", "sample_size": 210, "roi": 0.05, "status": "proposed"}
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(200, json=[existing]))
    post_route = respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals")
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        status, proposal_id = await persist_proposal(client, _headers(), **_proposal_kwargs())
    assert status == "unchanged"
    assert proposal_id == "prop-1"
    assert post_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_persist_proposal_inserts_correction_when_evidence_changes():
    existing = {"id": "prop-1", "sample_size": 210, "roi": 0.05, "status": "proposed"}
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(200, json=[existing]))

    import json

    captured = {}

    def _post_responder(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[{"id": "prop-2"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(side_effect=_post_responder)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        status, proposal_id = await persist_proposal(client, _headers(), **_proposal_kwargs(sample_size=225, roi=0.07))

    assert status == "corrected"
    assert proposal_id == "prop-2"
    assert captured["body"]["is_correction"] is True
    assert captured["body"]["corrects_proposal_id"] == "prop-1"
    assert captured["body"]["applied_weight"] is None


@pytest.mark.asyncio
@respx.mock
async def test_persist_proposal_never_sets_applied_weight():
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(200, json=[]))
    import json

    captured = {}

    def _post_responder(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[{"id": "prop-1"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(side_effect=_post_responder)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await persist_proposal(client, _headers(), **_proposal_kwargs())
    assert captured["body"]["applied_weight"] is None


@pytest.mark.asyncio
@respx.mock
async def test_persist_proposal_recovers_from_race_lost_insert():
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(
        side_effect=[
            httpx.Response(200, json=[]),
            httpx.Response(200, json=[{"id": "prop-winner", "sample_size": 210, "roi": 0.05, "status": "proposed"}]),
        ]
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(409, json={"code": "23505"}))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        status, proposal_id = await persist_proposal(client, _headers(), **_proposal_kwargs())
    assert status == "unchanged"
    assert proposal_id == "prop-winner"


@pytest.mark.asyncio
@respx.mock
async def test_persist_proposal_observation_creates():
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposal_observations").mock(
        return_value=httpx.Response(201, json=[{"id": "obs-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        obs_id = await persist_proposal_observation(
            client, _headers(), proposal_id="prop-1", recommendation_leg_grade_event_id="grade-1",
            classification="correct", directional_lean="home", notional_pnl=0.8,
        )
    assert obs_id == "obs-1"
