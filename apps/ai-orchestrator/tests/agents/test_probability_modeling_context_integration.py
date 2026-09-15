"""Tests for the Context Intelligence integration into
`ProbabilityModelingAgent.build_evidence` (2026-09-15, HQ-authorized
"MANSA -- PHASE 8 BUILD_EVIDENCE CONTEXT INTEGRATION"), implementing the
same-day Admission Decision. Synthetic/mechanism tests only -- the real
JSN/SEA@NE proof through the actual engine + assembly + build_evidence
path lives in `tests/context_intelligence/test_engine.py` (built on real
live-queried DEV values, not hand-built fixtures)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.agents.committee_context import ParticipationMetadata, SequentialDecisionContext
from app.agents.probability_modeling import ADMITTED_CONTEXT_DIMENSIONS, ProbabilityModelingAgent
from app.context_intelligence.context_package import ContextPackage, DimensionCompleteness
from app.context_intelligence.models import ContextualDimensionResult, ContextualIntelligenceResult, ProvenanceRef
from app.features.candidate import MarketCandidate

GAME_ID = "g1"
TARGET_TS = "2026-09-15T10:30:00+00:00"


def _candidate() -> MarketCandidate:
    return MarketCandidate(
        game_id=GAME_ID, sportsbook="DraftKings", market_type="moneyline",
        selection="Kansas City Chiefs", american_odds=-125, point=None,
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


def _context(**overrides) -> SequentialDecisionContext:
    base = dict(
        game_id=GAME_ID, correlation_id="corr-1", candidate=_candidate(),
        upstream_outputs=(), participation=_participation(),
    )
    base.update(overrides)
    return SequentialDecisionContext(**base)


def _dim_result(
    dimension: str, *, completeness: str, sample_size: int = 0, facts: dict | None = None,
    reason: str | None = None, provenance: tuple = (),
) -> ContextualDimensionResult:
    insufficient = completeness != "joined"
    return ContextualDimensionResult(
        dimension=dimension, context_dimensions_used=(), sample_size=sample_size,
        similarity_score=None, recency_weighting=None, confidence=None,
        confounders=(f"standing confounder for {dimension}",),
        insufficient_evidence=insufficient, insufficient_evidence_reason=reason,
        provenance=provenance, facts=facts or {}, data_completeness=completeness,
    )


def _package(dim_results: dict[str, ContextualDimensionResult], *, player_id: str | None = None) -> ContextPackage:
    intelligence = ContextualIntelligenceResult(game_id=GAME_ID, generated_at="2026-09-15T00:00:00+00:00", dimensions=dim_results)
    joined = tuple(sorted(n for n, r in dim_results.items() if r.data_completeness == "joined"))
    partial = tuple(sorted(n for n, r in dim_results.items() if r.data_completeness == "partial"))
    unavailable = tuple(sorted(n for n, r in dim_results.items() if r.data_completeness == "unavailable"))
    dimension_completeness = {
        n: DimensionCompleteness(dimension=n, completeness=r.data_completeness, reason=r.insufficient_evidence_reason, sample_size=r.sample_size, provenance=r.provenance)
        for n, r in dim_results.items()
    }
    return ContextPackage(
        game_id=GAME_ID, player_id=player_id, generated_at="2026-09-15T00:00:00+00:00",
        target_event_timestamp=TARGET_TS, joined_dimensions=joined, partial_dimensions=partial,
        unavailable_dimensions=unavailable, dimension_completeness=dimension_completeness,
        known_limitations=(), intelligence=intelligence,
    )


# --------------------------------------------------------------------------
# Regression safety -- existing callers unaffected
# --------------------------------------------------------------------------


def test_no_context_package_omits_contextual_evidence_entirely():
    """The core regression guarantee: every real production caller today
    constructs SequentialDecisionContext without context_package (defaults
    to None) -- the evidence dict must be byte-identical in shape to
    before this pass."""
    evidence = ProbabilityModelingAgent().build_evidence(_context())
    assert "contextual_evidence" not in evidence
    assert set(evidence.keys()) == {"candidate", "upstream_findings", "participation"}


def test_existing_fields_unchanged_regardless_of_context_package():
    ctx_without = _context()
    ctx_with = _context(context_package=_package({"venue": _dim_result("venue", completeness="joined", facts={"venue_id": "v1"})}))
    ev_without = ProbabilityModelingAgent().build_evidence(ctx_without)
    ev_with = ProbabilityModelingAgent().build_evidence(ctx_with)
    assert ev_without["candidate"] == ev_with["candidate"]
    assert ev_without["upstream_findings"] == ev_with["upstream_findings"]
    assert ev_without["participation"] == ev_with["participation"]


# --------------------------------------------------------------------------
# Explicit allowlist -- blocked dimensions cannot enter
# --------------------------------------------------------------------------


def test_blocked_dimension_never_appears_even_when_joined_in_the_package():
    """The single most important structural guarantee: a dimension not in
    ADMITTED_CONTEXT_DIMENSIONS must never reach contextual_evidence, no
    matter how "ready" it looks in the underlying ContextPackage."""
    package = _package({
        "venue": _dim_result("venue", completeness="joined", facts={"venue_id": "v1"}),
        "news": _dim_result("news", completeness="joined", facts={"articles": ["real", "data"]}),  # blocked, even though JOINED
        "injuries": _dim_result("injuries", completeness="partial", facts={"x": 1}),  # blocked
    })
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    assert "news" not in evidence["contextual_evidence"]["dimensions"]
    assert "injuries" not in evidence["contextual_evidence"]["dimensions"]
    assert set(evidence["contextual_evidence"]["dimensions"].keys()) == {"venue"}


def test_admitted_dimensions_constant_is_exactly_the_four_from_the_admission_decision():
    assert ADMITTED_CONTEXT_DIMENSIONS == ("venue", "player_performance", "market", "weather")
    blocked = {"news", "injuries", "roster_role", "team_performance", "depth_lineup", "game_state_pbp"}
    assert blocked.isdisjoint(ADMITTED_CONTEXT_DIMENSIONS)


def test_future_engine_expansion_cannot_silently_widen_admission():
    """Even a ContextPackage carrying an entirely new, hypothetical
    dimension name (simulating a future engine.py addition) cannot reach
    contextual_evidence without a code change to ADMITTED_CONTEXT_
    DIMENSIONS itself -- proving admission is not inferred from whatever
    the package happens to contain."""
    package = _package({
        "venue": _dim_result("venue", completeness="joined", facts={"venue_id": "v1"}),
        "some_future_dimension": _dim_result("some_future_dimension", completeness="joined", facts={"y": 2}),
    })
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    assert "some_future_dimension" not in evidence["contextual_evidence"]["dimensions"]


# --------------------------------------------------------------------------
# Missing-data safeguards
# --------------------------------------------------------------------------


def test_unavailable_admitted_dimension_is_absent_not_zero_filled():
    package = _package({
        "venue": _dim_result("venue", completeness="joined", facts={"venue_id": "v1"}),
        "player_performance": _dim_result("player_performance", completeness="unavailable", facts={}, reason="no real observation"),
    })
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    assert "player_performance" not in evidence["contextual_evidence"]["dimensions"]
    assert "venue" in evidence["contextual_evidence"]["dimensions"]


def test_partial_dimension_is_admitted_as_partial_never_coerced_to_joined():
    package = _package({
        "weather": _dim_result("weather", completeness="partial", facts={"temperature_f": 63.1}, sample_size=1, reason="fewer than 2 comparables"),
    })
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    entry = evidence["contextual_evidence"]["dimensions"]["weather"]
    assert entry["completeness"] == "partial"  # never silently upgraded
    assert "fewer than 2 comparables" in entry["limitations"]


def _all_keys(obj) -> set[str]:
    """Recursively collects every dict key in a nested structure -- used
    to prove no field literally named confidence/probability_score exists
    anywhere, without false-positiving on caveat prose that legitimately
    discusses the word "confidence" as documentation."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _all_keys(item)
    return keys


