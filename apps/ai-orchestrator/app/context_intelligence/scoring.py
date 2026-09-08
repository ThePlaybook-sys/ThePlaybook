"""Shared deterministic scoring primitives for every context-intelligence
dimension (Phase 8.1 Foundation Pass, 2026-09-08). Pure functions only --
no I/O, mirroring `app.features.market`/`app.features.market_integrity`'s
own separation of computation from persistence.

**Every constant below is a disclosed-conservative policy default, NOT
empirically derived from real data** -- same discipline as
`app.features.market_integrity.THRESHOLD_VERSION`/
`POINT_MOVEMENT_THRESHOLDS` and Milestone 5.5's
`ADAPTIVE_WEIGHT_LEARNING_RATE`. Real sample sizes across every real
tracked dimension today are in the single digits (Phase 8.0.5 closeout:
8 real games, ~3-5 with weather, ~10 teams' worth of news) -- far too
small to calibrate anything from. `SCORING_VERSION` is frozen onto every
result's provenance so a future recalibration is a new, distinguishable
version, never a silent redefinition of what a given confidence number
already meant historically."""
from __future__ import annotations

from datetime import datetime, timezone

SCORING_VERSION = "v1-provisional"

#: Halves a comparable observation's weight every this many days old.
RECENCY_HALF_LIFE_DAYS = 14.0

#: `sample_size / MIN_SAMPLE_FOR_FULL_CONFIDENCE` is the sample-adequacy
#: factor confidence is multiplied by (capped at 1.0) -- reaching this
#: many real comparables is treated as "enough to stop being sample-size
#: limited," not as any claim of statistical significance.
MIN_SAMPLE_FOR_FULL_CONFIDENCE = 8

#: Fewer real comparables than this and a dimension reports
#: `insufficient_evidence=True` outright rather than a low-confidence
#: number -- two points is the minimum needed to say anything about
#: spread/consistency at all.
INSUFFICIENT_SAMPLE_FLOOR = 2


def parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def recency_weight(observed_at: datetime, *, now: datetime, half_life_days: float = RECENCY_HALF_LIFE_DAYS) -> float:
    """Exponential decay, 1.0 at age zero, 0.5 at `half_life_days` old.
    Never negative, never above 1.0 (an `observed_at` after `now` --
    should not happen for real captured data -- is clamped to age 0)."""
    age_days = max((now - observed_at).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (age_days / half_life_days)


def numeric_similarity(a: float, b: float, *, scale: float) -> float:
    """1.0 when identical, decaying linearly to 0.0 at `scale` apart and
    beyond. `scale` is the disclosed "beyond this difference, treat as
    maximally dissimilar" policy default for one specific field."""
    if scale <= 0:
        return 1.0 if a == b else 0.0
    return max(0.0, 1.0 - abs(a - b) / scale)


def weighted_mean(values_and_weights: list[tuple[float, float]]) -> float | None:
    """`None` when every weight is zero (or the input is empty) -- never
    a fabricated 0.0 standing in for "no real weight to average over."""
    total_weight = sum(w for _, w in values_and_weights)
    if total_weight <= 0:
        return None
    return sum(v * w for v, w in values_and_weights) / total_weight


def dispersion(values: list[float]) -> float:
    """A simple, bounded [0, 1] consistency signal -- the coefficient of
    variation (stdev / |mean|), clamped at 1.0. Not a claim of formal
    statistical rigor, only a deterministic, disclosed "how scattered is
    this comparable pool" measure. `0.0` for fewer than two values (no
    spread to measure) or when every value is identical."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    stdev = variance**0.5
    if mean == 0:
        return min(1.0, stdev)
    return min(1.0, stdev / abs(mean))


def confidence_score(*, sample_size: int, avg_recency_weight: float, consistency: float) -> float:
    """Three independent, bounded `[0, 1]` factors combined by simple
    multiplication so any single weak factor honestly caps the overall
    result: sample adequacy, recency of the comparable pool, and
    consistency (`1 - dispersion`) within it. Never a fabricated score
    when any factor is missing -- callers only reach this function once
    `sample_size >= INSUFFICIENT_SAMPLE_FLOOR` has already been checked."""
    sample_factor = min(1.0, sample_size / MIN_SAMPLE_FOR_FULL_CONFIDENCE)
    return round(max(0.0, min(1.0, sample_factor * avg_recency_weight * consistency)), 4)


__all__ = [
    "SCORING_VERSION",
    "RECENCY_HALF_LIFE_DAYS",
    "MIN_SAMPLE_FOR_FULL_CONFIDENCE",
    "INSUFFICIENT_SAMPLE_FLOOR",
    "parse_ts",
    "recency_weight",
    "numeric_similarity",
    "weighted_mean",
    "dispersion",
    "confidence_score",
]
