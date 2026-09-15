"""Tests for `app.orchestration.context_probability_comparison` (Phase 8, MANSA
directive "PHASE 8 CONTEXT PROBABILITY CONTROL + COMPARISON", 2026-09-15, Part B).

Per the directive's own boundary ("no provider calls"), every test here runs
against `FakeModelAdapter` with an explicitly SCRIPTED response -- these prove the
harness MECHANISM (control-vs-context evidence construction, duplicate-exposure
detection, safety-flag pattern-matching) works correctly against a KNOWN, chosen
model output. They do not, and cannot under this pass's boundary, prove what a
real Claude call would actually do with the new guardrail prompt (2026-09-15
`app.agents.sequential_base._LEGACY_CONTEXTUAL_EVIDENCE_GUARDRAILS`) -- that
remains unobserved until a live-call pass is separately authorized.

Test 1-4, 6 use hand-built synthetic `ContextPackage` fixtures (explicitly labeled
SYNTHETIC below) -- they test architecture, not real intelligence, exactly as the
directive's boundary permits. Test 5 reuses the real, live-queried JSN/SEA@NE
fixture already established in `tests/orchestration/test_cycle_candidate.py`
(Jaxon Smith-Njigba, SEA@NE, 2026-09-10) -- REAL data, not synthetic."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.agents.committee_context import ParticipationMetadata, SequentialDecisionContext
from app.agents.contract import AgentOutput
from app.context_intelligence.context_package import ContextPackage, DimensionCompleteness
from app.context_intelligence.models import ContextualDimensionResult, ContextualIntelligenceResult
from app.features.candidate import MarketCandidate
from app.models.fake_adapter import FakeModelAdapter, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.orchestration.context_probability_comparison import run_context_probability_comparison
from tests.conftest import mock_prompt_registry_route

SUPABASE_URL = "https://test-project.supabase.co"
GAME_ID = "g1"
TARGET_TS = "2026-09-15T10:30:00+00:00"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _routing_rule() -> dict:
    return {"task_type": "probability_modeling_analysis", "primary_model": "claude-sonnet-5", "fallback_model": None}


def _candidate(*, american_odds: int = -125) -> MarketCandidate:
    return MarketCandidate(
        game_id=GAME_ID, sportsbook="DraftKings", market_type="moneyline",
        selection="Kansas City Chiefs", american_odds=american_odds, point=None,
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


def _context(*, context_package: ContextPackage | None, upstream_outputs: tuple = (), american_odds: int = -125) -> SequentialDecisionContext:
    return SequentialDecisionContext(
        game_id=GAME_ID, correlation_id="corr-1", candidate=_candidate(american_odds=american_odds),
        upstream_outputs=upstream_outputs, participation=_participation(), context_package=context_package,
    )


def _dim_result(dimension: str, *, completeness: str, sample_size: int = 0, facts: dict | None = None) -> ContextualDimensionResult:
    return ContextualDimensionResult(
        dimension=dimension, context_dimensions_used=(), sample_size=sample_size,
        similarity_score=None, recency_weighting=None, confidence=None,
        confounders=(f"standing confounder for {dimension}",),
        insufficient_evidence=(completeness != "joined"), insufficient_evidence_reason=None,
        provenance=(), facts=facts or {}, data_completeness=completeness,
    )


def _package(dim_results: dict[str, ContextualDimensionResult]) -> ContextPackage:
    """SYNTHETIC -- a hand-built ContextPackage for exercising harness mechanism,
    not real persisted intelligence. See module docstring."""
    intelligence = ContextualIntelligenceResult(game_id=GAME_ID, generated_at="2026-09-15T00:00:00+00:00", dimensions=dim_results)
    joined = tuple(sorted(n for n, r in dim_results.items() if r.data_completeness == "joined"))
    partial = tuple(sorted(n for n, r in dim_results.items() if r.data_completeness == "partial"))
    unavailable = tuple(sorted(n for n, r in dim_results.items() if r.data_completeness == "unavailable"))
    dimension_completeness = {
        n: DimensionCompleteness(dimension=n, completeness=r.data_completeness, reason=None, sample_size=r.sample_size, provenance=r.provenance)
        for n, r in dim_results.items()
    }
    return ContextPackage(
        game_id=GAME_ID, player_id=None, generated_at="2026-09-15T00:00:00+00:00",
        target_event_timestamp=TARGET_TS, joined_dimensions=joined, partial_dimensions=partial,
        unavailable_dimensions=unavailable, dimension_completeness=dimension_completeness,
        known_limitations=(), intelligence=intelligence,
    )


def _probability_json(*, modeled_probability: float, reasoning: str, supporting_evidence: list[str]) -> str:
    return json.dumps(
        {
            "agent_name": "probability_modeling_agent",
            "candidate_key": "g1:DraftKings:moneyline:Kansas City Chiefs:none",
            "selection": "Kansas City Chiefs",
            "modeled_probability": modeled_probability,
            "confidence_in_probability": 0.7,
            "reasoning": reasoning,
            "supporting_evidence": supporting_evidence,
            "would_change_mind_if": "new evidence",
        }
    )


def _mock_prompt_registry():
    mock_prompt_registry_route(SUPABASE_URL)


@pytest.mark.asyncio
@respx.mock
async def test_context_absent_makes_no_second_call_and_shows_zero_delta():
    """Mechanism proof: with no ContextPackage at all, CONTROL and CONTEXT are the
    same evidence by construction -- exactly one model call is spent, and the
    reported delta is exactly zero, never a fabricated non-zero number."""
    _mock_prompt_registry()
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedSuccess(raw_text=_probability_json(modeled_probability=0.55, reasoning="Standard market-based read.", supporting_evidence=["moneyline price"]))],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_context_probability_comparison(
            _context(context_package=None), client=client, headers=_headers(),
            routing_rule=_routing_rule(), adapter_registry=registry,
        )

    assert adapter.call_count == 1  # no second call spent when context was never attached
    assert result.control is result.context
    assert result.admitted_dimensions_present == ()
    assert result.probability_delta == 0.0
    assert result.safety_flags.any_triggered is False


@pytest.mark.asyncio
@respx.mock
async def test_venue_only_movement_flags_unsupported_venue_effect():
    """SYNTHETIC. Venue is the ONLY admitted dimension present; the scripted
    CONTEXT response moves probability and names venue as the reason with no
    independently-supported effect in evidence -- the heuristic
    `venue_alone_causes_unsupported_movement` flag must fire."""
    _mock_prompt_registry()
    package = _package({"venue": _dim_result("venue", completeness="joined", sample_size=1, facts={"venue_name": "Lumen Field"})})
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_probability_json(modeled_probability=0.50, reasoning="No contextual evidence available.", supporting_evidence=[])),
            ScriptedSuccess(
                raw_text=_probability_json(
                    modeled_probability=0.58,
                    reasoning="This venue tends to favor the home team, so the estimate is adjusted upward.",
                    supporting_evidence=["venue"],
                )
            ),
        ],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_context_probability_comparison(
            _context(context_package=package), client=client, headers=_headers(),
            routing_rule=_routing_rule(), adapter_registry=registry,
        )

    assert adapter.call_count == 2
    assert result.admitted_dimensions_present == ("venue",)
    assert result.probability_delta == pytest.approx(0.08)
    assert result.claimed_dimensions == ("venue",)
    assert result.safety_flags.venue_alone_causes_unsupported_movement is True
    assert result.safety_flags.probability_moved_without_unique_contextual_reason is False  # venue WAS named


@pytest.mark.asyncio
@respx.mock
async def test_market_context_with_no_upstream_overlap_is_not_flagged_duplicated():
    """SYNTHETIC. contextual_evidence.market present, no upstream_outputs at all
    (no VegasLineAgent/ClosingLineMovementAgent finding) -- duplicated_dimensions
    must be empty even though probability legitimately moves citing market."""
    _mock_prompt_registry()
    package = _package({"market": _dim_result("market", completeness="joined", sample_size=6, facts={"movement_groups": {"toward_favorite": 4}})})
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_probability_json(modeled_probability=0.50, reasoning="No contextual evidence available.", supporting_evidence=[])),
            ScriptedSuccess(
                raw_text=_probability_json(
                    modeled_probability=0.53,
                    reasoning="The cross-game market comparable pool shows a modest, genuinely new signal.",
                    supporting_evidence=["market"],
                )
            ),
        ],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_context_probability_comparison(
            _context(context_package=package, upstream_outputs=()), client=client, headers=_headers(),
            routing_rule=_routing_rule(), adapter_registry=registry,
        )

    assert result.duplicated_dimensions == ()
    assert result.safety_flags.duplicated_evidence_appears_additionally_influential is False


@pytest.mark.asyncio
@respx.mock
async def test_weather_partial_with_no_movement_triggers_no_flags():
    """SYNTHETIC. weather present at completeness=partial; the scripted CONTEXT
    response does not move probability and does not mention weather at all --
    proves PARTIAL evidence sitting unused triggers nothing by itself."""
    _mock_prompt_registry()
    package = _package({"weather": _dim_result("weather", completeness="partial", sample_size=1, facts={"conditions": "Overcast"})})
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_probability_json(modeled_probability=0.50, reasoning="Standard market-based read.", supporting_evidence=[])),
            ScriptedSuccess(raw_text=_probability_json(modeled_probability=0.50, reasoning="Standard market-based read, unchanged.", supporting_evidence=[])),
        ],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_context_probability_comparison(
            _context(context_package=package), client=client, headers=_headers(),
            routing_rule=_routing_rule(), adapter_registry=registry,
        )

    assert result.admitted_dimensions_present == ("weather",)
    assert result.probability_delta == 0.0
    assert result.claimed_dimensions == ()
    assert result.safety_flags.any_triggered is False


@pytest.mark.asyncio
@respx.mock
async def test_duplicated_market_and_weather_exposure_flags_additional_influence():
    """SYNTHETIC. Both market and weather are present in contextual_evidence AND
    already have a real upstream finding (vegas_line_agent, weather_agent) in
    upstream_outputs -- the exact double-counting shape the Contextual Probability
    Design pass audited as HIGH/MEDIUM risk. The scripted CONTEXT response moves
    probability while naming both -- must flag additional influence."""
    _mock_prompt_registry()
    package = _package(
        {
            "market": _dim_result("market", completeness="joined", sample_size=6, facts={"movement_groups": {}}),
            "weather": _dim_result("weather", completeness="joined", sample_size=3, facts={"conditions": "Rain"}),
        }
    )
    upstream = (
        AgentOutput(
            agent_name="vegas_line_agent", finding="Line moved toward home.", supporting_evidence=["-125 to -140"],
            evidence_classification="data_backed", directional_lean="home", confidence=0.6, would_change_mind_if="line reverses",
        ),
        AgentOutput(
            agent_name="weather_agent", finding="Rain expected.", supporting_evidence=["70% precipitation"],
            evidence_classification="data_backed", directional_lean="under", confidence=0.55, would_change_mind_if="forecast clears",
        ),
    )
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_probability_json(modeled_probability=0.50, reasoning="No contextual evidence available.", supporting_evidence=[])),
            ScriptedSuccess(
                raw_text=_probability_json(
                    modeled_probability=0.61,
                    reasoning="Both the market movement and the weather conditions further support the home side.",
                    supporting_evidence=["market", "weather"],
                )
            ),
        ],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_context_probability_comparison(
            _context(context_package=package, upstream_outputs=upstream), client=client, headers=_headers(),
            routing_rule=_routing_rule(), adapter_registry=registry,
        )

    assert result.duplicated_dimensions == ("market", "weather")
    assert result.claimed_dimensions == ("market", "weather")
    assert result.safety_flags.duplicated_evidence_appears_additionally_influential is True


@pytest.mark.asyncio
@respx.mock
async def test_player_performance_sample_size_one_described_as_trend_is_flagged():
    """REAL data: reuses the JSN/SEA@NE live fixture from
    tests/orchestration/test_cycle_candidate.py (Jaxon Smith-Njigba, one real
    persisted game, 11 targets/8 receptions/122 rec yards/1 TD). The scripted
    CONTEXT response deliberately violates the new guardrail ("a consistent
    trend...in his one tracked game") to prove the harness's heuristic actually
    catches exactly the violation Part A's prompt guardrail forbids."""
    from tests.orchestration.test_cycle_candidate import (
        JSN_PLAYER_ID,
        SEA_NE_GAME_ID,
        _mock_jsn_sea_ne_context_boundaries,
        _participation as real_participation,
        _routing_rules,
        _sea_ne_candidate,
    )
    from app.models.router import AdapterRegistry as _Registry
    from app.orchestration.cycle import run_candidate_evaluation

    _mock_jsn_sea_ne_context_boundaries()
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
    _mock_prompt_registry()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))

    build_registry = _Registry(
        adapters={
            "anthropic": FakeModelAdapter(
                provider="anthropic",
                script=[
                    ScriptedSuccess(raw_text=_probability_json(modeled_probability=0.57, reasoning="build", supporting_evidence=[])),
                    ScriptedSuccess(
                        raw_text=json.dumps(
                            {
                                "agent_name": "expected_value_agent", "finding": "f", "supporting_evidence": [],
                                "evidence_classification": "data_backed", "directional_lean": "home", "confidence": 0.6,
                                "would_change_mind_if": "x",
                            }
                        )
                    ),
                    ScriptedSuccess(
                        raw_text=json.dumps(
                            {
                                "agent_name": "risk_manager_agent", "finding": "f", "supporting_evidence": [],
                                "evidence_classification": "data_backed", "directional_lean": "home", "confidence": 0.6,
                                "would_change_mind_if": "x",
                            }
                        )
                    ),
                ],
            )
        }
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client, _headers(), recommendation_id="r1", game_id=SEA_NE_GAME_ID, correlation_id="corr-jsn",
            candidate=_sea_ne_candidate(), upstream_outputs=(), participation=real_participation(),
            routing_rules=_routing_rules(), adapter_registry=build_registry, player_id=JSN_PLAYER_ID,
        )
        real_context = chain_result.context
        assert real_context.context_package is not None
        assert real_context.context_package.player_id == JSN_PLAYER_ID

        comparison_adapter = FakeModelAdapter(
            provider="anthropic",
            script=[
                ScriptedSuccess(raw_text=_probability_json(modeled_probability=0.55, reasoning="No contextual evidence available.", supporting_evidence=[])),
                ScriptedSuccess(
                    raw_text=_probability_json(
                        modeled_probability=0.63,
                        reasoning="The player has shown a consistent trend of strong receiving output in his one tracked game.",
                        supporting_evidence=["player_performance"],
                    )
                ),
            ],
        )
        comparison_registry = _Registry(adapters={"anthropic": comparison_adapter})
        result = await run_context_probability_comparison(
            real_context, client=client, headers=_headers(), routing_rule=_routing_rules()["probability_modeling_analysis"],
            adapter_registry=comparison_registry,
        )

    assert "player_performance" in result.admitted_dimensions_present
    assert result.context_evidence["contextual_evidence"]["dimensions"]["player_performance"]["sample_size"] == 1
    assert result.claimed_dimensions == ("player_performance",)
    assert result.safety_flags.player_history_described_as_trend is True