def test_no_confidence_field_anywhere_in_contextual_evidence():
    """Structural proof: completeness never becomes a confidence number
    -- no dict KEY named confidence/probability_score exists anywhere in
    the payload (prose that merely mentions "confidence" as documentation,
    e.g. inside a caveat string, is not itself a field)."""
    package = _package({
        "market": _dim_result("market", completeness="joined", facts={"movement_groups": []}, sample_size=5),
        "weather": _dim_result("weather", completeness="partial", facts={"temperature_f": 63.1}, sample_size=1),
    })
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    keys = _all_keys(evidence["contextual_evidence"])
    forbidden = {"confidence", "probability_score", "probability", "prediction_score"}
    assert keys.isdisjoint(forbidden)


# --------------------------------------------------------------------------
# Provenance and point-in-time caveats preserved
# --------------------------------------------------------------------------


def test_provenance_carried_forward_verbatim_not_flattened():
    prov = (ProvenanceRef(table="venues", source=None, row_count=1, earliest_at=None, latest_at=None),)
    package = _package({"venue": _dim_result("venue", completeness="joined", facts={"venue_id": "v1"}, provenance=prov)})
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    assert evidence["contextual_evidence"]["dimensions"]["venue"]["provenance"] == [
        {"table": "venues", "source": None, "row_count": 1, "earliest_at": None, "latest_at": None}
    ]


