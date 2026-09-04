"""Milestone 7.1's deterministic Unexplained-Movement Detection Engine
(Volume 4 §8.5, Phase 7, Milestone 7.0's own locked decisions). Pure
functions only -- no I/O, mirroring `app.features.market`/`app.features.
grading`'s exact separation of computation from persistence.

**Mechanism decision (Milestone 7.0): deterministic, never an LLM.**
Nothing in this module calls a model. Classification is a pure
comparison of an already-computed movement magnitude against a fixed,
disclosed threshold table.

**Language lock (Milestone 7.0, Volume 4 §8.5).** This module's only
vocabulary is STATISTICAL ANOMALY / MARKET ANOMALY / UNEXPLAINED MARKET
MOVEMENT, neutral magnitude/direction/timing facts, and an explicit
evidence-presence/absence disclosure. It never computes, infers, or
emits "sharp money," "manipulation," "insider activity," "fixing," or
any other confirmed-integrity-breach language -- that vocabulary
requires a confirmed authoritative source (regulator action, official
investigation, credible reporting) this module has no access to and
does not attempt to approximate.

**Thresholds are disclosed-conservative policy defaults, NOT empirically
derived (Milestone 7.0's own explicit finding: DEV's real odds history
is functionally nonexistent -- 4 rows, 1 game, 1 computable delta,
confirmed live 2026-09-02 and reconfirmed unchanged 2026-09-04).** Same
disclosure discipline as `ADAPTIVE_WEIGHT_LEARNING_RATE = 0.25`
(Milestone 5.5): a real, working number this system needs today, openly
marked as a policy choice pending real accumulated data, never
presented as calibrated from the current DEV sample. `THRESHOLD_VERSION`
is frozen onto every classification and every persisted
`market_monitoring_events` row precisely so a future recalibration is a
new, distinguishable version, never a silent redefinition of what
"SEVERE" already meant historically.

**Never claims causation.** `check_explanatory_evidence` and
`assess_market_integrity` report only whether a candidate explanatory
fact (an injury report, a weather snapshot, a lineup/depth-chart
change, a news article) was ALSO observed within a bounded time window
around the movement -- temporal proximity, not a causal claim. Evidence
occurring near a movement is reported as "explained" (a known category
of information exists that could account for it); the absence of any
such evidence is reported as `UNEXPLAINED_MARKET_MOVEMENT` -- the one
buildable core signal this milestone exists to produce, per Volume 4
§8.5's own naming. Neither outcome asserts *why* the market actually
moved.

**Preserves `LineMovementFeatures.insufficient_history` behavior
verbatim (Milestone 4.5's own explicit rule): never a fabricated
`NORMAL` for a single-snapshot group.** `INSUFFICIENT_HISTORY` is
returned as its own distinct classification, not folded into `NORMAL`
-- "we don't have enough history to say" and "we checked and it's
normal" are different facts, and conflating them would let a genuinely
under-observed market silently read as "nothing to see here."
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.features.market import LineMovementFeatures

#: Frozen onto every classification/persisted event. Bump this (never
#: silently redefine the thresholds below in place) if/when real
#: accumulated production odds history ever justifies recalibration --
#: same discipline as GRADING_VERSION/EXPLAINABILITY_VERSION/STRATEGY_VERSION.
THRESHOLD_VERSION = "v1-provisional"

#: Disclosed-conservative, NOT empirically derived (see module
#: docstring). Applied to `abs(point_movement)` -- spread/total markets,
#: where movement is naturally expressed in points.
POINT_MOVEMENT_THRESHOLDS: dict[str, float] = {"WATCH": 1.0, "ELEVATED": 2.5, "SEVERE": 4.0}

#: Disclosed-conservative, NOT empirically derived. Applied to
#: `abs(price_movement)` -- moneyline markets (American odds units),
#: used only when `point_movement` is unavailable (mirrors
#: `app.features.market`'s own `point_movement if not None else
#: price_movement` primary-movement precedence, applied consistently
#: here rather than inventing a second rule).
PRICE_MOVEMENT_THRESHOLDS: dict[str, float] = {"WATCH": 20.0, "ELEVATED": 40.0, "SEVERE": 75.0}

CLASSIFICATIONS = ("INSUFFICIENT_HISTORY", "NORMAL", "WATCH", "ELEVATED", "SEVERE")
_QUALIFYING_CLASSIFICATIONS = ("WATCH", "ELEVATED", "SEVERE")

#: How far before a movement's own observation window a piece of
#: explanatory evidence may fall and still count as a candidate match.
#: A second disclosed-conservative, non-empirical policy default this
#: milestone introduces (Milestone 7.0 authorized the classification
#: thresholds above; this window is a necessary companion decision for
#: the explanatory-evidence check specifically, disclosed with the same
#: rigor rather than smuggled in as though already authorized).
EXPLANATORY_EVIDENCE_LOOKBACK = timedelta(hours=24)

EXPLANATORY_CATEGORIES = ("injury", "weather", "lineup", "news")

SIGNAL_EXPLAINED = "EXPLAINED_MARKET_MOVEMENT"
SIGNAL_UNEXPLAINED = "UNEXPLAINED_MARKET_MOVEMENT"


@dataclass(frozen=True)
class MarketMovementClassification:
    sportsbook: str
    market_type: str
    side: str
    classification: str  # one of CLASSIFICATIONS
    magnitude: float | None
    magnitude_basis: str | None  # "point" | "price" | None
    direction: str | None
    sample_count: int
    price_movement: float | None
    point_movement: float | None
    threshold_version: str


@dataclass(frozen=True)
class ExplanatoryEvidenceMatch:
    category: str  # one of EXPLANATORY_CATEGORIES
    observed_at: datetime
    reference: dict[str, Any]  # a small, honest descriptor -- never the full raw payload, never a causal claim


@dataclass(frozen=True)
class ExplanatoryEvidenceResult:
    explained: bool
    matches: tuple[ExplanatoryEvidenceMatch, ...]


@dataclass(frozen=True)
class MarketIntegrityAssessment:
    classification: MarketMovementClassification
    explanatory: ExplanatoryEvidenceResult | None
    signal: str | None  # SIGNAL_EXPLAINED | SIGNAL_UNEXPLAINED | None (None when not a qualifying classification)


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def classify_market_movement(features: LineMovementFeatures) -> MarketMovementClassification:
    """Pure deterministic classification of one already-computed
    `LineMovementFeatures` row. Never NORMAL for `insufficient_history`
    (see module docstring) -- that is its own distinct classification."""
    if features.insufficient_history:
        return MarketMovementClassification(
            sportsbook=features.sportsbook,
            market_type=features.market_type,
            side=features.side,
            classification="INSUFFICIENT_HISTORY",
            magnitude=None,
            magnitude_basis=None,
            direction=features.direction,
            sample_count=features.sample_count,
            price_movement=features.price_movement,
            point_movement=features.point_movement,
            threshold_version=THRESHOLD_VERSION,
        )

    if features.point_movement is not None:
        magnitude = abs(features.point_movement)
        basis = "point"
        thresholds = POINT_MOVEMENT_THRESHOLDS
    elif features.price_movement is not None:
        magnitude = abs(features.price_movement)
        basis = "price"
        thresholds = PRICE_MOVEMENT_THRESHOLDS
    else:
        # Sufficient history but neither movement is computable (e.g. a
        # side present in the latest snapshot with no matching side in
        # the opening one) -- nothing to classify as anomalous; NORMAL,
        # never a fabricated magnitude.
        magnitude = None
        basis = None
        thresholds = None

    classification = "NORMAL"
    if thresholds is not None:
        if magnitude >= thresholds["SEVERE"]:
            classification = "SEVERE"
        elif magnitude >= thresholds["ELEVATED"]:
            classification = "ELEVATED"
        elif magnitude >= thresholds["WATCH"]:
            classification = "WATCH"

    return MarketMovementClassification(
        sportsbook=features.sportsbook,
        market_type=features.market_type,
        side=features.side,
        classification=classification,
        magnitude=magnitude,
        magnitude_basis=basis,
        direction=features.direction,
        sample_count=features.sample_count,
        price_movement=features.price_movement,
        point_movement=features.point_movement,
        threshold_version=THRESHOLD_VERSION,
    )


def movement_windows(snapshots: list[dict]) -> dict[tuple[str, str], tuple[datetime, datetime]]:
    """One `(first_captured_at, last_captured_at)` pair per
    `(sportsbook, market_type)` group, from the same raw `odds_snapshots`
    rows `app.features.market.compute_line_movement` consumes. Kept
    separate from that module rather than extending
    `LineMovementFeatures` itself (Milestone 4.5, frozen, already
    consumed by `ClosingLineMovementAgent`) -- this milestone needs
    timestamps that dataclass was never designed to carry, and adding
    them there would be an unrelated-consumer schema change to code
    outside this milestone's own scope."""
    groups: dict[tuple[str, str], list[datetime]] = {}
    for row in snapshots:
        key = (row["sportsbook"], row["market_type"])
        groups.setdefault(key, []).append(_parse_ts(row["captured_at"]))
    return {key: (min(timestamps), max(timestamps)) for key, timestamps in groups.items()}


