"""Tests for app.features.adaptive_weighting (Milestone 5.5) -- the
deterministic weighting engine. Pure functions, no I/O."""
from __future__ import annotations

import pytest

from app.features.adaptive_weighting import (
    ADAPTIVE_WEIGHT_LEARNING_RATE,
    ADAPTIVE_WEIGHT_MAX_CHANGE_FRACTION,
    ADAPTIVE_WEIGHT_MIN_SAMPLE_SIZE,
    ADAPTIVE_WEIGHT_MIN_WINDOW_DAYS,
    WEIGHTING_VERSION,
    EvaluationWindowTooShortError,
    ObservationInput,
    aggregate_roi,
    check_sample_size_guardrail,
    classify_and_price_observation,
    clamp_to_max_change,
    committee_average_roi,
    compute_performance_delta,
    compute_raw_proposed_weight,
    leg_notional_pnl,
    validate_evaluation_window,
)


def test_policy_constants_are_frozen_at_approved_values():
    assert WEIGHTING_VERSION == "v1"
    assert ADAPTIVE_WEIGHT_LEARNING_RATE == 0.25
    assert ADAPTIVE_WEIGHT_MAX_CHANGE_FRACTION == 0.10
    assert ADAPTIVE_WEIGHT_MIN_SAMPLE_SIZE == 200
    assert ADAPTIVE_WEIGHT_MIN_WINDOW_DAYS == 90


# --- leg_notional_pnl -------------------------------------------------------


def test_leg_notional_pnl_win_uses_decimal_odds_profit():
    assert leg_notional_pnl(outcome="WIN", decimal_odds=1.8) == pytest.approx(0.8)


def test_leg_notional_pnl_loss_is_flat_negative_one():
    assert leg_notional_pnl(outcome="LOSS", decimal_odds=1.8) == -1.0


def test_leg_notional_pnl_rejects_non_terminal_outcome():
    with pytest.raises(ValueError):
        leg_notional_pnl(outcome="PUSH", decimal_odds=1.8)


# --- classify_and_price_observation -----------------------------------------


def _obs(*, lean: str, realized: str, outcome: str, decimal_odds: float = 1.8) -> ObservationInput:
    return ObservationInput(
        recommendation_leg_grade_event_id="grade-1", directional_lean=lean, realized_direction=realized,
        outcome=outcome, decimal_odds=decimal_odds,
    )


def test_classify_correct_on_win_gets_exact_leg_pnl():
    # correct + WIN: this agent's lean equals the recommended (winning)
    # side -- its real price IS the graded leg's own decimal_odds.
    result = classify_and_price_observation(_obs(lean="home", realized="home", outcome="WIN", decimal_odds=1.8))
    assert result.classification == "correct"
    assert result.notional_pnl == pytest.approx(0.8)


def test_classify_underperforming_on_win_gets_flat_negative_unit_proxy():
    # underperforming + WIN: this agent leaned the side that lost, whose
    # real price is unknown -- flat -1.0 proxy, NOT -(decimal_odds - 1).
    result = classify_and_price_observation(_obs(lean="away", realized="home", outcome="WIN", decimal_odds=1.8))
    assert result.classification == "underperforming"
    assert result.notional_pnl == pytest.approx(-1.0)


def test_classify_correct_on_loss_gets_flat_positive_unit_proxy():
    # correct + LOSS: this agent leaned the side that actually won, but
    # that side is not the graded (recommended) leg, so its real price
    # is unknown -- flat +1.0 proxy.
    result = classify_and_price_observation(_obs(lean="away", realized="away", outcome="LOSS"))
    assert result.classification == "correct"
    assert result.notional_pnl == pytest.approx(1.0)


def test_classify_underperforming_on_loss_gets_exact_leg_pnl():
    # underperforming + LOSS: this agent's lean equals the recommended
    # (losing) side -- its real price IS the graded leg's own realized loss.
    result = classify_and_price_observation(_obs(lean="home", realized="away", outcome="LOSS"))
    assert result.classification == "underperforming"
    assert result.notional_pnl == pytest.approx(-1.0)


