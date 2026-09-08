"""Market/odds contextual dimension (Phase 8.1 Foundation Pass,
2026-09-08). Real data source: `odds_snapshots`, real and active since
Phase 7.

**Deliberately reuses Milestone 4.5/7.1's existing pure computation,
never duplicates it.** `app.features.market.compute_line_movement` (this
game's own opening/latest/movement/direction facts) and
`app.features.market_integrity.classify_market_movement`/
`check_explanatory_evidence` (WATCH/ELEVATED/SEVERE classification +
temporal-proximity-to-real-evidence presence, never a causal claim) are
called here exactly as they already exist -- this module adds the
NEW thing Phase 8.1 needs on top: a cross-game comparable-pool
similarity/sample-size/confidence framing those two modules were never
designed to produce. `app.orchestration.market_integrity.
assess_game_market_integrity` (the orchestrator that ALSO writes
`market_monitoring_events`) is deliberately NOT called or imported here
-- that write path and its "first real caller" role are reserved for
Milestone 7.2 (Strategy Engine Integration), per that module's own
docstring; this pass only reads and reuses the pure classification/
explanatory-evidence functions, never the writer.

**Cross-game magnitude comparison is restricted to point-based
(spread/total) movement.** Point movement (spread/total points) and
price movement (moneyline American-odds units) are not on the same
scale -- mixing them into one similarity number would be arithmetically
meaningless. Moneyline movement is still reported in `facts` for the
target game itself; it simply never enters the comparable-pool
similarity/confidence computation. This is disclosed as a standing
confounder, not silently done."""
from __future__ import annotations

from datetime import datetime, timezone

from app.context_intelligence.models import ContextualDimensionResult, ProvenanceRef
from app.context_intelligence.scoring import (
    INSUFFICIENT_SAMPLE_FLOOR,
    confidence_score,
    dispersion,
    numeric_similarity,
    parse_ts,
    recency_weight,
    weighted_mean,
)
from app.features.market import LineMovementFeatures, compute_line_movement
from app.features.market_integrity import (
    ExplanatoryEvidenceResult,
    check_explanatory_evidence,
    classify_market_movement,
    movement_windows,
)

#: Disclosed-conservative -- "beyond a 7-point spread/total swing, treat
#: two games' movement as maximally dissimilar." Not empirically derived
#: (see `scoring.py`'s own module docstring).
POINT_MOVEMENT_SCALE = 7.0

_STANDING_CONFOUNDER = (
    "No real completed-game outcome data exists for any tracked game yet -- this describes "
    "contextual similarity to other tracked games' real market movement only, never a predictive "
    "or outcome-linked claim."
)
_SCALE_CONFOUNDER = (
    "Cross-game similarity is computed from point-based (spread/total) movement only -- moneyline "
    "price movement is reported for this game but excluded from the comparable-pool comparison, "
    "since the two are not on the same numeric scale."
)
_TEMPORAL_CONFOUNDER = (
    "Explanatory-evidence presence reflects temporal proximity only (an evidence category was also "
    "observed near a movement window) -- this is never a causal claim about why the market moved."
)

_CONTEXT_DIMENSIONS_USED = ("point_movement", "price_movement", "direction", "explanatory_evidence")


def _own_point_magnitude(features: list[LineMovementFeatures]) -> float | None:
    magnitudes = [abs(f.point_movement) for f in features if f.point_movement is not None]
    return sum(magnitudes) / len(magnitudes) if magnitudes else None


