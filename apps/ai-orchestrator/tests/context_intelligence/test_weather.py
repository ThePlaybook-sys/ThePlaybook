"""Tests for app.context_intelligence.weather (Phase 8.1 Foundation
Pass) -- pure function, no I/O."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.context_intelligence.weather import compute_weather_context

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def _real_row(*, game_id, is_dome, temp, wind, precip, age_days):
    ts = (NOW - timedelta(days=age_days)).isoformat()
    return {
        "game_id": game_id,
        "weather_data": {
            "source": "weatherapi",
            "is_dome": is_dome,
            "temperature_f": temp,
            "wind_mph": wind,
            "precipitation_pct": precip,
            "conditions": "Clear",
            "observed_at": ts,
        },
        "captured_at": ts,
    }


def _fixture_row(*, game_id):
    return {
        "game_id": game_id,
        "weather_data": {"temp_f": 72, "wind_mph": 8, "condition": "clear", "precipitation_pct": 5},
        "captured_at": (NOW - timedelta(days=60)).isoformat(),
    }


def test_no_real_row_for_target_game_is_insufficient_evidence():
    rows = [_real_row(game_id="other", is_dome=False, temp=60, wind=5, precip=10, age_days=1)]
    result = compute_weather_context(rows, game_id="target", now=NOW)
    assert result.insufficient_evidence is True
    assert result.sample_size == 0
    assert result.similarity_score is None
    assert result.confidence is None


def test_fixture_row_never_counted_as_real():
    rows = [_fixture_row(game_id="target")]
    result = compute_weather_context(rows, game_id="target", now=NOW)
    assert result.insufficient_evidence is True
    assert result.insufficient_evidence_reason == "no real WeatherAPI observation exists for this game yet"


def test_sparse_history_below_floor_is_insufficient_evidence():
    rows = [
        _real_row(game_id="target", is_dome=False, temp=60, wind=5, precip=10, age_days=1),
        _real_row(game_id="only_one_comparable", is_dome=False, temp=61, wind=5, precip=11, age_days=1),
    ]
    result = compute_weather_context(rows, game_id="target", now=NOW)
    assert result.sample_size == 1
    assert result.insufficient_evidence is True
    assert "minimum 2 required" in result.insufficient_evidence_reason


def test_sufficient_evidence_consistent_pool_yields_high_similarity_and_real_confidence():
    rows = [
        _real_row(game_id="target", is_dome=False, temp=60, wind=5, precip=10, age_days=1),
        _real_row(game_id="c1", is_dome=False, temp=62, wind=6, precip=12, age_days=2),
        _real_row(game_id="c2", is_dome=False, temp=58, wind=4, precip=8, age_days=3),
    ]
    result = compute_weather_context(rows, game_id="target", now=NOW)
    assert result.insufficient_evidence is False
    assert result.sample_size == 2
    assert result.similarity_score > 0.8
    assert result.confidence > 0.0
    assert result.facts["temperature_f"] == 60


def test_stale_history_lowers_confidence_via_recency():
    fresh_rows = [
        _real_row(game_id="target", is_dome=False, temp=60, wind=5, precip=10, age_days=1),
        _real_row(game_id="c1", is_dome=False, temp=61, wind=5, precip=11, age_days=1),
        _real_row(game_id="c2", is_dome=False, temp=59, wind=5, precip=9, age_days=2),
    ]
    stale_rows = [
        _real_row(game_id="target", is_dome=False, temp=60, wind=5, precip=10, age_days=1),
        _real_row(game_id="c1", is_dome=False, temp=61, wind=5, precip=11, age_days=200),
        _real_row(game_id="c2", is_dome=False, temp=59, wind=5, precip=9, age_days=250),
    ]
    fresh = compute_weather_context(fresh_rows, game_id="target", now=NOW)
    stale = compute_weather_context(stale_rows, game_id="target", now=NOW)
    assert stale.recency_weighting < fresh.recency_weighting
    assert stale.confidence < fresh.confidence


def test_mixed_contradictory_pool_lowers_confidence_via_dispersion():
    rows = [
        _real_row(game_id="target", is_dome=False, temp=60, wind=5, precip=10, age_days=1),
        _real_row(game_id="c1", is_dome=False, temp=61, wind=5, precip=11, age_days=1),
        _real_row(game_id="c2", is_dome=False, temp=95, wind=25, precip=90, age_days=1),
    ]
    result = compute_weather_context(rows, game_id="target", now=NOW)
    assert result.insufficient_evidence is False
    # One comparable matches closely, the other is wildly different --
    # the resulting dispersion should meaningfully suppress confidence
    # even though recency is maximal for both.
    assert result.confidence < 0.15


def test_dome_game_buckets_against_other_domes_only():
    rows = [
        _real_row(game_id="target", is_dome=True, temp=72, wind=0, precip=0, age_days=1),
        _real_row(game_id="dome1", is_dome=True, temp=72, wind=0, precip=0, age_days=1),
        _real_row(game_id="dome2", is_dome=True, temp=72, wind=0, precip=0, age_days=1),
        # Outdoor games must never leak into a dome game's comparable pool.
        _real_row(game_id="outdoor1", is_dome=False, temp=30, wind=20, precip=50, age_days=1),
        _real_row(game_id="outdoor2", is_dome=False, temp=35, wind=25, precip=60, age_days=1),
    ]
    result = compute_weather_context(rows, game_id="target", now=NOW)
    assert result.sample_size == 2
    assert result.similarity_score == 1.0
    assert result.facts["is_dome"] is True


def test_unresolved_roof_type_bucketed_separately_never_coerced():
    rows = [
        _real_row(game_id="target", is_dome=None, temp=72, wind=5, precip=2, age_days=1),
        _real_row(game_id="unresolved1", is_dome=None, temp=73, wind=6, precip=3, age_days=1),
        _real_row(game_id="unresolved2", is_dome=None, temp=71, wind=4, precip=1, age_days=1),
        _real_row(game_id="outdoor1", is_dome=False, temp=72, wind=5, precip=2, age_days=1),
    ]
    result = compute_weather_context(rows, game_id="target", now=NOW)
    assert result.facts["is_dome"] is None
    assert result.sample_size == 2  # only the two other is_dome=None rows, never the outdoor one
