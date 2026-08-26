"""Tests for app.orchestration.adaptive_weighting (Milestone 5.5) --
committee-wide evaluation: window guardrail, sample-size guardrail,
evidence gathering/classification, idempotency, and the hard requirement
that `agents.current_weight` is never touched."""
from __future__ import annotations

import json
from datetime import date

import httpx
import pytest
import respx

from app.features.adaptive_weighting import ADAPTIVE_WEIGHT_MIN_SAMPLE_SIZE, EvaluationWindowTooShortError
from app.orchestration.adaptive_weighting import evaluate_committee

SUPABASE_URL = "https://test-project.supabase.co"

_AGENT = {"id": "agent-1", "name": "sharp_money_agent", "category": "market", "current_weight": "1.0000"}


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _mock_no_evidence(agents: list[dict] | None = None):
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=agents if agents is not None else [_AGENT]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": "prop-x"}])
    )


@pytest.mark.asyncio
@respx.mock
async def test_window_shorter_than_90_days_is_rejected_before_any_read():
    agents_route = respx.get(f"{SUPABASE_URL}/rest/v1/agents")
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(EvaluationWindowTooShortError):
            await evaluate_committee(
                client, _headers(), evaluation_window_start=date(2026, 6, 1), evaluation_window_end=date(2026, 8, 1)
            )
    assert agents_route.call_count == 0  # nothing read, nothing computed, nothing persisted


@pytest.mark.asyncio
@respx.mock
async def test_zero_evidence_rejects_every_agent_as_insufficient_sample():
    _mock_no_evidence()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await evaluate_committee(
            client, _headers(), evaluation_window_start=date(2026, 5, 1), evaluation_window_end=date(2026, 8, 1)
        )
    assert result.agents[0].proposal_status == "rejected_insufficient_sample"
    assert result.agents[0].sample_size == 0
    assert result.committee_average_roi is None


def _leg_grade_event(*, id_, leg_id, outcome, created_at):
    return {"id": id_, "recommendation_leg_id": leg_id, "game_id": "game-1", "outcome": outcome, "created_at": created_at}


def _leg(*, id_, decimal_odds=1.8):
    return {
        "id": id_, "market_type": "moneyline", "selection": "KC", "point": None,
        "decimal_odds": decimal_odds, "game_id": "game-1", "recommendation_id": "rec-1",
    }


def _game_level_output(*, agent_name, lean):
    return [
        {
            "raw_output": {"agent_name": agent_name, "directional_lean": lean, "evidence_classification": "supporting"},
            "agent_confidence": 0.7, "weight_applied": 1.0, "agents": {"name": agent_name, "category": "market"},
        }
    ]


