"""Tests for app.features.consensus (Milestone 4.7, Decisions H/I/J).
Hand-computed examples, not derived from the module under test."""
from __future__ import annotations

import pytest

from app.features.consensus import (
    CandidateDirectionError,
    apply_confidence_adjustment,
    compute_consensus,
    is_below_confidence_floor,
    lean_factor,
    resolve_candidate_direction,
    should_trigger_elite_second_pass,
)


# --- resolve_candidate_direction ---


def test_moneyline_resolves_home():
    assert resolve_candidate_direction(market_type="moneyline", selection="KC", home_team="KC", away_team="BAL") == "home"


def test_moneyline_resolves_away():
    assert resolve_candidate_direction(market_type="moneyline", selection="BAL", home_team="KC", away_team="BAL") == "away"


def test_spread_resolves_same_as_moneyline():
    assert resolve_candidate_direction(market_type="spread", selection="KC", home_team="KC", away_team="BAL") == "home"


def test_moneyline_selection_matching_neither_team_raises():
    with pytest.raises(CandidateDirectionError):
        resolve_candidate_direction(market_type="moneyline", selection="Buffalo Bills", home_team="KC", away_team="BAL")


def test_total_resolves_over_and_under():
    assert resolve_candidate_direction(market_type="total", selection="Over", home_team="KC", away_team="BAL") == "over"
    assert resolve_candidate_direction(market_type="total", selection="Under", home_team="KC", away_team="BAL") == "under"


def test_total_invalid_selection_raises():
    with pytest.raises(CandidateDirectionError):
        resolve_candidate_direction(market_type="total", selection="KC", home_team="KC", away_team="BAL")


def test_prop_market_type_returns_none_not_malformed():
    assert resolve_candidate_direction(market_type="prop", selection="Mahomes Over 1.5 TDs", home_team="KC", away_team="BAL") is None


# --- lean_factor: the exact three-state rule ---


def test_matching_lean_is_support():
    assert lean_factor("home", "home") == 1.0


def test_opposite_lean_on_same_axis_is_opposition():
    assert lean_factor("away", "home") == 0.3
    assert lean_factor("under", "over") == 0.3


def test_none_lean_is_not_support_or_opposition():
    assert lean_factor("none", "home") is None


def test_off_axis_lean_is_not_support_or_opposition():
    # candidate is a totals (over/under axis); agent leans home/away -- a different axis entirely
    assert lean_factor("home", "over") is None
    assert lean_factor("over", "home") is None


def test_no_candidate_direction_means_no_agent_can_vote():
    assert lean_factor("home", None) is None


# --- compute_consensus ---


def _row(directional_lean: str, confidence: float, weight_applied: float, evidence_classification: str = "data_backed") -> dict:
    return {
        "directional_lean": directional_lean,
        "confidence": confidence,
        "weight_applied": weight_applied,
        "evidence_classification": evidence_classification,
    }


def test_hand_calculated_aggregate_confidence_and_variance():
    rows = [
        _row("home", 0.7, 1.0, "data_backed"),
        _row("away", 0.6, 0.5, "assumption"),  # effective_weight = 0.5*0.5 = 0.25, factor = 0.3 (opposes "home")
    ]
    result = compute_consensus(rows, candidate_direction="home")
    # aggregate = (0.7*1.0*1.0 + 0.6*0.25*0.3) / (1.0+0.25) = 0.745/1.25 = 0.596
    assert result.aggregate_confidence == pytest.approx(0.596)
    # factors=[1.0, 0.3], mean=0.65, variance=((0.35)^2+(0.35)^2)/2=0.1225
    assert result.agreement_variance == pytest.approx(0.1225)
    assert result.voting_agent_count == 2
    assert result.non_voting_agent_count == 0


def test_assumption_discount_does_not_mutate_input_row():
    row = _row("home", 0.7, 1.0, "assumption")
    compute_consensus([row], candidate_direction="home")
    assert row["weight_applied"] == 1.0  # stored weight_applied is never mutated


def test_none_lean_excluded_from_numerator_and_denominator():
    voting_only = compute_consensus([_row("home", 0.7, 1.0)], candidate_direction="home")
    with_none_agent = compute_consensus([_row("home", 0.7, 1.0), _row("none", 0.9, 5.0)], candidate_direction="home")
    assert with_none_agent.aggregate_confidence == voting_only.aggregate_confidence
    assert with_none_agent.voting_agent_count == 1
    assert with_none_agent.non_voting_agent_count == 1


