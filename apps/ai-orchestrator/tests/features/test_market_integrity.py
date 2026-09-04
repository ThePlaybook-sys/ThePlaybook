"""Tests for app.features.market_integrity (Milestone 7.1). Every
threshold is a disclosed-conservative policy default (see module
docstring) -- these tests prove the classification LOGIC is correct
against the fixed thresholds actually shipped, not that the thresholds
themselves are empirically right (DEV has no real history to validate
that against, per Milestone 7.0's own audit)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.features.market import LineMovementFeatures
from app.features.market_integrity import (
    ExplanatoryEvidenceResult,
    MarketIntegrityAssessment,
    THRESHOLD_VERSION,
    assess_market_integrity,
    check_explanatory_evidence,
    classify_market_movement,
    movement_windows,
)

T0 = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _features(
    *, point_movement=None, price_movement=None, insufficient_history=False, sample_count=2, direction=None
) -> LineMovementFeatures:
    return LineMovementFeatures(
        sportsbook="DraftKings",
        market_type="spread",
        side="BUF",
        opening_price=-150.0,
        latest_price=-150.0 + (price_movement or 0),
        price_movement=price_movement,
        opening_point=-3.5,
        latest_point=-3.5 + (point_movement or 0) if point_movement is not None else None,
        point_movement=point_movement,
        direction=direction,
        sample_count=sample_count,
        insufficient_history=insufficient_history,
    )


# --- classify_market_movement ---


def test_insufficient_history_is_its_own_classification_not_normal():
    features = _features(insufficient_history=True, sample_count=1)
    result = classify_market_movement(features)
    assert result.classification == "INSUFFICIENT_HISTORY"
    assert result.magnitude is None
    assert result.threshold_version == THRESHOLD_VERSION


def test_zero_movement_is_normal():
    result = classify_market_movement(_features(point_movement=0.0))
    assert result.classification == "NORMAL"
    assert result.magnitude == 0.0


def test_small_point_movement_below_watch_is_normal():
    result = classify_market_movement(_features(point_movement=0.5))
    assert result.classification == "NORMAL"


def test_point_movement_at_watch_threshold():
    result = classify_market_movement(_features(point_movement=1.0))
    assert result.classification == "WATCH"
    assert result.magnitude_basis == "point"


def test_point_movement_at_elevated_threshold():
    result = classify_market_movement(_features(point_movement=2.5))
    assert result.classification == "ELEVATED"


def test_point_movement_at_severe_threshold():
    result = classify_market_movement(_features(point_movement=4.0))
    assert result.classification == "SEVERE"


def test_negative_point_movement_uses_absolute_magnitude():
    result = classify_market_movement(_features(point_movement=-4.0))
    assert result.classification == "SEVERE"
    assert result.magnitude == 4.0


def test_price_movement_used_when_point_movement_is_none():
    result = classify_market_movement(_features(point_movement=None, price_movement=25.0))
    assert result.classification == "WATCH"
    assert result.magnitude_basis == "price"


def test_price_movement_severe():
    result = classify_market_movement(_features(point_movement=None, price_movement=80.0))
    assert result.classification == "SEVERE"


def test_neither_movement_computable_is_normal_not_fabricated():
    result = classify_market_movement(_features(point_movement=None, price_movement=None))
    assert result.classification == "NORMAL"
    assert result.magnitude is None
    assert result.magnitude_basis is None


# --- movement_windows ---


def test_movement_windows_groups_by_sportsbook_and_market_type():
    snapshots = [
        {"sportsbook": "DraftKings", "market_type": "spread", "captured_at": "2026-09-20T10:00:00+00:00"},
        {"sportsbook": "DraftKings", "market_type": "spread", "captured_at": "2026-09-20T14:00:00+00:00"},
        {"sportsbook": "FanDuel", "market_type": "total", "captured_at": "2026-09-20T11:00:00+00:00"},
    ]
    windows = movement_windows(snapshots)
    assert windows[("DraftKings", "spread")] == (
        datetime(2026, 9, 20, 10, tzinfo=timezone.utc),
        datetime(2026, 9, 20, 14, tzinfo=timezone.utc),
    )
    assert windows[("FanDuel", "total")] == (
        datetime(2026, 9, 20, 11, tzinfo=timezone.utc),
        datetime(2026, 9, 20, 11, tzinfo=timezone.utc),
    )


# --- check_explanatory_evidence ---


def test_no_evidence_anywhere_is_unexplained():
    result = check_explanatory_evidence(window_start=T0, window_end=T0 + timedelta(hours=2))
    assert result.explained is False
    assert result.matches == ()


def test_injury_within_lookback_window_is_a_match():
    injury_reports = [{"id": "inj-1", "captured_at": (T0 - timedelta(hours=3)).isoformat()}]
    result = check_explanatory_evidence(window_start=T0, window_end=T0 + timedelta(hours=2), injury_reports=injury_reports)
    assert result.explained is True
    assert result.matches[0].category == "injury"
    assert result.matches[0].reference == {"id": "inj-1"}


def test_evidence_before_lookback_window_is_not_a_match():
    # 30 hours before window_start -- outside the 24h EXPLANATORY_EVIDENCE_LOOKBACK
    injury_reports = [{"id": "inj-old", "captured_at": (T0 - timedelta(hours=30)).isoformat()}]
    result = check_explanatory_evidence(window_start=T0, window_end=T0 + timedelta(hours=2), injury_reports=injury_reports)
    assert result.explained is False


def test_evidence_after_window_end_is_not_a_match():
    injury_reports = [{"id": "inj-late", "captured_at": (T0 + timedelta(hours=5)).isoformat()}]
    result = check_explanatory_evidence(window_start=T0, window_end=T0 + timedelta(hours=2), injury_reports=injury_reports)
    assert result.explained is False


def test_weather_lineup_and_news_all_recognized_as_distinct_categories():
    weather_snapshots = [{"id": "w-1", "captured_at": T0.isoformat()}]
    depth_chart_snapshots = [{"id": "dc-1", "team_id": "team-1", "captured_at": T0.isoformat()}]
    news_articles = [{"id": "n-1", "ingested_at": T0.isoformat(), "headline": "Starting QB ruled out", "article_url": "https://example.com/a"}]
    result = check_explanatory_evidence(
        window_start=T0,
        window_end=T0 + timedelta(hours=2),
        weather_snapshots=weather_snapshots,
        depth_chart_snapshots=depth_chart_snapshots,
        news_articles=news_articles,
    )
    categories = {m.category for m in result.matches}
    assert categories == {"weather", "lineup", "news"}


def test_news_falls_back_to_published_at_when_ingested_at_missing():
    news_articles = [{"id": "n-2", "published_at": T0.isoformat(), "ingested_at": None}]
    result = check_explanatory_evidence(window_start=T0, window_end=T0 + timedelta(hours=2), news_articles=news_articles)
    assert result.explained is True


def test_news_with_no_timestamp_at_all_is_skipped_not_fatal():
    news_articles = [{"id": "n-3"}]
    result = check_explanatory_evidence(window_start=T0, window_end=T0 + timedelta(hours=2), news_articles=news_articles)
    assert result.explained is False


# --- assess_market_integrity (the combinator) ---


def test_normal_classification_has_no_signal_and_no_explanatory_check():
    features = _features(point_movement=0.5)
    result = assess_market_integrity(features, window=(T0, T0))
    assert result.signal is None
    assert result.explanatory is None


def test_insufficient_history_has_no_signal():
    features = _features(insufficient_history=True, sample_count=1)
    result = assess_market_integrity(features, window=None)
    assert result.signal is None


def test_qualifying_movement_with_evidence_is_explained():
    features = _features(point_movement=2.0)  # WATCH
    injury_reports = [{"id": "inj-1", "captured_at": T0.isoformat()}]
    result = assess_market_integrity(features, window=(T0, T0 + timedelta(hours=1)), injury_reports=injury_reports)
    assert result.classification.classification == "WATCH"
    assert result.signal == "EXPLAINED_MARKET_MOVEMENT"
    assert result.explanatory.explained is True


def test_qualifying_movement_with_no_evidence_is_unexplained():
    features = _features(point_movement=2.0)  # WATCH
    result = assess_market_integrity(features, window=(T0, T0 + timedelta(hours=1)))
    assert result.signal == "UNEXPLAINED_MARKET_MOVEMENT"
    assert result.explanatory.explained is False


def test_qualifying_movement_with_no_window_is_conservatively_unexplained_not_crashed():
    features = _features(point_movement=5.0)  # SEVERE
    result = assess_market_integrity(features, window=None)
    assert result.signal == "UNEXPLAINED_MARKET_MOVEMENT"
    assert result.explanatory.matches == ()


def test_evidence_never_asserted_as_causal_only_temporal_proximity():
    # The result carries evidence presence/timestamps, never a "caused_by"
    # or "reason" field asserting why the market moved -- this test pins
    # the dataclass shape so a future change can't quietly add one.
    features = _features(point_movement=2.0)
    injury_reports = [{"id": "inj-1", "captured_at": T0.isoformat()}]
    result = assess_market_integrity(features, window=(T0, T0 + timedelta(hours=1)), injury_reports=injury_reports)
    match = result.explanatory.matches[0]
    assert set(match.__dataclass_fields__) == {"category", "observed_at", "reference"}
    assert isinstance(result, MarketIntegrityAssessment)
    assert isinstance(result.explanatory, ExplanatoryEvidenceResult)
