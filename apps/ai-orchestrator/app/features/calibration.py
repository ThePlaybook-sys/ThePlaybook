"""Probability calibration math (Phase 8, MANSA directive "PHASE 8 PROBABILITY
CALIBRATION LEDGER", 2026-09-15). Pure, deterministic, zero I/O -- the reading
and joining live in `app.persistence.calibration_reads`.

**This module answers exactly one question: "MANSA predicted X -- what actually
happened?"** It never tunes a probability, never proposes a weight, never
touches EV/Kelly/Risk, and never writes anything. It only measures.

**What counts as a scoreable prediction.** Only `WIN` and `LOSS` are scoreable:
they are the two outcomes with an unambiguous realized value (1 and 0). `PUSH`,
`VOID_NO_ACTION` and `PENDING_MISSING_DATA` are NOT coerced into either -- a
push is not half a win, and a void bet never resolved at all. They are counted
and reported separately so the excluded population is always visible rather than
silently dropped (the same null-not-neutral discipline the rest of this codebase
applies to missing data).

**Sample-size honesty is enforced in the type, not left to the reader.**
`CalibrationReport.conclusions_justified` is False below
`MIN_SAMPLE_FOR_CALIBRATION_CONCLUSIONS`, and the metrics are still computed
(they are mathematically valid at any n >= 1) -- what the flag says is that
believing them is not. A Brier score over three bets is a real number and a
meaningless one at the same time; this type refuses to let a caller forget the
second half.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

#: Outcomes with an unambiguous realized value. Everything else is excluded
#: from scoring rather than coerced -- see module docstring.
SCOREABLE_OUTCOMES: dict[str, float] = {"WIN": 1.0, "LOSS": 0.0}

#: Disclosed-conservative, explicitly NOT empirically derived -- the same
#: convention as `app.context_intelligence.scoring`'s own sample floors. Below
#: this, `CalibrationReport.conclusions_justified` is False. Chosen as a round
#: number that is obviously insufficient for per-bucket inference rather than as
#: a statistically defended threshold; raising it later is a policy decision, not
#: a bug fix.
MIN_SAMPLE_FOR_CALIBRATION_CONCLUSIONS = 100

#: Numerical guard for `log_loss` only: ln(0) is undefined, so a modeled
#: probability of exactly 0.0 or 1.0 is clamped into the open interval before
#: taking the log. This is floating-point hygiene, NOT a probability adjustment
#: -- `brier_score` and every reported bucket use the unclamped value.
_LOG_LOSS_EPSILON = 1e-15

#: 0.05-wide buckets across the full [0, 1] range. Volume 4 Section 5's own
#: calibration language ("0.55-0.60, 0.60-0.65") is a subset of these; the full
#: range is covered so a prediction can never fall outside every bucket and be
#: silently lost.
BUCKET_WIDTH = 0.05


@dataclass(frozen=True)
class SettledPrediction:
    """One frozen prediction joined to its authoritative realized outcome.

    Every field is copied from an already-immutable, DB-trigger-protected row
    (`recommendation_agent_outputs`, `recommendation_legs`,
    `recommendation_leg_grade_events`) -- nothing here is recomputed from
    current data, and nothing here can be changed by a later prompt, model or
    context change. See `app.persistence.calibration_reads` for the join."""

    candidate_key: str
    recommendation_id: str
    recommendation_leg_id: str
    game_id: str
    market_type: str
    selection: str
    sportsbook: str
    american_odds: int
    point: float | None
    #: The book's own vig-inclusive break-even at decision time, derived
    #: deterministically from `american_odds` -- never a stored guess.
    sportsbook_implied_probability: float
    #: FROZEN at decision time. Never reconstructed.
    modeled_probability: float
    confidence_in_probability: float | None
    model_name: str | None
    provider: str | None
    prompt_name: str | None
    prompt_version: int | None
    predicted_at: str
    #: Admitted contextual dimensions present when the prediction was made, with
    #: their completeness/sample_size. `None` for any prediction made before
    #: this provenance was captured -- honestly absent, never backfilled.
    context_provenance: dict | None
    outcome: str
    graded_at: str | None
    grading_version: str | None
    grade_event_id: str | None
    #: True when the authoritative grade for this leg is itself a correction of
    #: an earlier grade (stat correction, grading-rule change, manual review).
    grade_is_correction: bool
    corrects_grade_event_id: str | None

    @property
    def is_scoreable(self) -> bool:
        return self.outcome in SCOREABLE_OUTCOMES

    @property
    def realized_value(self) -> float | None:
        return SCOREABLE_OUTCOMES.get(self.outcome)


@dataclass(frozen=True)
class BucketBreakdown:
    lower: float
    upper: float
    count: int
    wins: int
    #: `wins / count` -- the OBSERVED frequency in this bucket.
    observed_win_rate: float
    #: Mean of the modeled probabilities that landed in this bucket -- what was
    #: PREDICTED. Calibration is the comparison of these two numbers.
    mean_predicted_probability: float

    @property
    def calibration_gap(self) -> float:
        """Observed minus predicted. Positive = underconfident in this bucket,
        negative = overconfident. Meaningless at small `count` -- read
        `CalibrationReport.conclusions_justified` first."""
        return self.observed_win_rate - self.mean_predicted_probability


@dataclass(frozen=True)
class CalibrationReport:
    total_predictions: int
    scoreable_predictions: int
    excluded_by_outcome: dict[str, int]
    wins: int
    losses: int
    brier_score: float | None
    log_loss: float | None
    buckets: tuple[BucketBreakdown, ...]
    conclusions_justified: bool
    notes: tuple[str, ...]


def bucket_bounds(probability: float, *, width: float = BUCKET_WIDTH) -> tuple[float, float]:
    """The [lower, upper) bucket a probability falls in. 1.0 is placed in the
    final bucket rather than a degenerate one of its own."""
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"probability must be within [0, 1], got {probability!r}")
    index = min(int(probability / width), int(1 / width) - 1)
    return (round(index * width, 10), round((index + 1) * width, 10))


def brier_score(predictions: list[SettledPrediction]) -> float | None:
    """Mean squared error between the frozen modeled probability and the
    realized outcome, over scoreable predictions only. Lower is better; 0.25 is
    what a constant 0.5 forecast scores. `None` when nothing is scoreable."""
    scoreable = [p for p in predictions if p.is_scoreable]
    if not scoreable:
        return None
    return sum((p.modeled_probability - p.realized_value) ** 2 for p in scoreable) / len(scoreable)


def log_loss(predictions: list[SettledPrediction]) -> float | None:
    """Mean negative log likelihood over scoreable predictions only. Punishes
    confident wrongness far harder than Brier does. `None` when nothing is
    scoreable. See `_LOG_LOSS_EPSILON` for the clamping note."""
    scoreable = [p for p in predictions if p.is_scoreable]
    if not scoreable:
        return None
    total = 0.0
    for prediction in scoreable:
        probability = min(max(prediction.modeled_probability, _LOG_LOSS_EPSILON), 1.0 - _LOG_LOSS_EPSILON)
        realized = prediction.realized_value
        total += -(realized * math.log(probability) + (1.0 - realized) * math.log(1.0 - probability))
    return total / len(scoreable)


def bucket_breakdown(predictions: list[SettledPrediction], *, width: float = BUCKET_WIDTH) -> tuple[BucketBreakdown, ...]:
    """Observed win rate vs. mean predicted probability, per bucket, over
    scoreable predictions only. Empty buckets are omitted entirely rather than
    reported as 0% -- an untested bucket is not a failing one."""
    grouped: dict[tuple[float, float], list[SettledPrediction]] = {}
    for prediction in predictions:
        if not prediction.is_scoreable:
            continue
        grouped.setdefault(bucket_bounds(prediction.modeled_probability, width=width), []).append(prediction)

    breakdowns = []
    for (lower, upper), bucket in sorted(grouped.items()):
        wins = sum(1 for p in bucket if p.outcome == "WIN")
        breakdowns.append(
            BucketBreakdown(
                lower=lower,
                upper=upper,
                count=len(bucket),
                wins=wins,
                observed_win_rate=wins / len(bucket),
                mean_predicted_probability=sum(p.modeled_probability for p in bucket) / len(bucket),
            )
        )
    return tuple(breakdowns)


def build_calibration_report(
    predictions: list[SettledPrediction], *, min_sample: int = MIN_SAMPLE_FOR_CALIBRATION_CONCLUSIONS
) -> CalibrationReport:
    """The whole deterministic picture in one value. Computes everything that is
    mathematically valid at the sample actually available, and states plainly --
    via `conclusions_justified` and `notes` -- when believing it is not."""
    scoreable = [p for p in predictions if p.is_scoreable]
    excluded: dict[str, int] = {}
    for prediction in predictions:
        if not prediction.is_scoreable:
            excluded[prediction.outcome] = excluded.get(prediction.outcome, 0) + 1

    notes: list[str] = []
    if not predictions:
        notes.append(
            "No settled predictions exist yet. Every metric is None -- this is an empty ledger, "
            "not a calibration finding."
        )
    elif not scoreable:
        notes.append(
            f"{len(predictions)} settled prediction(s) exist but none are scoreable "
            f"(outcomes: {sorted(excluded)}). PUSH/VOID/PENDING are never coerced into a win or loss."
        )
    if scoreable and len(scoreable) < min_sample:
        notes.append(
            f"Only {len(scoreable)} scoreable prediction(s) -- below the {min_sample} floor. The metrics "
            f"below are arithmetically correct and evidentially meaningless; no calibration conclusion, "
            f"and no probability or context adjustment, is justified by them."
        )
    if excluded:
        notes.append(f"Excluded from scoring by outcome: {dict(sorted(excluded.items()))}.")

    return CalibrationReport(
        total_predictions=len(predictions),
        scoreable_predictions=len(scoreable),
        excluded_by_outcome=dict(sorted(excluded.items())),
        wins=sum(1 for p in scoreable if p.outcome == "WIN"),
        losses=sum(1 for p in scoreable if p.outcome == "LOSS"),
        brier_score=brier_score(predictions),
        log_loss=log_loss(predictions),
        buckets=bucket_breakdown(predictions),
        conclusions_justified=len(scoreable) >= min_sample,
        notes=tuple(notes),
    )
