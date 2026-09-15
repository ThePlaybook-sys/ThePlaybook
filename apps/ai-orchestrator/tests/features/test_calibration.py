"""Tests for `app.features.calibration` (Phase 8 Probability Calibration Ledger,
2026-09-15). Pure math -- no I/O, no fixtures from the database.

Note on realism: these use hand-built `SettledPrediction` values because dev
currently holds ZERO settled predictions (0 recommendation_legs, 0 grade events,
live-verified). They prove the math is correct for when real rows exist; they are
explicitly NOT evidence about MANSA's actual calibration."""
from __future__ import annotations

import math

import pytest

from app.features.calibration import (
    EXCLUSION_MISSING_PREDICTED_AT,
    EXCLUSION_MISSING_SCHEDULED_START,
    EXCLUSION_NOT_PREDICTED_BEFORE_KICKOFF,
    EXCLUSION_OUTCOME_NOT_BINARY,
    EXCLUSION_UNPARSEABLE_TIMESTAMP,
    MIN_SAMPLE_FOR_CALIBRATION_CONCLUSIONS,
    SettledPrediction,
    brier_score,
    bucket_bounds,
    bucket_breakdown,
    build_calibration_report,
    log_loss,
)


def _prediction(
    *, modeled_probability: float, outcome: str, key: str = "k",
    predicted_at: str | None = "2026-09-15T00:00:00+00:00",
    scheduled_start: str | None = "2026-09-15T17:00:00+00:00",
) -> SettledPrediction:
    return SettledPrediction(
        candidate_key=key, recommendation_id="r1", recommendation_leg_id="l1", game_id="g1",
        market_type="moneyline", selection="Kansas City Chiefs", sportsbook="DraftKings",
        american_odds=-125, point=None, sportsbook_implied_probability=0.5556,
        modeled_probability=modeled_probability, confidence_in_probability=0.7,
        model_name="claude-opus-5", provider="anthropic", prompt_name="probability_modeling_agent",
        prompt_version=3, predicted_at=predicted_at, context_provenance=None, scheduled_start=scheduled_start,
        outcome=outcome, graded_at="2026-09-16T00:00:00+00:00", grading_version="v1",
        grade_event_id="ge1", grade_is_correction=False, corrects_grade_event_id=None,
    )


# --- scoreability: PUSH/VOID/PENDING are never coerced into a win or loss ---


@pytest.mark.parametrize(
    "outcome,expected_scoreable,expected_value",
    [("WIN", True, 1.0), ("LOSS", True, 0.0), ("PUSH", False, None), ("VOID_NO_ACTION", False, None), ("PENDING_MISSING_DATA", False, None)],
)
def test_only_win_and_loss_are_scoreable(outcome, expected_scoreable, expected_value):
    prediction = _prediction(modeled_probability=0.6, outcome=outcome)
    assert prediction.is_scoreable is expected_scoreable
    assert prediction.realized_value == expected_value


def test_pushes_and_voids_are_excluded_from_metrics_not_counted_as_losses():
    """A push scored as a loss would silently defame a correct model. It must be
    excluded from the denominator entirely and reported separately."""
    predictions = [
        _prediction(modeled_probability=0.6, outcome="WIN"),
        _prediction(modeled_probability=0.6, outcome="PUSH"),
        _prediction(modeled_probability=0.6, outcome="VOID_NO_ACTION"),
    ]
    report = build_calibration_report(predictions)
    assert report.total_predictions == 3
    assert report.scoreable_predictions == 1
    assert report.wins == 1 and report.losses == 0
    assert report.excluded_by_reason == {"outcome_not_binary": 2}
    # Brier over the single scoreable prediction only: (0.6 - 1)^2
    assert report.brier_score == pytest.approx(0.16)


# --- Brier / log loss correctness against hand-computed values ---


def test_brier_score_matches_hand_computation():
    predictions = [
        _prediction(modeled_probability=0.8, outcome="WIN"),   # (0.8-1)^2 = 0.04
        _prediction(modeled_probability=0.3, outcome="LOSS"),  # (0.3-0)^2 = 0.09
    ]
    assert brier_score(predictions) == pytest.approx((0.04 + 0.09) / 2)


def test_brier_score_of_constant_coin_flip_is_one_quarter():
    predictions = [_prediction(modeled_probability=0.5, outcome="WIN"), _prediction(modeled_probability=0.5, outcome="LOSS")]
    assert brier_score(predictions) == pytest.approx(0.25)


def test_log_loss_matches_hand_computation():
    predictions = [
        _prediction(modeled_probability=0.8, outcome="WIN"),
        _prediction(modeled_probability=0.3, outcome="LOSS"),
    ]
    expected = (-math.log(0.8) + -math.log(0.7)) / 2
    assert log_loss(predictions) == pytest.approx(expected)


