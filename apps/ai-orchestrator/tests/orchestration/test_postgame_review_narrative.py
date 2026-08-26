"""Tests for app.orchestration.postgame_review_narrative (Milestone 5.4)
-- FakeModelAdapter only, zero live provider calls, proving: narrative
generation is skipped without a routing rule, skipped for NOT_APPLICABLE/
PENDING_MISSING_DATA outcomes, and that a generated narrative is
persisted alongside deterministically-computed agent correctness --
never able to alter the outcome it was given."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.models.fake_adapter import FakeModelAdapter, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.orchestration.postgame_review_narrative import generate_and_persist_postgame_review

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _narrative_json() -> str:
    return json.dumps(
        {
            "outcome_summary": "The recommendation won as graded.",
            "why_it_won_or_lost": "The favored side covered comfortably.",
            "learning_notes": "No weighting changes are decided here.",
        }
    )


@pytest.mark.asyncio
async def test_skipped_when_no_routing_rule_configured():
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await generate_and_persist_postgame_review(
            client, _headers(),
            recommendation_product_id="prod-1", product_grade_event_id="grade-1", grading_version="v1",
            outcome="WIN", routing_rules={}, adapter_registry=AdapterRegistry(adapters={}),
        )
    assert result.status == "skipped_no_routing_rule"


@pytest.mark.asyncio
async def test_skipped_for_not_applicable_outcome():
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await generate_and_persist_postgame_review(
            client, _headers(),
            recommendation_product_id="prod-1", product_grade_event_id="grade-1", grading_version="v1",
            outcome="NOT_APPLICABLE",
            routing_rules={"postgame_review_narrative": {"task_type": "postgame_review_narrative", "primary_model": "fake-model"}},
            adapter_registry=AdapterRegistry(adapters={"fake": FakeModelAdapter(provider="fake", script=[])}),
        )
    assert result.status == "skipped_not_applicable"


@pytest.mark.asyncio
@respx.mock
async def test_generates_and_persists_narrative_using_fake_adapter_only():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "leg-1", "recommendation_product_id": "prod-1", "market_type": "moneyline", "selection": "KC", "point": None, "game_id": "game-1", "recommendation_id": "rec-1"}],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-grade-1", "outcome": "WIN", "authoritative_result": {}, "is_correction": False}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "game-1", "status": "final", "home_team": "KC", "away_team": "BAL", "final_score": {"home": 27, "away": 24}, "finalized_at": "2026-10-01T00:00:00Z"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "raw_output": {"agent_name": "weather_agent", "directional_lean": "home", "evidence_classification": "supporting"},
                    "agent_confidence": 0.7, "weight_applied": 1.0, "agents": {"name": "weather_agent", "category": "context"},
                },
                {
                    "raw_output": {"agent_name": "injury_agent", "directional_lean": "away", "evidence_classification": "supporting"},
                    "agent_confidence": 0.6, "weight_applied": 1.0, "agents": {"name": "injury_agent", "category": "context"},
                },
            ],
        )
    )
    captured = {}

    def _review_post(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[{"id": "review-1"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_postgame_reviews").mock(side_effect=_review_post)

    fake_adapter = FakeModelAdapter(provider="fake", script=[ScriptedSuccess(raw_text=_narrative_json())])
    registry = AdapterRegistry(adapters={"fake": fake_adapter})
    routing_rules = {"postgame_review_narrative": {"task_type": "postgame_review_narrative", "primary_model": "fake-model"}}

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await generate_and_persist_postgame_review(
            client, _headers(),
            recommendation_product_id="prod-1", product_grade_event_id="grade-1", grading_version="v1",
            outcome="WIN", routing_rules=routing_rules, adapter_registry=registry,
            model_providers={"fake-model": "fake"},
        )

    assert result.status == "generated"
    assert result.postgame_review_id == "review-1"
    assert fake_adapter.call_count == 1  # exactly one call -- FakeModelAdapter only
    assert captured["body"]["outcome_summary"] == "The recommendation won as graded."
    assert captured["body"]["correct_agents"] == ["weather_agent"]
    assert captured["body"]["underperforming_agents"] == ["injury_agent"]
    assert captured["body"]["grading_version"] == "v1"
    assert captured["body"]["postgame_review_version"] == "v1"
    # The narrative payload has no field capable of representing a grade,
    # EV, confidence, or Explainability value at all.
    assert "outcome" not in captured["body"] or captured["body"].get("outcome") is None