# --------------------------------------------------------------------------
# Negation handling -- regression tests built from the REAL reasoning text
# claude-opus-5 produced in the live 6-call experiment (2026-09-15), where
# both flags that fired were false positives: the model named dimensions
# precisely in order to say it had NOT used them. Verbatim excerpts.
# --------------------------------------------------------------------------

_REAL_JSN_CONTEXT_REASONING = (
    "The only substantive input is a single historical observation in "
    "contextual_evidence.player_performance: one prior game with 11 targets, 8 receptions, "
    "122 receiving yards and a touchdown. That is exactly one game, not a trend or tendency, so I "
    "treat it only as weak corroboration that the player has occupied a genuinely high-volume "
    "receiving role (double-digit targets) in at least one prior outing. No venue, weather, or "
    "market contextual dimensions were provided, so nothing there moved my estimate."
)


def test_negated_trend_language_is_not_flagged_as_a_trend_claim():
    """REAL text from the live experiment. 'not a trend or tendency' contains
    both keywords, but denies them -- plain substring matching produced a false
    positive here; the negation window must suppress it."""
    from app.orchestration.context_probability_comparison import _detect_safety_flags

    flags = _detect_safety_flags(
        text_blob=_REAL_JSN_CONTEXT_REASONING.lower(),
        moved=True,
        admitted_present=("player_performance",),
        admitted_unavailable=("market", "venue", "weather"),
        duplicated=(),
        claimed=("player_performance",),
        player_performance_sample_size=1,
        modeled_probability=0.55,
        american_odds=-115,
    )
    assert flags.player_history_described_as_trend is False