@pytest.mark.asyncio
@respx.mock
async def test_below_199_observations_rejects_but_199_still_yields_metrics():
    """199 valid observations -> no eligible proposal (Decision 24's own
    named boundary case)."""
    n = ADAPTIVE_WEIGHT_MIN_SAMPLE_SIZE - 1
    events = [_leg_grade_event(id_=f"grade-{i}", leg_id=f"leg-{i}", outcome="WIN", created_at="2026-07-01T00:00:00Z") for i in range(n)]
    legs = [_leg(id_=f"leg-{i}") for i in range(n)]

    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[_AGENT]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=events))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=legs))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "game-1", "status": "final", "home_team": "KC", "away_team": "BAL", "final_score": {"home": 27, "away": 24}, "finalized_at": "2026-07-01T00:00:00Z"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(200, json=_game_level_output(agent_name="sharp_money_agent", lean="home"))
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(201, json=[{"id": "prop-1"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposal_observations").mock(return_value=httpx.Response(201, json=[{"id": "obs-1"}]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await evaluate_committee(
            client, _headers(), evaluation_window_start=date(2026, 5, 1), evaluation_window_end=date(2026, 8, 1)
        )

    agent_result = result.agents[0]
    assert agent_result.sample_size == n
    assert agent_result.proposal_status == "rejected_insufficient_sample"


@pytest.mark.asyncio
@respx.mock
async def test_200_observations_meets_sample_guardrail_and_computes_weight():
    n = ADAPTIVE_WEIGHT_MIN_SAMPLE_SIZE
    events = [_leg_grade_event(id_=f"grade-{i}", leg_id=f"leg-{i}", outcome="WIN", created_at="2026-07-01T00:00:00Z") for i in range(n)]
    legs = [_leg(id_=f"leg-{i}") for i in range(n)]

    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[_AGENT]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=events))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=legs))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "game-1", "status": "final", "home_team": "KC", "away_team": "BAL", "final_score": {"home": 27, "away": 24}, "finalized_at": "2026-07-01T00:00:00Z"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(200, json=_game_level_output(agent_name="sharp_money_agent", lean="home"))
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(200, json=[]))
    captured = {}

    def _post_responder(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[{"id": "prop-1"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(side_effect=_post_responder)
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposal_observations").mock(return_value=httpx.Response(201, json=[{"id": "obs-1"}]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await evaluate_committee(
            client, _headers(), evaluation_window_start=date(2026, 5, 1), evaluation_window_end=date(2026, 8, 1)
        )

    agent_result = result.agents[0]
    assert agent_result.sample_size == n
    assert agent_result.proposal_status == "proposed"
    assert captured["body"]["status"] == "proposed"
    assert captured["body"]["applied_weight"] is None
    assert captured["body"]["learning_rate"] == 0.25
    # KC (home) always wins (27-24) -> agent leaning "home" is correct every
    # time -> agent ROI == committee ROI (only agent) -> performance_delta == 0
    # -> raw_proposed_weight == previous_weight.
    assert captured["body"]["performance_delta"] == pytest.approx(0.0)
    assert captured["body"]["guardrail_adjusted_proposed_weight"] == pytest.approx(1.0)


@pytest.mark.asyncio
@respx.mock
async def test_failed_agent_output_does_not_count():
    """An agent with zero recommendation_agent_outputs rows (i.e. it
    failed every cycle) never appears in the game-level output rows at
    all -- confirmed it accumulates sample_size=0, never fabricated."""
    _mock_no_evidence(agents=[{"id": "agent-2", "name": "never_succeeded_agent", "category": "context", "current_weight": "1.0"}])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await evaluate_committee(
            client, _headers(), evaluation_window_start=date(2026, 5, 1), evaluation_window_end=date(2026, 8, 1)
        )
    assert result.agents[0].sample_size == 0


@pytest.mark.asyncio
@respx.mock
async def test_abstention_and_off_axis_do_not_count():
    events = [_leg_grade_event(id_="grade-1", leg_id="leg-1", outcome="WIN", created_at="2026-07-01T00:00:00Z")]
    legs = [_leg(id_="leg-1")]
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[_AGENT]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=events))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=legs))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "game-1", "status": "final", "home_team": "KC", "away_team": "BAL", "final_score": {"home": 27, "away": 24}, "finalized_at": "2026-07-01T00:00:00Z"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(200, json=_game_level_output(agent_name="sharp_money_agent", lean="none"))
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(201, json=[{"id": "prop-1"}]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await evaluate_committee(
            client, _headers(), evaluation_window_start=date(2026, 5, 1), evaluation_window_end=date(2026, 8, 1)
        )
    assert result.agents[0].sample_size == 0


@pytest.mark.asyncio
@respx.mock
async def test_evaluation_never_touches_agents_current_weight():
    """Proposal generation never issues a PATCH/PUT/write of any kind to
    /rest/v1/agents -- only a GET."""
    _mock_no_evidence()
    agents_writes = respx.patch(f"{SUPABASE_URL}/rest/v1/agents")
    agents_posts = respx.post(f"{SUPABASE_URL}/rest/v1/agents")
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await evaluate_committee(client, _headers(), evaluation_window_start=date(2026, 5, 1), evaluation_window_end=date(2026, 8, 1))
    assert agents_writes.call_count == 0
    assert agents_posts.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_repeated_evaluation_with_identical_evidence_is_idempotent():
    _AGENT_LOCAL = dict(_AGENT)
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[_AGENT_LOCAL]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(
        return_value=httpx.Response(200, json=[{"id": "prop-existing", "sample_size": 0, "roi": None, "status": "rejected_insufficient_sample"}])
    )
    post_route = respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await evaluate_committee(
            client, _headers(), evaluation_window_start=date(2026, 5, 1), evaluation_window_end=date(2026, 8, 1)
        )
    assert result.agents[0].status == "unchanged"
    assert post_route.call_count == 0
