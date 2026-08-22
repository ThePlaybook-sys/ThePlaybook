"""Tests for app.features.risk (Milestone 4.6, Decision E)."""
from __future__ import annotations

import pytest

from app.features.risk import build_risk_assessment, compute_outcome_variance


def test_outcome_variance_hand_calculated():
    # p=0.6: 0.6*(1-0.6) = 0.24
    assert compute_outcome_variance(0.6) == pytest.approx(0.24)


def test_outcome_variance_at_extremes_is_zero():
    assert compute_outcome_variance(0.0) == pytest.approx(0.0)
    assert compute_outcome_variance(1.0) == pytest.approx(0.0)


def test_outcome_variance_is_maximal_at_half():
    assert compute_outcome_variance(0.5) == pytest.approx(0.25)


def test_missing_probability_yields_none_variance():
    assert compute_outcome_variance(None) is None


def test_invalid_probability_raises():
    with pytest.raises(ValueError):
        compute_outcome_variance(1.5)


def test_historical_bet_type_variance_always_none():
    assessment = build_risk_assessment(0.6)
    assert assessment.historical_bet_type_variance is None
    assert assessment.bernoulli_outcome_variance == pytest.approx(0.24)


def test_risk_assessment_degrades_fully_when_probability_missing():
    assessment = build_risk_assessment(None)
    assert assessment.bernoulli_outcome_variance is None
    assert assessment.historical_bet_type_variance is None
