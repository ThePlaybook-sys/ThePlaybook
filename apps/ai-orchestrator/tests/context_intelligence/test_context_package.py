"""Tests for app.context_intelligence.context_package (Historical Context
Assembly V1 pass, 2026-09-15). Pure function, no I/O -- mechanism tests
using small, explicitly synthetic `ContextualDimensionResult` fixtures to
exercise the JOINED/PARTIAL/UNAVAILABLE derivation rule and the
package-level summary in isolation. The real JSN/SEA@NE package proof
lives in test_engine.py (built on top of the real engine path, not
hand-built fixtures)."""
from __future__ import annotations

import dataclasses

from app.context_intelligence.context_package import (
    COMPLETENESS_VALUES,
    ContextPackage,
    assemble_context_package,
)
from app.context_intelligence.models import ContextualDimensionResult, ContextualIntelligenceResult, ProvenanceRef

GAME_ID = "g1"
PLAYER_ID = "p1"
TARGET_TS = "2026-09-15T10:30:00+00:00"


def _result(
    dimension: str,
    *,
    insufficient_evidence: bool,
    facts: dict | None = None,
    reason: str | None = None,
    sample_size: int = 0,
    data_completeness: str | None = None,
    provenance: tuple = (),
) -> ContextualDimensionResult:
    return ContextualDimensionResult(
        dimension=dimension,
        context_dimensions_used=(),
        sample_size=sample_size,
        similarity_score=None,
        recency_weighting=None,
        confidence=None,
        confounders=("standing confounder",),
        insufficient_evidence=insufficient_evidence,
        insufficient_evidence_reason=reason,
        provenance=provenance,
        facts=facts or {},
        data_completeness=data_completeness,
    )


def _intelligence(dimensions: dict[str, ContextualDimensionResult]) -> ContextualIntelligenceResult:
    return ContextualIntelligenceResult(game_id=GAME_ID, generated_at="2026-09-15T00:00:00+00:00", dimensions=dimensions)


# --------------------------------------------------------------------------
# Derivation rule -- JOINED / PARTIAL / UNAVAILABLE
# --------------------------------------------------------------------------


def test_joined_when_evidence_is_sufficient():
    intelligence = _intelligence({"weather": _result("weather", insufficient_evidence=False, facts={"temperature_f": 63.1}, sample_size=5)})
    package = assemble_context_package(intelligence, player_id=None, target_event_timestamp=TARGET_TS)
    assert package.joined_dimensions == ("weather",)
    assert package.partial_dimensions == ()
    assert package.unavailable_dimensions == ()


def test_partial_when_insufficient_but_real_facts_exist():
    """The exact real shape a target-game observation was found (facts
    non-empty) but too few real comparables exist to score similarity --
    "real data exists but with a named caveat," per the JOINED/PARTIAL/
    UNAVAILABLE vocabulary's own definition."""
    intelligence = _intelligence({
        "venue": _result("venue", insufficient_evidence=True, facts={"venue_id": "v1"}, reason="only 0 other real tracked games share this venue", sample_size=0)
    })
    package = assemble_context_package(intelligence, player_id=None, target_event_timestamp=TARGET_TS)
    assert package.partial_dimensions == ("venue",)
    assert package.joined_dimensions == ()
    assert package.unavailable_dimensions == ()


def test_unavailable_when_insufficient_and_no_facts():
    """The exact real shape every unsupported.py stub already produces
    (facts={} unconditionally) -- requires zero special-casing by name."""
    intelligence = _intelligence({
        "injuries": _result("injuries", insufficient_evidence=True, facts={}, reason="BALLDONTLIE entitlement not confirmed active")
    })
    package = assemble_context_package(intelligence, player_id=None, target_event_timestamp=TARGET_TS)
    assert package.unavailable_dimensions == ("injuries",)


def test_explicit_data_completeness_is_respected_verbatim_not_rederived():
    """player_performance already sets data_completeness itself -- this
    module must use that value directly, never recompute it from
    insufficient_evidence/facts (which would be a redundant, possibly
    divergent second source of truth)."""
    intelligence = _intelligence({
        "player_performance": _result(
            "player_performance", insufficient_evidence=True, facts={"game_count": 1},
            data_completeness="joined",  # explicitly joined despite insufficient_evidence=True
        )
    })
    package = assemble_context_package(intelligence, player_id="jsn", target_event_timestamp=TARGET_TS)
    assert package.joined_dimensions == ("player_performance",)  # respects the explicit value, not "partial"