def check_explanatory_evidence(
    *,
    window_start: datetime,
    window_end: datetime,
    injury_reports: list[dict] = (),
    weather_snapshots: list[dict] = (),
    depth_chart_snapshots: list[dict] = (),
    news_articles: list[dict] = (),
) -> ExplanatoryEvidenceResult:
    """Whether ANY explanatory-evidence category has a candidate match
    within `[window_start - EXPLANATORY_EVIDENCE_LOOKBACK, window_end]`.
    Each input list is a list of already-fetched rows carrying their own
    timestamp field (`captured_at` for injury/weather/lineup,
    `ingested_at`/`published_at` for news, per each table's real
    schema -- Volume 3 §4/§4.4). A match is recorded as a category +
    timestamp + small honest reference (id, and for news only, the
    already-documented `headline`/`article_url` columns) -- never the
    full raw jsonb payload for injury/weather/lineup, since this module
    has no confirmed knowledge of what those payloads actually contain
    (Volume 3 §4's own `report_data`/`weather_data`/`depth_chart_data`
    are deliberately undocumented-shape jsonb) and inventing a summary
    of them would be exactly the kind of fabricated structure this
    project's persistence layer already refuses elsewhere."""
    lookback_start = window_start - EXPLANATORY_EVIDENCE_LOOKBACK
    matches: list[ExplanatoryEvidenceMatch] = []

    for row in injury_reports:
        ts = _parse_ts(row["captured_at"])
        if lookback_start <= ts <= window_end:
            matches.append(ExplanatoryEvidenceMatch(category="injury", observed_at=ts, reference={"id": row.get("id")}))

    for row in weather_snapshots:
        ts = _parse_ts(row["captured_at"])
        if lookback_start <= ts <= window_end:
            matches.append(ExplanatoryEvidenceMatch(category="weather", observed_at=ts, reference={"id": row.get("id")}))

    for row in depth_chart_snapshots:
        ts = _parse_ts(row["captured_at"])
        if lookback_start <= ts <= window_end:
            matches.append(
                ExplanatoryEvidenceMatch(
                    category="lineup", observed_at=ts, reference={"id": row.get("id"), "team_id": row.get("team_id")}
                )
            )

    for row in news_articles:
        raw_ts = row.get("ingested_at") or row.get("published_at")
        if raw_ts is None:
            continue
        ts = _parse_ts(raw_ts)
        if lookback_start <= ts <= window_end:
            matches.append(
                ExplanatoryEvidenceMatch(
                    category="news",
                    observed_at=ts,
                    reference={"id": row.get("id"), "headline": row.get("headline"), "article_url": row.get("article_url")},
                )
            )

    return ExplanatoryEvidenceResult(explained=bool(matches), matches=tuple(matches))


