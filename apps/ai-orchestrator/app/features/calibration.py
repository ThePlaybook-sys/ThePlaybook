"""Probability calibration math (Phase 8, MANSA directive "PHASE 8 PROBABILITY
CALIBRATION LEDGER", 2026-09-15). Pure, deterministic, zero I/O -- the reading
and joining live in `app.persistence.calibration_reads`.

**This module answers exactly one question: "MANSA predicted X -- what actually
happened?"** It never tunes a probability, never proposes a weight, never
touches EV/Kelly/Risk, and never writes anything. It only measures.

**What counts as a scoreable prediction.** Two independent gates, both required.

*Gate 1 -- the forward-looking timing contract (2026-09-15).* A calibration
observation is only meaningful if the prediction genuinely existed BEFORE the
outcome was knowable. A probability produced at or after kickoff may encode
hindsight -- in-game state, a known final score, a settled stat line -- and
scoring it would flatter the model with information it never had to forecast.
So `predicted_at` must exist, the event's `scheduled_start` must exist, and
`predicted_at` must be strictly earlier than `scheduled_start`. A prediction
failing this is **never deleted and never silently dropped** -- it is returned
with an explicit `calibration_exclusion_reason` so the excluded population stays
auditable.

*Gate 2 -- a binary realized outcome.* Only `WIN` and `LOSS` have an unambiguous
realized value (1 and 0). `PUSH`, `VOID_NO_ACTION` and `PENDING_MISSING_DATA`
are NOT coerced into either -- a push is not half a win, and a void bet never
resolved at all.

Both gates report through one field, `calibration_exclusion_reason`: `None`
means eligible. Every metric in this module filters on `is_scoreable`, so an
ineligible prediction cannot reach a Brier score, a log loss or a bucket by any
path.

**Hindsight backfill is prohibited, not merely discouraged.** Generating a
prediction after a game has ended and treating it as a historical calibration
observation is post-event prediction, not forecasting. Neither is
`modeled_probability` ever reconstructed later -- it is read frozen or the row
does not become a prediction at all. No historical/replay path has been proven
point-in-time safe in this codebase, so none may feed this ledger. Synthetic and
post-hoc fixtures may prove plumbing in tests; they must never increase the real
calibration sample count.

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
from datetime import datetime

#: Outcomes with an unambiguous realized value. Everything else is excluded
#: from scoring rather than coerced -- see module docstring.
SCOREABLE_OUTCOMES: dict[str, float] = {"WIN": 1.0, "LOSS": 0.0}

#: Every reason a settled prediction can be held out of binary scoring. Stable
#: strings -- they are reported to operators, so they are part of this module's
#: contract rather than incidental prose.
EXCLUSION_MISSING_PREDICTED_AT = "missing_predicted_at"
EXCLUSION_MISSING_SCHEDULED_START = "missing_event_scheduled_start"
EXCLUSION_UNPARSEABLE_TIMESTAMP = "unparseable_timestamp"
EXCLUSION_NOT_PREDICTED_BEFORE_KICKOFF = "predicted_at_not_before_scheduled_start"
EXCLUSION_OUTCOME_NOT_BINARY = "outcome_not_binary"


def _parse_timestamp(value: str | None) -> datetime | None:
    """Tolerant ISO-8601 parse of a Postgres `timestamptz`. Returns `None`
    rather than raising -- an unparseable timestamp is an eligibility failure to
    be reported, never an exception that hides the whole ledger."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