def test_log_loss_clamps_certainty_instead_of_raising():
    """A confidently wrong 0.0/1.0 forecast must produce a large finite penalty,
    never a math-domain crash -- the clamp is numerical hygiene only."""
    predictions = [_prediction(modeled_probability=1.0, outcome="LOSS")]
    value = log_loss(predictions)
    assert value is not None and math.isfinite(value) and value > 30


def test_brier_is_unaffected_by_the_log_loss_clamp():
    """The clamp exists only inside log_loss -- Brier must use the raw value."""
    assert brier_score([_prediction(modeled_probability=1.0, outcome="LOSS")]) == pytest.approx(1.0)


def test_metrics_are_none_when_nothing_is_scoreable():
    predictions = [_prediction(modeled_probability=0.6, outcome="PUSH")]
    assert brier_score(predictions) is None
    assert log_loss(predictions) is None


# --- buckets ---


@pytest.mark.parametrize(
    "probability,expected",
    [(0.0, (0.0, 0.05)), (0.52, (0.5, 0.55)), (0.55, (0.55, 0.6)), (0.999, (0.95, 1.0)), (1.0, (0.95, 1.0))],
)
def test_bucket_bounds(probability, expected):
    assert bucket_bounds(probability) == expected


def test_bucket_bounds_rejects_out_of_range():
    with pytest.raises(ValueError):
        bucket_bounds(1.5)


def test_bucket_breakdown_reports_observed_vs_predicted():
    predictions = [
        _prediction(modeled_probability=0.56, outcome="WIN"),
        _prediction(modeled_probability=0.58, outcome="LOSS"),
        _prediction(modeled_probability=0.72, outcome="WIN"),
    ]
    buckets = {(b.lower, b.upper): b for b in bucket_breakdown(predictions)}
    assert set(buckets) == {(0.55, 0.6), (0.7, 0.75)}

    mid = buckets[(0.55, 0.6)]
    assert mid.count == 2 and mid.wins == 1
    assert mid.observed_win_rate == pytest.approx(0.5)
    assert mid.mean_predicted_probability == pytest.approx(0.57)
    assert mid.calibration_gap == pytest.approx(0.5 - 0.57)


def test_empty_buckets_are_omitted_not_reported_as_zero_percent():
    """An untested bucket is not a 0%-win-rate bucket."""
    buckets = bucket_breakdown([_prediction(modeled_probability=0.62, outcome="WIN")])
    assert len(buckets) == 1 and buckets[0].lower == pytest.approx(0.6)


# --- sample-size honesty ---


def test_empty_ledger_is_reported_as_empty_not_as_a_finding():
    report = build_calibration_report([])
    assert report.total_predictions == 0
    assert report.brier_score is None and report.log_loss is None
    assert report.conclusions_justified is False
    assert any("empty ledger" in note for note in report.notes)


def test_small_sample_computes_metrics_but_refuses_to_justify_conclusions():
    predictions = [_prediction(modeled_probability=0.6, outcome="WIN") for _ in range(3)]
    report = build_calibration_report(predictions)
    assert report.scoreable_predictions == 3
    assert report.brier_score is not None  # arithmetically valid...
    assert report.conclusions_justified is False  # ...and evidentially meaningless
    assert any("below the" in note and "floor" in note for note in report.notes)


def test_conclusions_become_justified_at_the_floor():
    predictions = [_prediction(modeled_probability=0.6, outcome="WIN") for _ in range(MIN_SAMPLE_FOR_CALIBRATION_CONCLUSIONS)]
    report = build_calibration_report(predictions)
    assert report.conclusions_justified is True
    assert not any("floor" in note for note in report.notes)


# --------------------------------------------------------------------------
# Forward-looking timing contract (2026-09-15). A calibration observation is
# only meaningful if the prediction genuinely existed BEFORE the outcome was
# knowable. These are the tests that keep hindsight out of the ledger.
# --------------------------------------------------------------------------


def test_prediction_made_before_kickoff_is_eligible():
    prediction = _prediction(
        modeled_probability=0.6, outcome="WIN",
        predicted_at="2026-09-15T12:00:00+00:00", scheduled_start="2026-09-15T17:00:00+00:00",
    )
    assert prediction.calibration_exclusion_reason is None
    assert prediction.predicted_before_kickoff is True
    assert prediction.is_scoreable is True