def assess_market_integrity(
    features: LineMovementFeatures,
    *,
    window: tuple[datetime, datetime] | None,
    injury_reports: list[dict] = (),
    weather_snapshots: list[dict] = (),
    depth_chart_snapshots: list[dict] = (),
    news_articles: list[dict] = (),
) -> MarketIntegrityAssessment:
    """Classifies one `LineMovementFeatures` row and, only when the
    classification actually qualifies as a detected movement (WATCH,
    ELEVATED, or SEVERE -- NORMAL and INSUFFICIENT_HISTORY are not
    "movement detected" in the sense this check cares about), runs the
    explanatory-evidence check against it. `signal` is `None` for a
    non-qualifying classification -- "was this explained" is not even a
    meaningful question when nothing anomalous was detected.

    `window=None` (no timestamps available to bound a check, e.g. a
    caller that only has features and no raw snapshot rows) never
    guesses a window -- it is treated as "no evidence could be checked",
    which conservatively resolves to `SIGNAL_UNEXPLAINED` (an unverified
    claim of "explained" would be worse than an honest "we couldn't
    check")."""
    classification = classify_market_movement(features)
    if classification.classification not in _QUALIFYING_CLASSIFICATIONS:
        return MarketIntegrityAssessment(classification=classification, explanatory=None, signal=None)

    if window is None:
        explanatory = ExplanatoryEvidenceResult(explained=False, matches=())
    else:
        window_start, window_end = window
        explanatory = check_explanatory_evidence(
            window_start=window_start,
            window_end=window_end,
            injury_reports=injury_reports,
            weather_snapshots=weather_snapshots,
            depth_chart_snapshots=depth_chart_snapshots,
            news_articles=news_articles,
        )

    signal = SIGNAL_EXPLAINED if explanatory.explained else SIGNAL_UNEXPLAINED
    return MarketIntegrityAssessment(classification=classification, explanatory=explanatory, signal=signal)
