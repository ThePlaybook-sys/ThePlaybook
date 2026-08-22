"""Tests for app.features.probability (Milestone 4.6, Decision C).
Hand-computed examples, not derived from the module under test."""
from __future__ import annotations

import pytest

from app.features.probability import InvalidOddsError, american_to_decimal, implied_probability


def test_negative_odds_to_decimal():
    # -125: 1 + 100/125 = 1.8
    assert american_to_decimal(-125) == pytest.approx(1.8)


def test_positive_odds_to_decimal():
    # +150: 1 + 150/100 = 2.5
    assert american_to_decimal(150) == pytest.approx(2.5)


def test_negative_odds_implied_probability():
    # -125: 125 / (125+100) = 0.555555...
    assert implied_probability(-125) == pytest.approx(125 / 225)


def test_positive_odds_implied_probability():
    # +150: 100 / (150+100) = 0.4
    assert implied_probability(150) == pytest.approx(0.4)


def test_even_money_positive_and_negative_agree():
    # +100 and -100 are both even money -- both imply exactly 0.5
    assert implied_probability(100) == pytest.approx(0.5)
    assert implied_probability(-100) == pytest.approx(0.5)


def test_zero_odds_rejected_for_decimal():
    with pytest.raises(InvalidOddsError):
        american_to_decimal(0)


def test_zero_odds_rejected_for_implied_probability():
    with pytest.raises(InvalidOddsError):
        implied_probability(0)
