"""Tests for app.orchestration.cycle.run_candidate_evaluation and
run_bankroll_coach_evaluation (Milestone 4.6, Decision G; split in
Milestone 4.9, Decision 2): the sequential Decision & Advisory chain for
one `MarketCandidate` against an already-existing `recommendation_id` --
never creates a second `recommendations` row, tags every persisted row
with `candidate_key`. `run_candidate_evaluation` is the shared,
user-independent half (Probability -> EV -> Risk); `run_bankroll_coach_
evaluation` is the separate per-user half."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.agents.committee_context import ParticipationMetadata
from app.agents.probability_modeling import ProbabilityModelingAgent
from app.context_intelligence.context_package import ContextPackage
from app.features.candidate import MarketCandidate
from app.models.errors import ModelTimeoutError
from app.models.fake_adapter import FakeModelAdapter, ScriptedFailure, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.orchestration.cycle import run_bankroll_coach_evaluation, run_candidate_evaluation
from tests.conftest import mock_prompt_registry_route

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _candidate() -> MarketCandidate:
    return MarketCandidate(
        game_id="g1",
        sportsbook="DraftKings",
        market_type="moneyline",
        selection="Kansas City Chiefs",
        american_odds=-125,
        point=None,
        observed_at=datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc),
    )


def _participation() -> ParticipationMetadata:
    return ParticipationMetadata(
        configured_agents=frozenset({"injury_intelligence_agent"}),
        built_agents=frozenset({"injury_intelligence_agent"}),
        deferred_agents=frozenset(),
        attempted_agents=frozenset({"injury_intelligence_agent"}),
        successful_agents=frozenset({"injury_intelligence_agent"}),
        failed_agents=frozenset(),
        fan_out_status="full",
        committee_completeness=1.0,
    )


def _routing_rules() -> dict[str, dict]:
    task_types = [
        "probability_modeling_analysis",
        "expected_value_analysis",
        "risk_manager_analysis",
        "bankroll_coach_analysis",
    ]
    return {t: {"task_type": t, "primary_model": "claude-sonnet-5", "fallback_model": None} for t in task_types}


def _valid_probability_json() -> str:
    return json.dumps(
        {
            "agent_name": "probability_modeling_agent",
            "candidate_key": "g1:DraftKings:moneyline:Kansas City Chiefs:none",
            "selection": "Kansas City Chiefs",
            "modeled_probability": 0.57,
            "confidence_in_probability": 0.72,
            "reasoning": "reasoning",
            "supporting_evidence": [],
            "would_change_mind_if": "x",
        }
    )


def _valid_agent_output_json(agent_name: str) -> str:
    return json.dumps(
        {
            "agent_name": agent_name,
            "finding": "finding",
            "supporting_evidence": [],
            "evidence_classification": "data_backed",
            "directional_lean": "home",
            "confidence": 0.6,
            "would_change_mind_if": "x",
        }
    )


def _mock_agents():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
    mock_prompt_registry_route(SUPABASE_URL)


def _shared_chain_adapter() -> FakeModelAdapter:
    return FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_valid_probability_json()),
            ScriptedSuccess(raw_text=_valid_agent_output_json("expected_value_agent")),
            ScriptedSuccess(raw_text=_valid_agent_output_json("risk_manager_agent")),
        ],
    )


# --- run_candidate_evaluation: shared, user-independent half ---


@pytest.mark.asyncio
@respx.mock
async def test_run_candidate_evaluation_persists_one_row_per_successful_step_tagged_with_candidate_key():
    _mock_agents()
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    registry = AdapterRegistry(adapters={"anthropic": _shared_chain_adapter()})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=registry,
        )

    assert chain_result.status == "full"
    assert output_route.call_count == 3  # Probability, EV, Risk -- no Bankroll Coach here
    expected_key = "g1:DraftKings:moneyline:Kansas City Chiefs:none"
    for call in output_route.calls:
        sent = json.loads(call.request.content)
        assert sent["recommendation_id"] == "r1"
        assert sent["candidate_key"] == expected_key


@pytest.mark.asyncio
@respx.mock
async def test_run_candidate_evaluation_never_creates_a_recommendations_row():
    _mock_agents()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    recommendations_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "should-not-be-called"}]))
    registry = AdapterRegistry(adapters={"anthropic": _shared_chain_adapter()})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=registry,
        )

    assert recommendations_route.call_count == 0  # the SAME existing recommendation_id is reused, never a second row


@pytest.mark.asyncio
@respx.mock
async def test_run_candidate_evaluation_has_no_user_concept_and_never_reads_user_profiles():
    _mock_agents()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    profile_route = respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(return_value=httpx.Response(200, json=[]))
    registry = AdapterRegistry(adapters={"anthropic": _shared_chain_adapter()})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=registry,
        )

    assert profile_route.call_count == 0
    assert chain_result.context.kelly is None  # no bankroll/Kelly concept at all in the shared chain


@pytest.mark.asyncio
@respx.mock
async def test_probability_modeling_failure_persists_nothing():
    _mock_agents()
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedFailure(error=ModelTimeoutError("t1")), ScriptedFailure(error=ModelTimeoutError("t2"))],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=registry,
        )

    assert chain_result.status == "failed"
    assert output_route.call_count == 0


# --- run_bankroll_coach_evaluation: separate, per-user half ---


@pytest.mark.asyncio
@respx.mock
async def test_run_bankroll_coach_evaluation_persists_one_row_tagged_with_candidate_key():
    _mock_agents()
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    shared_registry = AdapterRegistry(adapters={"anthropic": _shared_chain_adapter()})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=shared_registry,
        )
        assert output_route.call_count == 3

        bankroll_adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_valid_agent_output_json("bankroll_coach_agent"))])
        result = await run_bankroll_coach_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            candidate=_candidate(),
            shared_chain_context=chain_result.context,
            routing_rule=_routing_rules()["bankroll_coach_analysis"],
            adapter_registry=AdapterRegistry(adapters={"anthropic": bankroll_adapter}),
        )

    assert result.status == "success"
    assert output_route.call_count == 4  # 3 shared + 1 bankroll coach
    last_call = output_route.calls[-1]
    sent = json.loads(last_call.request.content)
    assert sent["recommendation_id"] == "r1"
    assert sent["candidate_key"] == "g1:DraftKings:moneyline:Kansas City Chiefs:none"


@pytest.mark.asyncio
@respx.mock
async def test_run_bankroll_coach_evaluation_without_user_id_never_reads_user_profiles_and_yields_null_stake():
    _mock_agents()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    profile_route = respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(return_value=httpx.Response(200, json=[]))
    shared_registry = AdapterRegistry(adapters={"anthropic": _shared_chain_adapter()})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=shared_registry,
        )

        bankroll_adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_valid_agent_output_json("bankroll_coach_agent"))])
        result = await run_bankroll_coach_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            candidate=_candidate(),
            shared_chain_context=chain_result.context,
            routing_rule=_routing_rules()["bankroll_coach_analysis"],
            adapter_registry=AdapterRegistry(adapters={"anthropic": bankroll_adapter}),
        )

    assert profile_route.call_count == 0  # user_id omitted entirely -- never fabricated
    assert result.status == "success"
    assert result.kelly.stake is None


@pytest.mark.asyncio
@respx.mock
async def test_run_bankroll_coach_evaluation_with_user_id_reads_real_profile_and_uses_it():
    _mock_agents()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(
        return_value=httpx.Response(200, json=[{"id": "u1", "risk_tolerance": "moderate", "preferred_unit_size": 25.0, "optional_bankroll": 1000.0}])
    )
    shared_registry = AdapterRegistry(adapters={"anthropic": _shared_chain_adapter()})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=shared_registry,
        )

        bankroll_adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_valid_agent_output_json("bankroll_coach_agent"))])
        result = await run_bankroll_coach_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            candidate=_candidate(),
            shared_chain_context=chain_result.context,
            routing_rule=_routing_rules()["bankroll_coach_analysis"],
            adapter_registry=AdapterRegistry(adapters={"anthropic": bankroll_adapter}),
            user_id="u1",
        )

    assert result.status == "success"
    assert result.kelly.stake is not None  # a real (synthetic-for-this-test) complete profile -> a valid stake


@pytest.mark.asyncio
@respx.mock
async def test_run_bankroll_coach_evaluation_skipped_when_shared_chain_never_reached_a_probability():
    _mock_agents()
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    failing_registry = AdapterRegistry(
        adapters={"anthropic": FakeModelAdapter(provider="anthropic", script=[ScriptedFailure(error=ModelTimeoutError("t1")), ScriptedFailure(error=ModelTimeoutError("t2"))])}
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=failing_registry,
        )
        assert chain_result.status == "failed"

        result = await run_bankroll_coach_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            candidate=_candidate(),
            shared_chain_context=chain_result.context,
            routing_rule=_routing_rules()["bankroll_coach_analysis"],
            adapter_registry=AdapterRegistry(adapters={}),
        )

    assert result.status == "skipped_no_probability"
    assert output_route.call_count == 0  # never persisted -- nothing ran


# --------------------------------------------------------------------------
# Live Context Package Orchestration (2026-09-15, HQ-authorized "MANSA --
# PHASE 8 LIVE CONTEXT PACKAGE ORCHESTRATION") -- run_candidate_evaluation
# now attaches one real ContextPackage per candidate via the existing,
# unmodified Context Intelligence engine, additively and failure-isolated.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_context_package_construction_failure_does_not_fail_candidate_evaluation():
    """No Context Intelligence boundary mocked at all -- _attach_context_
    package's own real Supabase reads hit respx's unmocked-request error,
    caught and logged, degrading to context_package=None. The rest of the
    chain must run exactly as if this pass never existed."""
    _mock_agents()
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    registry = AdapterRegistry(adapters={"anthropic": _shared_chain_adapter()})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client, _headers(), recommendation_id="r1", game_id="g1", correlation_id="corr-1",
            candidate=_candidate(), upstream_outputs=(), participation=_participation(),
            routing_rules=_routing_rules(), adapter_registry=registry,
        )

    assert chain_result.status == "full"  # unaffected
    assert output_route.call_count == 3  # unaffected -- Probability, EV, Risk still persist
    assert chain_result.context.context_package is None  # honest degradation, no exception propagated


@pytest.mark.asyncio
@respx.mock
async def test_context_package_attached_when_construction_succeeds():
    _mock_agents()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "venue_id": None}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=[]))
    registry = AdapterRegistry(adapters={"anthropic": _shared_chain_adapter()})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client, _headers(), recommendation_id="r1", game_id="g1", correlation_id="corr-1",
            candidate=_candidate(), upstream_outputs=(), participation=_participation(),
            routing_rules=_routing_rules(), adapter_registry=registry,
        )

    assert isinstance(chain_result.context.context_package, ContextPackage)
    assert chain_result.context.context_package.game_id == "g1"
    assert chain_result.context.context_package.player_id is None  # no player_id passed -- real, honest default


# --- Real JSN/SEA@NE live-path proof: cycle.py -> engine -> ContextPackage
# -> SequentialDecisionContext -> build_evidence() -> contextual_evidence ---

JSN_PLAYER_ID = "c9b7de10-b380-45e4-90a3-f98444dce258"
SEA_NE_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"
SEATTLE_TEAM_ID = "3ca09e7e-f92a-4fc8-9ba2-3c3144d58207"
NEW_ENGLAND_TEAM_ID = "918a529e-f9e7-4bf5-8957-de5f39af5ad2"
SEA_NE_VENUE_ID = "ebe8bbcc-23b4-453e-98d9-8b7eee1e0dc3"

JSN_STATS = {
    "receiving": {"recTD": 1, "recLng": 45, "targets": 11, "recYards": 122, "rec20Plus": 2, "rec40Plus": 1, "recAverage": 15.2, "recFumbles": 0, "receptions": 8, "rec1stDowns": 5},
    "_unreliable_fields": ["snapCounts"],
    "_unreliable_fields_reason": "test: snapCounts flagged unreliable by source pipeline",
}
JSN_SEA_NE_RAW_ROWS = [
    {"id": "4026f70f-5b08-483d-88ba-c6a6bb07f07c", "player_id": JSN_PLAYER_ID, "game_id": SEA_NE_GAME_ID, "created_at": "2026-09-10T20:38:42.113431+00:00", "stats": {**JSN_STATS, "snapCounts": {"offenseSnaps": 0}}},
    {"id": "4ee8eae8-e213-4533-b099-3945d0d3fd41", "player_id": JSN_PLAYER_ID, "game_id": SEA_NE_GAME_ID, "created_at": "2026-09-14T23:02:03.657231+00:00", "stats": {**JSN_STATS, "snapCounts": {"offenseSnaps": 45}}},
]
SEA_NE_RAW_GAME_EVENT_PAYLOAD = {"body": {"game": {"id": 163541, "homeTeam": {"id": 79, "abbreviation": "SEA"}, "awayTeam": {"id": 50, "abbreviation": "NE"}}}}
SEA_NE_SPREAD_OPEN = {"game_id": SEA_NE_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "New England Patriots", "point": 3.5, "price": -115}, {"name": "Seattle Seahawks", "point": -3.5, "price": -105}]}, "captured_at": "2026-09-07T02:30:55.267463+00:00"}
SEA_NE_SPREAD_LATEST = {"game_id": SEA_NE_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "New England Patriots", "point": 3, "price": -102}, {"name": "Seattle Seahawks", "point": -3, "price": -118}]}, "captured_at": "2026-09-10T00:17:07.104582+00:00"}
LV_MIA_GAME_ID = "42eae7bd-08ca-4bfc-a83b-3bfac35f8b92"
LV_MIA_SPREAD_OPEN = {"game_id": LV_MIA_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "Las Vegas Raiders", "point": -3.5, "price": -105}, {"name": "Miami Dolphins", "point": 3.5, "price": -115}]}, "captured_at": "2026-09-07T18:03:29.355010+00:00"}
LV_MIA_SPREAD_LATEST = {"game_id": LV_MIA_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "Las Vegas Raiders", "point": -3, "price": -110}, {"name": "Miami Dolphins", "point": 3, "price": -110}]}, "captured_at": "2026-09-13T20:15:54.296273+00:00"}
LAC_ARI_GAME_ID = "57316028-d864-48e5-bbeb-df37618a1b27"
LAC_ARI_SPREAD_OPEN = {"game_id": LAC_ARI_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "Arizona Cardinals", "point": 10, "price": -115}, {"name": "Los Angeles Chargers", "point": -10, "price": -105}]}, "captured_at": "2026-09-07T18:03:29.355010+00:00"}
LAC_ARI_SPREAD_LATEST = {"game_id": LAC_ARI_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "Arizona Cardinals", "point": 8.5, "price": -102}, {"name": "Los Angeles Chargers", "point": -8.5, "price": -118}]}, "captured_at": "2026-09-13T20:15:54.296273+00:00"}
ALL_REAL_ODDS_ROWS = [SEA_NE_SPREAD_OPEN, SEA_NE_SPREAD_LATEST, LV_MIA_SPREAD_OPEN, LV_MIA_SPREAD_LATEST, LAC_ARI_SPREAD_OPEN, LAC_ARI_SPREAD_LATEST]
SEA_NE_WEATHER_ROW = {"game_id": SEA_NE_GAME_ID, "weather_data": {"source": "weatherapi", "is_dome": False, "wind_mph": 0.9, "conditions": "Overcast", "observed_at": "2026-09-09T23:00:00+00:00", "temperature_f": 63.1, "precipitation_pct": 15.0}, "captured_at": "2026-09-07T23:10:25.507456+00:00"}
PHI_WAS_WEATHER_ROW = {"game_id": "cd0f612b-6ff3-48c3-b9ef-55da1ac38226", "weather_data": {"source": "weatherapi", "is_dome": False, "wind_mph": 11.4, "conditions": "Cloudy", "observed_at": "2026-09-09T23:00:00+00:00", "temperature_f": 76.5, "precipitation_pct": 7}, "captured_at": "2026-09-07T23:10:25.507456+00:00"}


def _sea_ne_candidate() -> MarketCandidate:
    return MarketCandidate(
        game_id=SEA_NE_GAME_ID, sportsbook="DraftKings", market_type="player_receiving_yards",
        selection="Jaxon Smith-Njigba Over 65.5", american_odds=-115, point=65.5,
        observed_at=datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc),
    )


def _games_route(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    if "venue_id" in params:
        return httpx.Response(200, json=[])  # real, live-confirmed: 0 other games share Lumen Field
    id_param = params.get("id", "")
    if id_param.startswith("eq."):
        return httpx.Response(200, json=[{"id": SEA_NE_GAME_ID, "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "venue_id": SEA_NE_VENUE_ID, "venue_lat": 47.595097, "venue_long": -122.332245, "venue_type": "outdoor", "stadium": "Lumen Field"}])
    return httpx.Response(200, json=[{"id": SEA_NE_GAME_ID, "scheduled_start": "2026-09-10T00:20:00+00:00", "home_team": "SEA", "away_team": "NE"}])


def _teams_route(request: httpx.Request) -> httpx.Response:
    if "name" in request.url.params:
        return httpx.Response(200, json=[])
    return httpx.Response(200, json=[{"id": SEATTLE_TEAM_ID, "name": "Seattle Seahawks"}, {"id": NEW_ENGLAND_TEAM_ID, "name": "New England Patriots"}])


def _odds_route(request: httpx.Request) -> httpx.Response:
    if "game_id" in request.url.params:
        return httpx.Response(200, json=[SEA_NE_SPREAD_OPEN, SEA_NE_SPREAD_LATEST])
    return httpx.Response(200, json=ALL_REAL_ODDS_ROWS)


def _mock_jsn_sea_ne_context_boundaries():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_games_route)
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(side_effect=_teams_route)
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(side_effect=_odds_route)
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[SEA_NE_WEATHER_ROW, PHI_WAS_WEATHER_ROW]))
    respx.get(f"{SUPABASE_URL}/rest/v1/venues").mock(return_value=httpx.Response(200, json=[{"id": SEA_NE_VENUE_ID, "name": "Lumen Field", "city": "Seattle", "state": "WA", "venue_type": "outdoor"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(200, json=[{"id": JSN_PLAYER_ID, "name": "Jaxon Smith-Njigba", "position": "WR", "team_id": SEATTLE_TEAM_ID}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=JSN_SEA_NE_RAW_ROWS))
    respx.get(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(200, json=[{"game_id": SEA_NE_GAME_ID, "raw_payload": SEA_NE_RAW_GAME_EVENT_PAYLOAD}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": SEATTLE_TEAM_ID, "provider_team_id": "79"}, {"team_id": NEW_ENGLAND_TEAM_ID, "provider_team_id": "50"}])
    )


@pytest.mark.asyncio
@respx.mock
async def test_jsn_sea_ne_live_path_cycle_to_build_evidence():
    """Directive Section 5 -- the real JSN/SEA@NE live path, end to end:
    cycle.py -> Context Intelligence engine -> ContextPackage ->
    SequentialDecisionContext -> build_evidence() -> contextual_evidence.
    `player_id` is passed explicitly here (simulating a future caller
    that has one -- see cycle.py's own module docstring: no real
    production call site supplies one today)."""
    _mock_jsn_sea_ne_context_boundaries()
    _mock_agents()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    registry = AdapterRegistry(adapters={"anthropic": _shared_chain_adapter()})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client, _headers(), recommendation_id="r1", game_id=SEA_NE_GAME_ID, correlation_id="corr-jsn",
            candidate=_sea_ne_candidate(), upstream_outputs=(), participation=_participation(),
            routing_rules=_routing_rules(), adapter_registry=registry, player_id=JSN_PLAYER_ID,
        )

    # cycle.py -> engine -> ContextPackage: a real package reached SequentialDecisionContext.
    package = chain_result.context.context_package
    assert isinstance(package, ContextPackage)
    assert package.player_id == JSN_PLAYER_ID

    # SequentialDecisionContext -> build_evidence() -> contextual_evidence.
    evidence = ProbabilityModelingAgent().build_evidence(chain_result.context)
    ce = evidence["contextual_evidence"]

    # venue reaches contextual_evidence.
    assert "venue" in ce["dimensions"]
    # player_performance reaches contextual_evidence when available -- with the real stat line.
    obs = ce["dimensions"]["player_performance"]["facts"]["observations"][0]
    assert obs["role_usage_signals"]["receiving"] == {"targets": 11, "receptions": 8, "recYards": 122, "recTD": 1}
    # market reaches contextual_evidence.
    assert "market" in ce["dimensions"]
    assert ce["dimensions"]["market"]["completeness"] == "joined"
    # weather reaches contextual_evidence when available.
    assert ce["dimensions"]["weather"]["completeness"] == "partial"

    # blocked dimensions remain excluded.
    for blocked in ("news", "injuries", "roster_role", "team_performance", "depth_lineup", "game_state_pbp"):
        assert blocked not in ce["dimensions"]

    # no context-derived confidence anywhere.
    def _all_keys(obj):
        keys = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.add(k)
                keys |= _all_keys(v)
        elif isinstance(obj, list):
            for item in obj:
                keys |= _all_keys(item)
        return keys
    assert _all_keys(ce).isdisjoint({"confidence", "probability_score"})

    # no probability calculation / recommendation ranking changes -- the real chain's own
    # ProbabilityModelOutput (from the FakeModelAdapter's scripted response) is untouched by
    # whether contextual_evidence was attached; only what the evidence DICT contains differs.
    assert chain_result.status == "full"
    assert chain_result.probability.modeled_probability == 0.57  # exactly the scripted value, unchanged
    assert chain_result.probability.confidence_in_probability == 0.72  # unchanged -- no context-derived confidence