def test_off_axis_agent_excluded_from_totals_candidate_consensus():
    rows = [_row("over", 0.8, 1.0), _row("home", 0.99, 10.0)]  # the home lean is off-axis for a totals candidate
    result = compute_consensus(rows, candidate_direction="over")
    assert result.aggregate_confidence == pytest.approx(0.8)
    assert result.non_voting_agent_count == 1


def test_zero_agent_rows_yields_none_not_fabricated():
    result = compute_consensus([], candidate_direction="home")
    assert result.aggregate_confidence is None
    assert result.agreement_variance is None
    assert result.voting_agent_count == 0
    assert result.non_voting_agent_count == 0


def test_all_agents_non_voting_yields_none():
    result = compute_consensus([_row("none", 0.7, 1.0), _row("none", 0.5, 1.0)], candidate_direction="home")
    assert result.aggregate_confidence is None
    assert result.non_voting_agent_count == 2


def test_single_voting_agent_has_zero_variance():
    result = compute_consensus([_row("home", 0.7, 1.0)], candidate_direction="home")
    assert result.agreement_variance == pytest.approx(0.0)


def test_prop_candidate_direction_none_yields_undefined_consensus():
    rows = [_row("home", 0.7, 1.0), _row("over", 0.6, 1.0)]
    result = compute_consensus(rows, candidate_direction=None)
    assert result.aggregate_confidence is None
    assert result.non_voting_agent_count == 2


# --- apply_confidence_adjustment / is_below_confidence_floor ---


def test_confidence_adjustment_never_exceeds_starting_value():
    assert apply_confidence_adjustment(0.7, -0.1) == pytest.approx(0.6)
    assert apply_confidence_adjustment(0.7, 0.0) == pytest.approx(0.7)


def test_confidence_adjustment_floors_at_zero():
    assert apply_confidence_adjustment(0.05, -0.5) == 0.0


def test_confidence_floor_exact_boundary():
    assert is_below_confidence_floor(0.5499) is True
    assert is_below_confidence_floor(0.5500) is False
    assert is_below_confidence_floor(0.5501) is False


# --- should_trigger_elite_second_pass ---
# Milestone 4.8, Decision L: ELITE_VARIANCE_THRESHOLD corrected from the
# structurally-unreachable 0.25 (Volume 4 Section 4.3's original value)
# to 0.10 -- reachable from real compute_consensus output. A 70/30
# voting split (agreement_variance = 0.1029, hand-calculated) is the
# smallest real-world split that now triggers; 75/25 (0.0919) does not.
# These tests exercise the trigger LOGIC directly with supplied variance
# values (both boundary values and the real hand-calculated 70/30 figure).


def test_exactly_at_threshold_does_not_trigger():
    assert should_trigger_elite_second_pass(0.10, "elite") is False


def test_above_threshold_and_elite_triggers():
    assert should_trigger_elite_second_pass(0.11, "elite") is True


def test_70_30_split_variance_triggers_for_elite_tier():
    # p=0.7: agreement_variance = 0.49 * 0.7 * 0.3 = 0.1029 -- the
    # smallest real head-count split that now crosses the threshold.
    assert should_trigger_elite_second_pass(0.1029, "elite") is True


def test_75_25_split_variance_does_not_trigger():
    # p=0.75: agreement_variance = 0.49 * 0.75 * 0.25 = 0.091875 --
    # ordinary disagreement, deliberately below the threshold.
    assert should_trigger_elite_second_pass(0.091875, "elite") is False


def test_above_threshold_but_free_tier_does_not_trigger():
    assert should_trigger_elite_second_pass(0.11, "free") is False


def test_above_threshold_but_pro_tier_does_not_trigger():
    assert should_trigger_elite_second_pass(0.11, "pro") is False


def test_above_threshold_but_syndicate_tier_does_not_trigger():
    assert should_trigger_elite_second_pass(0.11, "syndicate") is False


def test_above_threshold_but_none_tier_does_not_trigger():
    assert should_trigger_elite_second_pass(0.11, None) is False


def test_none_variance_never_triggers_even_with_elite_tier():
    assert should_trigger_elite_second_pass(None, "elite") is False


def test_below_threshold_elite_tier_does_not_trigger():
    assert should_trigger_elite_second_pass(0.05, "elite") is False