def compute_market_context(
    *,
    game_id: str,
    target_snapshots: list[dict],
    all_odds_rows: list[dict],
    weather_snapshots_for_game: list[dict] = (),
    news_articles_for_teams: list[dict] = (),
    now: datetime | None = None,
) -> ContextualDimensionResult:
    """Pure function over already-fetched rows -- no I/O, directly
    unit-testable. `target_snapshots` is `game_id`'s own `odds_snapshots`
    history (via the existing `app.persistence.odds_snapshots.
    read_odds_snapshots`); `all_odds_rows` is every game's history (via
    the new `app.persistence.context_intelligence_reads.
    read_all_odds_snapshots`), used only to build the comparable pool."""
    now = now or datetime.now(timezone.utc)

    if not target_snapshots:
        return ContextualDimensionResult(
            dimension="market",
            context_dimensions_used=(),
            sample_size=0,
            similarity_score=None,
            recency_weighting=None,
            confidence=None,
            confounders=(_STANDING_CONFOUNDER,),
            insufficient_evidence=True,
            insufficient_evidence_reason="no real odds_snapshots history exists for this game yet",
            provenance=(),
            facts={},
        )

    own_features = compute_line_movement(target_snapshots)
    own_classifications = [classify_market_movement(f) for f in own_features]
    own_windows = movement_windows(target_snapshots)

    explanatory_by_group: dict[str, dict] = {}
    for classification in own_classifications:
        if classification.classification not in ("WATCH", "ELEVATED", "SEVERE"):
            continue
        window = own_windows.get((classification.sportsbook, classification.market_type))
        if window is None:
            continue
        result: ExplanatoryEvidenceResult = check_explanatory_evidence(
            window_start=window[0],
            window_end=window[1],
            weather_snapshots=list(weather_snapshots_for_game),
            news_articles=list(news_articles_for_teams),
        )
        key = f"{classification.sportsbook}:{classification.market_type}:{classification.side}"
        explanatory_by_group[key] = {
            "classification": classification.classification,
            "explained": result.explained,
            "matched_categories": sorted({m.category for m in result.matches}),
        }

    facts = {
        "movement_groups": [
            {
                "sportsbook": f.sportsbook,
                "market_type": f.market_type,
                "side": f.side,
                "opening_point": f.opening_point,
                "latest_point": f.latest_point,
                "point_movement": f.point_movement,
                "opening_price": f.opening_price,
                "latest_price": f.latest_price,
                "price_movement": f.price_movement,
                "direction": f.direction,
                "sample_count": f.sample_count,
                "insufficient_history": f.insufficient_history,
            }
            for f in own_features
        ],
        "explanatory_evidence": explanatory_by_group,
    }

    own_magnitude = _own_point_magnitude(own_features)
    target_latest = max((parse_ts(row["captured_at"]) for row in target_snapshots), default=now)
    provenance = [
        ProvenanceRef(
            table="odds_snapshots",
            source="the_odds_api",
            row_count=len(target_snapshots),
            earliest_at=min(parse_ts(row["captured_at"]) for row in target_snapshots).isoformat(),
            latest_at=target_latest.isoformat(),
        )
    ]

    if own_magnitude is None:
        return ContextualDimensionResult(
            dimension="market",
            context_dimensions_used=_CONTEXT_DIMENSIONS_USED,
            sample_size=0,
            similarity_score=None,
            recency_weighting=None,
            confidence=None,
            confounders=(_STANDING_CONFOUNDER, _SCALE_CONFOUNDER, _TEMPORAL_CONFOUNDER,
                         "no point-based (spread/total) movement is computable for this game yet "
                         "(insufficient history, or only moneyline data captured so far)"),
            insufficient_evidence=True,
            insufficient_evidence_reason="no computable point-based movement exists for this game yet",
            provenance=tuple(provenance),
            facts=facts,
        )

    other_game_magnitudes: dict[str, list[float]] = {}
    other_game_latest: dict[str, datetime] = {}
    for row in all_odds_rows:
        gid = row.get("game_id")
        if gid is None or gid == game_id:
            continue
        other_game_latest[gid] = max(other_game_latest.get(gid, parse_ts(row["captured_at"])), parse_ts(row["captured_at"]))

    grouped: dict[str, list[dict]] = {}
    for row in all_odds_rows:
        gid = row.get("game_id")
        if gid is None or gid == game_id:
            continue
        grouped.setdefault(gid, []).append(row)

    comparable_magnitudes: list[float] = []
    comparable_weights: list[float] = []
    for gid, rows in grouped.items():
        magnitude = _own_point_magnitude(compute_line_movement(rows))
        if magnitude is None:
            continue
        comparable_magnitudes.append(magnitude)
        comparable_weights.append(recency_weight(other_game_latest[gid], now=now))

    sample_size = len(comparable_magnitudes)
    provenance.append(
        ProvenanceRef(
            table="odds_snapshots",
            source="the_odds_api",
            row_count=sample_size,
            earliest_at=None,
            latest_at=None,
        )
    )

    if sample_size < INSUFFICIENT_SAMPLE_FLOOR:
        return ContextualDimensionResult(
            dimension="market",
            context_dimensions_used=_CONTEXT_DIMENSIONS_USED,
            sample_size=sample_size,
            similarity_score=None,
            recency_weighting=None,
            confidence=None,
            confounders=(
                _STANDING_CONFOUNDER,
                _SCALE_CONFOUNDER,
                _TEMPORAL_CONFOUNDER,
                f"fewer than {INSUFFICIENT_SAMPLE_FLOOR} comparable real games with computable "
                "point-based movement exist",
            ),
            insufficient_evidence=True,
            insufficient_evidence_reason=(
                f"only {sample_size} comparable game(s) with computable point-based movement available "
                f"(minimum {INSUFFICIENT_SAMPLE_FLOOR} required)"
            ),
            provenance=tuple(provenance),
            facts=facts,
        )

    sims = [numeric_similarity(own_magnitude, m, scale=POINT_MOVEMENT_SCALE) for m in comparable_magnitudes]
    similarity = weighted_mean(list(zip(sims, comparable_weights)))
    avg_recency = sum(comparable_weights) / len(comparable_weights)
    consistency = 1.0 - dispersion(sims)
    confidence = confidence_score(sample_size=sample_size, avg_recency_weight=avg_recency, consistency=consistency)

    return ContextualDimensionResult(
        dimension="market",
        context_dimensions_used=_CONTEXT_DIMENSIONS_USED,
        sample_size=sample_size,
        similarity_score=round(similarity, 4) if similarity is not None else None,
        recency_weighting=round(avg_recency, 4),
        confidence=confidence,
        confounders=(_STANDING_CONFOUNDER, _SCALE_CONFOUNDER, _TEMPORAL_CONFOUNDER),
        insufficient_evidence=False,
        insufficient_evidence_reason=None,
        provenance=tuple(provenance),
        facts=facts,
    )


__all__ = ["compute_market_context", "POINT_MOVEMENT_SCALE"]
