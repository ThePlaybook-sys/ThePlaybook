"""Tests for app.features.kelly (Milestone 4.6, Decision D). Hand-computed
examples, not derived from the module under test."""
from __future__ import annotations

import pytest

from app.features.kelly import InvalidKellyInputError, compute_full_kelly, compute_stake


def test_full_kelly_hand_calculated():
    # p=0.60, decimal_odds=1.8: b=0.8, q=0.4, full=(0.8*0.6-0.4)/0.8=0.1
    assert compute_full_kelly(0.60, 1.8) == pytest.approx(0.1)


def test_full_kelly_equals_ev_per_dollar_over_b():
    # Algebraic identity asserted directly, per the module's own docstring.
    p, decimal_odds = 0.60, 1.8
    b = decimal_odds - 1
    ev_per_dollar = p * decimal_odds - 1
    assert compute_full_kelly(p, decimal_odds) == pytest.approx(ev_per_dollar / b)


def test_negative_edge_full_kelly_is_negative():
    # p=0.30, decimal_odds=1.8: b=0.8, q=0.7, full=(0.8*0.3-0.7)/0.8=-0.575
    assert compute_full_kelly(0.30, 1.8) == pytest.approx(-0.575)


def test_invalid_probability_raises():
    with pytest.raises(InvalidKellyInputError):
        compute_full_kelly(1.5, 1.8)


def test_non_positive_net_odds_raises():
    with pytest.raises(InvalidKellyInputError):
        compute_full_kelly(0.60, 1.0)  # b = 0


# --- compute_stake ---


def test_quarter_kelly_and_stake_for_each_risk_tolerance():
    # full=0.1, quarter=0.025
    conservative = compute_stake(0.60, 1.8, bankroll=1000.0, risk_tolerance="conservative")
    moderate = compute_stake(0.60, 1.8, bankroll=1000.0, risk_tolerance="moderate")
    aggressive = compute_stake(0.60, 1.8, bankroll=1000.0, risk_tolerance="aggressive")

    for result in (conservative, moderate, aggressive):
        assert result.full_kelly_fraction == pytest.approx(0.1)
        assert result.quarter_kelly_fraction == pytest.approx(0.025)

    assert conservative.stake == pytest.approx(1000 * 0.025 * 0.50)  # 12.50
    assert moderate.stake == pytest.approx(1000 * 0.025 * 0.75)  # 18.75
    assert aggressive.stake == pytest.approx(1000 * 0.025 * 1.00)  # 25.00
    assert aggressive.stake < 1000 * 0.25  # never exceeds quarter-Kelly ceiling


def test_negative_edge_yields_zero_stake_never_negative():
    result = compute_stake(0.30, 1.8, bankroll=1000.0, risk_tolerance="aggressive")
    assert result.full_kelly_fraction < 0
    assert result.quarter_kelly_fraction == 0.0
    assert result.stake == 0.0


def test_zero_edge_yields_zero_stake():
    p = 100 / 225 + 25 / 225  # arbitrary; use exact breakeven for decimal_odds=1.8 -> p=1/1.8
    p = 1 / 1.8
    result = compute_stake(p, 1.8, bankroll=1000.0, risk_tolerance="moderate")
    assert result.stake == pytest.approx(0.0, abs=0.01)


def test_missing_bankroll_yields_null_stake_but_kelly_fractions_still_populated():
    result = compute_stake(0.60, 1.8, bankroll=None, risk_tolerance="moderate")
    assert result.stake is None
    assert result.full_kelly_fraction == pytest.approx(0.1)
    assert result.quarter_kelly_fraction == pytest.approx(0.025)


def test_zero_bankroll_yields_null_stake():
    result = compute_stake(0.60, 1.8, bankroll=0.0, risk_tolerance="moderate")
    assert result.stake is None


def test_negative_bankroll_yields_null_stake():
    result = compute_stake(0.60, 1.8, bankroll=-50.0, risk_tolerance="moderate")
    assert result.stake is None


def test_missing_risk_tolerance_yields_null_multiplier_and_stake():
    result = compute_stake(0.60, 1.8, bankroll=1000.0, risk_tolerance=None)
    assert result.risk_tolerance_multiplier is None
    assert result.stake is None


def test_unknown_risk_tolerance_yields_null_multiplier_and_stake():
    result = compute_stake(0.60, 1.8, bankroll=1000.0, risk_tolerance="reckless")
    assert result.risk_tolerance_multiplier is None
    assert result.stake is None


def test_missing_decimal_odds_degrades_every_field_to_none():
    result = compute_stake(0.60, None, bankroll=1000.0, risk_tolerance="moderate")
    assert result.full_kelly_fraction is None
    assert result.quarter_kelly_fraction is None
    assert result.risk_tolerance_multiplier is None
    assert result.stake is None