def test_classify_off_axis_lean_is_not_classifiable():
    assert classify_and_price_observation(_obs(lean="over", realized="home", outcome="WIN")) is None


def test_classify_none_lean_is_not_classifiable():
    assert classify_and_price_observation(_obs(lean="none", realized="home", outcome="WIN")) is None


# --- aggregate_roi / committee_average_roi ----------------------------------


def test_aggregate_roi_none_for_zero_observations():
    assert aggregate_roi([]) is None


def test_aggregate_roi_averages_notional_pnl():
    obs = [
        classify_and_price_observation(_obs(lean="home", realized="home", outcome="WIN", decimal_odds=2.0)),
        classify_and_price_observation(_obs(lean="home", realized="away", outcome="LOSS")),
    ]
    # pnl: +1.0, -1.0 -> average 0.0
    assert aggregate_roi(obs) == pytest.approx(0.0)


def test_committee_average_roi_excludes_none_entries():
    assert committee_average_roi([0.1, None, 0.3, None]) == pytest.approx(0.2)


def test_committee_average_roi_none_when_all_none():
    assert committee_average_roi([None, None]) is None


# --- performance_delta / raw weight / clamp ---------------------------------


def test_performance_delta_none_when_either_input_missing():
    assert compute_performance_delta(agent_roi=None, committee_average_roi_value=0.1) is None
    assert compute_performance_delta(agent_roi=0.1, committee_average_roi_value=None) is None


def test_performance_delta_is_agent_minus_committee():
    assert compute_performance_delta(agent_roi=0.30, committee_average_roi_value=0.10) == pytest.approx(0.20)


def test_raw_proposed_weight_formula_matches_volume_4_section_6_1():
    # new_weight = current_weight * (1 + learning_rate * performance_delta)
    # 1.0 * (1 + 0.25 * 0.20) = 1.05 -- Mac's own worked example.
    result = compute_raw_proposed_weight(current_weight=1.0, learning_rate=0.25, performance_delta=0.20)
    assert result == pytest.approx(1.05)


def test_raw_proposed_weight_none_when_performance_delta_none():
    assert compute_raw_proposed_weight(current_weight=1.0, learning_rate=0.25, performance_delta=None) is None


def test_clamp_does_not_alter_a_change_within_bounds():
    assert clamp_to_max_change(current_weight=1.0, raw_proposed_weight=1.05) == pytest.approx(1.05)


def test_clamp_caps_a_raw_increase_beyond_ten_percent():
    # performance_delta = +0.40 -> raw = 1.0 * (1 + 0.25*0.40) = 1.10 -- Mac's own example, already at the cap.
    raw = compute_raw_proposed_weight(current_weight=1.0, learning_rate=0.25, performance_delta=0.40)
    assert clamp_to_max_change(current_weight=1.0, raw_proposed_weight=raw) == pytest.approx(1.10)


def test_clamp_caps_a_larger_raw_increase_at_exactly_ten_percent():
    raw = compute_raw_proposed_weight(current_weight=1.0, learning_rate=0.25, performance_delta=1.0)  # raw = 1.25
    assert clamp_to_max_change(current_weight=1.0, raw_proposed_weight=raw) == pytest.approx(1.10)


def test_clamp_caps_a_raw_decrease_at_negative_ten_percent():
    raw = compute_raw_proposed_weight(current_weight=1.0, learning_rate=0.25, performance_delta=-1.0)  # raw = 0.75
    assert clamp_to_max_change(current_weight=1.0, raw_proposed_weight=raw) == pytest.approx(0.90)


def test_clamp_none_when_raw_none():
    assert clamp_to_max_change(current_weight=1.0, raw_proposed_weight=None) is None


# --- guardrails --------------------------------------------------------------


def test_sample_size_guardrail_199_fails_200_passes():
    assert check_sample_size_guardrail(199) is False
    assert check_sample_size_guardrail(200) is True


def test_window_guardrail_rejects_narrower_than_90_days():
    with pytest.raises(EvaluationWindowTooShortError):
        validate_evaluation_window(window_start_days_before_end=89)


def test_window_guardrail_accepts_90_days_exactly():
    validate_evaluation_window(window_start_days_before_end=90)  # must not raise