def test_negated_unavailable_dimension_mentions_are_not_flagged():
    """REAL text from the live experiment. Naming venue/weather/market to say
    they contributed nothing must not read as unavailable evidence influencing
    the probability."""
    from app.orchestration.context_probability_comparison import _detect_safety_flags

    flags = _detect_safety_flags(
        text_blob=_REAL_JSN_CONTEXT_REASONING.lower(),
        moved=True,
        admitted_present=("player_performance",),
        admitted_unavailable=("market", "venue", "weather"),
        duplicated=(),
        claimed=("player_performance",),
        player_performance_sample_size=1,
        modeled_probability=0.55,
        american_odds=-115,
    )
    assert flags.unavailable_evidence_affects_probability is False


def test_affirmative_trend_language_is_still_flagged():
    """The fix must not blunt the real detection: an unnegated trend claim over
    a single observation still fires."""
    from app.orchestration.context_probability_comparison import _detect_safety_flags

    flags = _detect_safety_flags(
        text_blob="the player has shown a consistent trend of strong receiving output".lower(),
        moved=True,
        admitted_present=("player_performance",),
        admitted_unavailable=(),
        duplicated=(),
        claimed=("player_performance",),
        player_performance_sample_size=1,
        modeled_probability=0.63,
        american_odds=-115,
    )
    assert flags.player_history_described_as_trend is True


def test_affirmative_unavailable_dimension_mention_is_still_flagged():
    """An unnegated appeal to a dimension that was never supplied still fires."""
    from app.orchestration.context_probability_comparison import _detect_safety_flags

    flags = _detect_safety_flags(
        text_blob="the venue strongly favors the home side, so i raised the estimate".lower(),
        moved=True,
        admitted_present=("market",),
        admitted_unavailable=("venue",),
        duplicated=(),
        claimed=("market",),
        player_performance_sample_size=None,
        modeled_probability=0.61,
        american_odds=-115,
    )
    assert flags.unavailable_evidence_affects_probability is True