def test_prediction_made_after_kickoff_is_excluded_as_post_event():
    """The core anti-hindsight rule: a probability produced after the event
    started may encode information it never had to forecast."""
    prediction = _prediction(
        modeled_probability=0.95, outcome="WIN",
        predicted_at="2026-09-16T03:00:00+00:00", scheduled_start="2026-09-15T17:00:00+00:00",
    )
    assert prediction.calibration_exclusion_reason == EXCLUSION_NOT_PREDICTED_BEFORE_KICKOFF
    assert prediction.predicted_before_kickoff is False
    assert prediction.is_scoreable is False
    assert prediction.realized_value is None


def test_prediction_made_exactly_at_kickoff_is_excluded():
    """`predicted_at < scheduled_start` is strict -- equality is not before."""
    prediction = _prediction(
        modeled_probability=0.6, outcome="WIN",
        predicted_at="2026-09-15T17:00:00+00:00", scheduled_start="2026-09-15T17:00:00+00:00",
    )
    assert prediction.calibration_exclusion_reason == EXCLUSION_NOT_PREDICTED_BEFORE_KICKOFF


def test_timing_gate_is_checked_before_the_outcome_gate():
    """A post-event prediction is disqualified as a forecast regardless of how
    cleanly it settled -- the reported reason must be the timing failure."""
    prediction = _prediction(
        modeled_probability=0.6, outcome="PUSH",
        predicted_at="2026-09-16T03:00:00+00:00", scheduled_start="2026-09-15T17:00:00+00:00",
    )
    assert prediction.calibration_exclusion_reason == EXCLUSION_NOT_PREDICTED_BEFORE_KICKOFF


def test_missing_scheduled_start_excludes_rather_than_assuming_in_time():
    prediction = _prediction(modeled_probability=0.6, outcome="WIN", scheduled_start=None)
    assert prediction.calibration_exclusion_reason == EXCLUSION_MISSING_SCHEDULED_START
    assert prediction.is_scoreable is False


def test_missing_predicted_at_excludes():
    prediction = _prediction(modeled_probability=0.6, outcome="WIN", predicted_at=None)
    assert prediction.calibration_exclusion_reason == EXCLUSION_MISSING_PREDICTED_AT


def test_unparseable_timestamp_excludes_without_raising():
    prediction = _prediction(modeled_probability=0.6, outcome="WIN", predicted_at="not-a-timestamp")
    assert prediction.calibration_exclusion_reason == EXCLUSION_UNPARSEABLE_TIMESTAMP


def test_post_event_predictions_cannot_reach_any_metric():
    """Belt and braces: a confidently-correct post-event prediction would
    flatter every metric. It must be invisible to all of them."""
    hindsight = _prediction(
        modeled_probability=1.0, outcome="WIN",
        predicted_at="2026-09-16T03:00:00+00:00", scheduled_start="2026-09-15T17:00:00+00:00",
    )
    assert brier_score([hindsight]) is None
    assert log_loss([hindsight]) is None
    assert bucket_breakdown([hindsight]) == ()


def test_report_counts_post_event_exclusions_separately_and_retains_them():
    legitimate = _prediction(
        modeled_probability=0.6, outcome="WIN",
        predicted_at="2026-09-15T12:00:00+00:00", scheduled_start="2026-09-15T17:00:00+00:00",
    )
    hindsight = _prediction(
        modeled_probability=1.0, outcome="WIN",
        predicted_at="2026-09-16T03:00:00+00:00", scheduled_start="2026-09-15T17:00:00+00:00",
    )
    report = build_calibration_report([legitimate, hindsight])

    assert report.total_predictions == 2  # retained, never deleted
    assert report.scoreable_predictions == 1
    assert report.excluded_post_event == 1
    assert report.excluded_by_reason == {EXCLUSION_NOT_PREDICTED_BEFORE_KICKOFF: 1}
    # Only the legitimate forecast reaches the metrics: (0.6 - 1)^2
    assert report.brier_score == pytest.approx(0.16)
    assert any("post-event predictions, not forecasts" in note for note in report.notes)


def test_report_distinguishes_post_event_from_ordinary_unscoreable_settlement():
    """A push is an ordinary un-scoreable settlement; a post-event prediction is
    a process problem. They must not be conflated in the reporting."""
    push = _prediction(modeled_probability=0.6, outcome="PUSH")
    hindsight = _prediction(
        modeled_probability=0.9, outcome="LOSS",
        predicted_at="2026-09-16T03:00:00+00:00", scheduled_start="2026-09-15T17:00:00+00:00",
    )
    report = build_calibration_report([push, hindsight])

    assert report.excluded_post_event == 1
    assert report.excluded_by_reason == {
        EXCLUSION_NOT_PREDICTED_BEFORE_KICKOFF: 1,
        EXCLUSION_OUTCOME_NOT_BINARY: 1,
    }