#: A PRODUCT RULE meaning "MANSA draws no conclusions yet" -- explicitly NOT a
#: statistically proven sufficiency threshold, and it must never be described as
#: one. 100 eligible observations does not make a calibration estimate reliable;
#: it is a round, conservative number chosen so that obviously-meaningless
#: samples cannot be read as findings. Genuine per-bucket inference needs far
#: more than 100, spread across buckets. Same disclosed-not-derived convention as
#: `app.context_intelligence.scoring`'s own sample floors; changing it is a
#: policy decision, not a bug fix.
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
    #: The event's scheduled kickoff, frozen on `games`. The forward-looking
    #: timing contract is `predicted_at < scheduled_start`; without this value
    #: the contract cannot be evaluated and the prediction is excluded.
    scheduled_start: str | None
    outcome: str
    graded_at: str | None
    grading_version: str | None
    grade_event_id: str | None
    #: True when the authoritative grade for this leg is itself a correction of
    #: an earlier grade (stat correction, grading-rule change, manual review).
    grade_is_correction: bool
    corrects_grade_event_id: str | None

    @property
    def calibration_exclusion_reason(self) -> str | None:
        """`None` when this prediction may contribute to calibration metrics.
        Otherwise the specific, stable reason it may not -- evaluated in a fixed
        order so a row with several problems reports the most fundamental one.

        The timing gate is checked BEFORE the outcome gate on purpose: a
        prediction made after kickoff is disqualified as a forecast regardless
        of how cleanly it later settled."""
        predicted = _parse_timestamp(self.predicted_at)
        scheduled = _parse_timestamp(self.scheduled_start)
        if not self.predicted_at:
            return EXCLUSION_MISSING_PREDICTED_AT
        if not self.scheduled_start:
            return EXCLUSION_MISSING_SCHEDULED_START
        if predicted is None or scheduled is None:
            return EXCLUSION_UNPARSEABLE_TIMESTAMP
        if predicted >= scheduled:
            return EXCLUSION_NOT_PREDICTED_BEFORE_KICKOFF
        if self.outcome not in SCOREABLE_OUTCOMES:
            return EXCLUSION_OUTCOME_NOT_BINARY
        return None

    @property
    def predicted_before_kickoff(self) -> bool:
        """The forward-looking timing contract alone, independent of outcome --
        the single property that separates a genuine forecast from a post-event
        prediction."""
        return self.calibration_exclusion_reason not in (
            EXCLUSION_MISSING_PREDICTED_AT,
            EXCLUSION_MISSING_SCHEDULED_START,
            EXCLUSION_UNPARSEABLE_TIMESTAMP,
            EXCLUSION_NOT_PREDICTED_BEFORE_KICKOFF,
        )

    @property
    def is_scoreable(self) -> bool:
        return self.calibration_exclusion_reason is None

    @property
    def realized_value(self) -> float | None:
        return SCOREABLE_OUTCOMES.get(self.outcome) if self.is_scoreable else None


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
    #: Every held-out prediction, grouped by `calibration_exclusion_reason`.
    #: Nothing is deleted or hidden -- the excluded population stays auditable.
    excluded_by_reason: dict[str, int]
    #: Predictions failing the forward-looking timing contract specifically.
    #: Called out separately because it is the one exclusion that indicates a
    #: process problem (a post-event prediction was produced) rather than an
    #: ordinary un-scoreable settlement like a push.
    excluded_post_event: int
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
    post_event = 0
    for prediction in predictions:
        reason = prediction.calibration_exclusion_reason
        if reason is None:
            continue
        excluded[reason] = excluded.get(reason, 0) + 1
        if not prediction.predicted_before_kickoff:
            post_event += 1

    notes: list[str] = []
    if not predictions:
        notes.append(
            "No settled predictions exist yet. Every metric is None -- this is an empty ledger, "
            "not a calibration finding."
        )
    elif not scoreable:
        notes.append(
            f"{len(predictions)} settled prediction(s) exist but none are eligible for scoring "
            f"(reasons: {sorted(excluded)}). PUSH/VOID are never coerced into a win or loss, and a "
            f"prediction made at or after kickoff is never scored at all."
        )
    if scoreable and len(scoreable) < min_sample:
        notes.append(
            f"Only {len(scoreable)} eligible prediction(s) -- below the {min_sample} product floor. The "
            f"metrics below are arithmetically correct and evidentially meaningless; no calibration "
            f"conclusion, and no probability or context adjustment, is justified by them."
        )
    if post_event:
        notes.append(
            f"{post_event} prediction(s) were made at or after the event's scheduled start and are "
            f"excluded from every metric -- these are post-event predictions, not forecasts, and may "
            f"encode hindsight. They are retained and reported, never deleted."
        )
    if excluded:
        notes.append(f"Excluded from scoring by reason: {dict(sorted(excluded.items()))}.")

    return CalibrationReport(
        total_predictions=len(predictions),
        scoreable_predictions=len(scoreable),
        excluded_by_reason=dict(sorted(excluded.items())),
        excluded_post_event=post_event,
        wins=sum(1 for p in scoreable if p.outcome == "WIN"),
        losses=sum(1 for p in scoreable if p.outcome == "LOSS"),
        brier_score=brier_score(predictions),
        log_loss=log_loss(predictions),
        buckets=bucket_breakdown(predictions),
        conclusions_justified=len(scoreable) >= min_sample,
        notes=tuple(notes),
    )
