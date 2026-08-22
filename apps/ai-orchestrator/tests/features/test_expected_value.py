"""Tests for app.features.expected_value (Milestone 4.6, Decision C).
Hand-computed examples, not derived from the module under test."""
from __future__ import annotations

import pytest

from app.features.expected_value import compute_ev
from app.features.probability import InvalidOddsError


def test_positive_edge_hand_calculated():
    # p=0.60, odds=-125: decimal=1.8, implied=125/225=0.555556,
    # edge=0.6-0.555556=0.044444, ev=0.6*1.8-1=0.08
    result = compute_ev(0.60, -125)
    assert result.decimal_odds == pytest.approx(1.8)
    assert result.raw_implied_probability == pytest.approx(125 / 225)
    assert result.raw_probability_edge == pytest.approx(0.6 - 125 / 225)
    assert result.ev_per_dollar == pytest.approx(0.08)


def test_negative_edge_hand_calculated():
    # p=0.40, odds=-125: decimal=1.8, implied=0.555556,
    # edge=0.4-0.555556=-0.155556, ev=0.4*1.8-1=-0.28
    result = compute_ev(0.40, -125)
    assert result.raw_probability_edge == pytest.approx(0.4 - 125 / 225)
    assert result.ev_per_dollar == pytest.approx(-0.28)


def test_zero_edge_at_exact_breakeven():
    # p exactly equal to the implied probability -> zero edge, zero EV
    p = 125 / 225
    result = compute_ev(p, -125)
    assert result.raw_probability_edge == pytest.approx(0.0, abs=1e-9)
    assert result.ev_per_dollar == pytest.approx(0.0, abs=1e-9)


def test_missing_odds_degrades_every_field_to_none():
    result = compute_ev(0.55, None)
    assert result.decimal_odds is None
    assert result.raw_implied_probability is None
    assert result.raw_probability_edge is None
    assert result.ev_per_dollar is None


def test_invalid_odds_raises_not_silently_absorbed():
    with pytest.raises(InvalidOddsError):
        compute_ev(0.55, 0)


def test_invalid_probability_raises():
    with pytest.raises(ValueError):
        compute_ev(1.5, -125)