def test_market_and_weather_carry_the_comparable_pool_live_only_caveat():
    package = _package({
        "market": _dim_result("market", completeness="joined", facts={"x": 1}),
        "weather": _dim_result("weather", completeness="partial", facts={"x": 1}),
    })
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    for name in ("market", "weather"):
        caveat = evidence["contextual_evidence"]["dimensions"][name]["point_in_time_caveat"]
        assert "has NOT been verified safe for backtesting" in caveat
        assert "live call" in caveat


def test_player_performance_carries_its_own_point_in_time_caveat():
    package = _package({"player_performance": _dim_result("player_performance", completeness="joined", facts={"game_count": 1, "observations": []})})
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    caveat = evidence["contextual_evidence"]["dimensions"]["player_performance"]["point_in_time_caveat"]
    assert "no observation/ingestion timestamp" in caveat


def test_venue_carries_a_static_facts_caveat_not_silently_omitted():
    package = _package({"venue": _dim_result("venue", completeness="joined", facts={"venue_id": "v1"})})
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    caveat = evidence["contextual_evidence"]["dimensions"]["venue"]["point_in_time_caveat"]
    assert "static" in caveat.lower()


def test_target_event_timestamp_and_known_limitations_carried_at_package_level():
    package = _package({"venue": _dim_result("venue", completeness="joined", facts={"venue_id": "v1"})})
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    assert evidence["contextual_evidence"]["target_event_timestamp"] == TARGET_TS
    assert evidence["contextual_evidence"]["known_limitations"] == []


# --------------------------------------------------------------------------
# player_performance-specific restriction enforcement
# --------------------------------------------------------------------------


def test_player_performance_sample_size_and_duplicate_tracking_preserved():
    facts = {
        "game_count": 1,
        "observations": [{
            "player_id": "p1", "game_id": "g2", "duplicate_raw_row_count": 2,
            "canonical_row_id": "row-new", "role_usage_signals": {"receiving": {"targets": 11}},
            "reliability_limitations": ["some limitation"], "opponent": "New England Patriots",
        }],
    }
    package = _package({"player_performance": _dim_result("player_performance", completeness="joined", facts=facts, sample_size=1)})
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    entry = evidence["contextual_evidence"]["dimensions"]["player_performance"]
    assert entry["sample_size"] == 1  # one-game evidence, not a trend
    obs = entry["facts"]["observations"][0]
    assert obs["duplicate_raw_row_count"] == 2  # correction history preserved
    assert obs["canonical_row_id"] == "row-new"  # canonical-observation semantics preserved
    assert obs["reliability_limitations"] == ["some limitation"]  # not silently dropped


def test_player_performance_unresolved_opponent_does_not_fabricate_context():
    facts = {"game_count": 1, "observations": [{"opponent": None, "role_usage_signals": {"receiving": {"targets": 5}}}]}
    package = _package({"player_performance": _dim_result("player_performance", completeness="joined", facts=facts, sample_size=1)})
    evidence = ProbabilityModelingAgent().build_evidence(_context(context_package=package))
    obs = evidence["contextual_evidence"]["dimensions"]["player_performance"]["facts"]["observations"][0]
    assert obs["opponent"] is None  # real None passed through, never a guessed team name
    assert obs["role_usage_signals"]["receiving"]["targets"] == 5  # rest of the observation still admitted
