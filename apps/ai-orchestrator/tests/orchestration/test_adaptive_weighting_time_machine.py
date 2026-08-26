"""Milestone 5.5, Decision 23 -- the roadmap's own named-pattern proof,
extended: creating a weight proposal cannot change any historical
`recommendation_agent_outputs`/`consensus_snapshots`/
`recommendation_products`/`recommendation_legs`/explanation/activation-
snapshot/grade-event/postgame-review record. Proven directly: every one
of those tables is only ever READ (GET) during evaluation, never
written (POST/PATCH/PUT/DELETE) -- confirmed by asserting zero write
calls landed on any of their REST endpoints."""
from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from app.orchestration.adaptive_weighting import evaluate_committee

SUPABASE_URL = "https://test-project.supabase.co"

_HISTORICAL_TABLES = [
    "recommendation_agent_outputs",
    "consensus_snapshots",
    "recommendation_products",
    "recommendation_legs",
    "recommendation_product_explanations",
    "recommendation_leg_explanations",
    "recommendation_activation_snapshots",
    "recommendation_activation_snapshot_legs",
    "recommendation_activation_snapshot_source_products",
    "recommendation_leg_grade_events",
    "recommendation_product_grade_events",
    "recommendation_product_postgame_reviews",
    "agents",
]


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_evaluation_never_writes_to_any_historical_table():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "agent-1", "name": "sharp_money_agent", "category": "market", "current_weight": "1.0"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "grade-1", "recommendation_leg_id": "leg-1", "game_id": "game-1", "outcome": "WIN", "created_at": "2026-07-01T00:00:00Z"}],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "leg-1", "market_type": "moneyline", "selection": "KC", "point": None, "decimal_odds": 1.8, "game_id": "game-1", "recommendation_id": "rec-1"}],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "game-1", "status": "final", "home_team": "KC", "away_team": "BAL", "final_score": {"home": 27, "away": 24}, "finalized_at": "2026-07-01T00:00:00Z"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "raw_output": {"agent_name": "sharp_money_agent", "directional_lean": "home", "evidence_classification": "supporting"},
                    "agent_confidence": 0.7, "weight_applied": 1.0, "agents": {"name": "sharp_money_agent", "category": "market"},
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposals").mock(return_value=httpx.Response(201, json=[{"id": "prop-1"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/adaptive_weight_proposal_observations").mock(return_value=httpx.Response(201, json=[{"id": "obs-1"}]))

    write_routes = []
    for table in _HISTORICAL_TABLES:
        for method in ("post", "patch", "put", "delete"):
            write_routes.append(getattr(respx, method)(f"{SUPABASE_URL}/rest/v1/{table}"))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await evaluate_committee(client, _headers(), evaluation_window_start=date(2026, 5, 1), evaluation_window_end=date(2026, 8, 1))

    for route in write_routes:
        assert route.call_count == 0, f"unexpected write to a historical table: {route}"
