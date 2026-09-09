"""Unit tests for the Phase 8.5 Pass 1 deterministic request pipeline
(app.request_intent). Every stage here is a pure function -- no I/O, no
mocking needed, matching this project's fixture-first discipline."""
from __future__ import annotations

from app.request_intent import (
    ExecutionAction,
    RawUserInput,
    RequestType,
    SelectionMode,
    build_execution_plan,
    normalize_request,
    resolve_intent,
)


def _resolve(text: str):
    return resolve_intent(normalize_request(RawUserInput(text=text)))


def test_normalize_request_lowercases_and_strips():
    normalized = normalize_request(RawUserInput(text="  What's MANSA's Highest Confidence Pick?  "))
    assert normalized.normalized_text == "what's mansa's highest confidence pick?"
    assert normalized.raw_text == "  What's MANSA's Highest Confidence Pick?  "


def test_resolve_intent_recognizes_highest_confidence_phrasing():
    intent = _resolve("What's MANSA's highest-confidence pick today?")
    assert intent.request_type == RequestType.RECOMMENDATION_LOOKUP
    assert intent.selection_mode == SelectionMode.HIGHEST_CONFIDENCE
    assert intent.time_scope == "today"
    assert intent.unresolved_reason is None


def test_resolve_intent_recognizes_equivalent_nl_phrasings():
    for phrase in (
        "give me your most confident pick",
        "what's your strongest confidence play today",
        "highest confidence pick please",
    ):
        intent = _resolve(phrase)
        assert intent.request_type == RequestType.RECOMMENDATION_LOOKUP, phrase
        assert intent.selection_mode == SelectionMode.HIGHEST_CONFIDENCE, phrase


def test_resolve_intent_never_treats_safest_as_highest_confidence():
    """HQ's explicit terminology guardrail: 'safest'/'guaranteed'/'most
    likely to win' must never resolve to the highest-confidence
    selection mode."""
    for phrase in ("what's the safest pick today", "give me a guaranteed win", "what's most likely to win"):
        intent = _resolve(phrase)
        assert intent.request_type == RequestType.UNSUPPORTED, phrase
        assert intent.selection_mode is None, phrase
        assert "highest-confidence" in intent.unresolved_reason


def test_resolve_intent_recognizes_other_known_unsupported_requests():
    for phrase in ("build me a parlay", "give me conservative options", "what's the best pick"):
        intent = _resolve(phrase)
        assert intent.request_type == RequestType.UNSUPPORTED, phrase
        assert intent.unresolved_reason


def test_resolve_intent_recognizes_highest_value_phrasing():
    """Phase 8.5 Pass 2: 'highest value'/'highest-value' were
    deliberately UNSUPPORTED in Pass 1 -- now genuinely supported,
    per the verified ev_per_dollar metric."""
    intent = _resolve("What's MANSA's highest-value pick today?")
    assert intent.request_type == RequestType.RECOMMENDATION_LOOKUP
    assert intent.selection_mode == SelectionMode.HIGHEST_VALUE
    assert intent.time_scope == "today"
    assert intent.unresolved_reason is None


def test_resolve_intent_recognizes_equivalent_value_phrasings():
    for phrase in ("what's the highest value?", "show me the best value pick today", "highest value today"):
        intent = _resolve(phrase)
        assert intent.request_type == RequestType.RECOMMENDATION_LOOKUP, phrase
        assert intent.selection_mode == SelectionMode.HIGHEST_VALUE, phrase


def test_resolve_intent_best_pick_never_treated_as_highest_value_or_confidence():
    """HQ's explicit instruction: 'best pick' remains unsupported and
    is never a synonym for either selection mode -- and 'best value
    pick' must not collide with the 'best pick' substring."""
    intent = _resolve("what's the best pick today")
    assert intent.request_type == RequestType.UNSUPPORTED
    assert intent.selection_mode is None

    # Substring-collision proof: "best value pick" contains "best
    # value" (matches HIGHEST_VALUE) but never "best pick" as a
    # contiguous substring, so it must resolve to highest_value, not
    # unsupported.
    value_intent = _resolve("show me the best value pick today")
    assert value_intent.request_type == RequestType.RECOMMENDATION_LOOKUP
    assert value_intent.selection_mode == SelectionMode.HIGHEST_VALUE


def test_resolve_intent_highest_value_and_highest_confidence_do_not_collide():
    confidence_intent = _resolve("what's MANSA's highest confidence pick today")
    value_intent = _resolve("what's MANSA's highest value pick today")
    assert confidence_intent.selection_mode == SelectionMode.HIGHEST_CONFIDENCE
    assert value_intent.selection_mode == SelectionMode.HIGHEST_VALUE


def test_resolve_intent_returns_ambiguous_for_unrecognized_text():
    intent = _resolve("what is the weather like tomorrow")
    assert intent.request_type == RequestType.AMBIGUOUS
    assert intent.selection_mode is None
    assert intent.unresolved_reason


def test_resolve_intent_returns_ambiguous_for_empty_text():
    intent = _resolve("   ")
    assert intent.request_type == RequestType.AMBIGUOUS
    assert "empty" in intent.unresolved_reason.lower()


def test_build_execution_plan_for_recommendation_lookup():
    intent = _resolve("highest confidence pick today")
    plan = build_execution_plan(intent)
    assert plan.action == ExecutionAction.RETRIEVE_HIGHEST_CONFIDENCE_TODAY
    assert plan.reason is None


def test_build_execution_plan_for_highest_value_lookup():
    intent = _resolve("highest value pick today")
    plan = build_execution_plan(intent)
    assert plan.action == ExecutionAction.RETRIEVE_HIGHEST_VALUE_TODAY
    assert plan.reason is None


def test_build_execution_plan_for_unsupported():
    intent = _resolve("what's the safest pick")
    plan = build_execution_plan(intent)
    assert plan.action == ExecutionAction.REJECT_UNSUPPORTED
    assert plan.reason == intent.unresolved_reason


def test_build_execution_plan_for_ambiguous():
    intent = _resolve("hello there")
    plan = build_execution_plan(intent)
    assert plan.action == ExecutionAction.REJECT_AMBIGUOUS
    assert plan.reason == intent.unresolved_reason
