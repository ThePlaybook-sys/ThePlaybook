"""Tests for app.context_intelligence.scoring (Phase 8.1 Foundation
Pass) -- pure deterministic math, no I/O."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.context_intelligence.scoring import (
    confidence_score,
    dispersion,
    numeric_similarity,
    recency_weight,
    weighted_mean,
)


def test_recency_weight_is_one_at_zero_age():
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    assert recency_weight(now, now=now) == 1.0


def test_recency_weight_halves_at_half_life():
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    observed = now - timedelta(days=14)
    assert abs(recency_weight(observed, now=now, half_life_days=14.0) - 0.5) < 1e-9


def test_recency_weight_never_negative_for_future_timestamp():
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    future = now + timedelta(days=5)
    assert recency_weight(future, now=now) == 1.0


def test_numeric_similarity_identical_is_one():
    assert numeric_similarity(60.0, 60.0, scale=25.0) == 1.0


def test_numeric_similarity_beyond_scale_is_zero():
    assert numeric_similarity(0.0, 100.0, scale=25.0) == 0.0


def test_weighted_mean_returns_none_for_zero_total_weight():
    assert weighted_mean([(1.0, 0.0), (2.0, 0.0)]) is None


def test_weighted_mean_returns_none_for_empty_input():
    assert weighted_mean([]) is None


def test_dispersion_zero_for_identical_values():
    assert dispersion([5.0, 5.0, 5.0]) == 0.0


def test_dispersion_zero_for_fewer_than_two_values():
    assert dispersion([5.0]) == 0.0


def test_dispersion_high_for_scattered_values():
    assert dispersion([0.0, 1.0]) > 0.5


def test_confidence_score_is_zero_when_any_factor_is_zero():
    assert confidence_score(sample_size=0, avg_recency_weight=1.0, consistency=1.0) == 0.0
    assert confidence_score(sample_size=8, avg_recency_weight=0.0, consistency=1.0) == 0.0
    assert confidence_score(sample_size=8, avg_recency_weight=1.0, consistency=0.0) == 0.0


def test_confidence_score_caps_at_one():
    assert confidence_score(sample_size=1000, avg_recency_weight=1.0, consistency=1.0) == 1.0