def test_all_three_states_can_coexist_in_one_package():
    intelligence = _intelligence({
        "weather": _result("weather", insufficient_evidence=False, facts={"temperature_f": 63.1}),
        "venue": _result("venue", insufficient_evidence=True, facts={"venue_id": "v1"}, reason="too few comparables"),
        "injuries": _result("injuries", insufficient_evidence=True, facts={}, reason="no provider entitlement"),
    })
    package = assemble_context_package(intelligence, player_id=None, target_event_timestamp=TARGET_TS)
    assert package.joined_dimensions == ("weather",)
    assert package.partial_dimensions == ("venue",)
    assert package.unavailable_dimensions == ("injuries",)


# --------------------------------------------------------------------------
# Package-level summary
# --------------------------------------------------------------------------


def test_every_dimension_present_in_intelligence_is_classified_exactly_once():
    """No dimension is silently omitted, no dimension appears twice."""
    dims = {name: _result(name, insufficient_evidence=True, facts={}) for name in ("a", "b", "c", "d")}
    intelligence = _intelligence(dims)
    package = assemble_context_package(intelligence, player_id=None, target_event_timestamp=TARGET_TS)
    all_classified = set(package.joined_dimensions) | set(package.partial_dimensions) | set(package.unavailable_dimensions)
    assert all_classified == set(dims.keys())
    assert set(package.dimension_completeness.keys()) == set(dims.keys())


def test_known_limitations_aggregates_real_reasons_deduplicated():
    intelligence = _intelligence({
        "weather": _result("weather", insufficient_evidence=True, facts={}, reason="no real WeatherAPI observation exists"),
        "venue": _result("venue", insufficient_evidence=True, facts={}, reason="no real WeatherAPI observation exists"),  # same reason, deliberately
        "market": _result("market", insufficient_evidence=False, facts={"x": 1}, reason=None),  # joined -- no reason to aggregate
    })
    package = assemble_context_package(intelligence, player_id=None, target_event_timestamp=TARGET_TS)
    assert package.known_limitations == ("no real WeatherAPI observation exists",)  # deduplicated, not doubled


def test_dimension_completeness_carries_sample_size_and_provenance():
    prov = (ProvenanceRef(table="weather_snapshots", source="weatherapi", row_count=3, earliest_at=None, latest_at=None),)
    intelligence = _intelligence({"weather": _result("weather", insufficient_evidence=False, facts={"x": 1}, sample_size=3, provenance=prov)})
    package = assemble_context_package(intelligence, player_id=None, target_event_timestamp=TARGET_TS)
    dc = package.dimension_completeness["weather"]
    assert dc.sample_size == 3
    assert dc.provenance == prov


def test_target_event_timestamp_and_player_id_are_carried_verbatim():
    intelligence = _intelligence({"weather": _result("weather", insufficient_evidence=True, facts={})})
    package = assemble_context_package(intelligence, player_id="jsn-id", target_event_timestamp=TARGET_TS)
    assert package.player_id == "jsn-id"
    assert package.target_event_timestamp == TARGET_TS
    assert package.game_id == GAME_ID


def test_to_json_serializes_cleanly_and_every_value_is_one_of_the_three_states():
    intelligence = _intelligence({
        "weather": _result("weather", insufficient_evidence=False, facts={"x": 1}),
        "injuries": _result("injuries", insufficient_evidence=True, facts={}, reason="blocked"),
    })
    package = assemble_context_package(intelligence, player_id=None, target_event_timestamp=TARGET_TS)
    payload = package.to_json()
    assert payload["game_id"] == GAME_ID
    assert payload["target_event_timestamp"] == TARGET_TS
    for name, dc in payload["dimension_completeness"].items():
        assert dc["completeness"] in COMPLETENESS_VALUES


def test_no_prediction_or_confidence_field_exists_anywhere_on_the_package():
    """Structural proof: this is evidence completeness, never a
    prediction score -- no field on ContextPackage (or its per-dimension
    detail type) even resembles one."""
    field_names = {f.name for f in dataclasses.fields(ContextPackage)}
    forbidden_substrings = ("confidence", "probability", "prediction", "score")
    for name in field_names:
        assert not any(s in name.lower() for s in forbidden_substrings), f"unexpected field {name!r} on ContextPackage"
