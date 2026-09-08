"""Venue contextual dimension (Phase 8.1 Foundation Pass, 2026-09-08).
Real data source: `venues` + `games.venue_id`/`.venue_type`, the
canonical sport-agnostic architecture Phase 8.0.5 Pass 2 built (2026-09-07)
-- reused here with zero redesign, the multi-sport architecture rule's
own proof point.

**"Similarity" here means literal venue identity, not a statistical
distance.** Unlike weather/market, there is no meaningful notion of "a
somewhat similar venue" -- two games either share the exact same
`venue_id` or they don't. `similarity_score` is therefore always `1.0`
when any comparable exists (the venue IS the same one, not merely
alike) and `None` when it doesn't -- disclosed explicitly, not presented
as a computed distance metric the way the other dimensions' scores are.

**SoFi's unresolved roof type stays `None`, never invented (Phase 8.0.5
Pass 2's locked precedent, held again here).** `venue_type` is reported
exactly as `games`/`venues` carries it -- `True`/`False`/`None`, never
coerced."""
from __future__ import annotations

from datetime import datetime, timezone

from app.context_intelligence.models import ContextualDimensionResult, ProvenanceRef
from app.context_intelligence.scoring import INSUFFICIENT_SAMPLE_FLOOR, confidence_score, parse_ts, recency_weight

_STANDING_CONFOUNDER = (
    "No real completed-game outcome data exists for any tracked game yet -- this describes real "
    "venue identity and metadata only, never a predictive or outcome-linked claim."
)
_IDENTITY_CONFOUNDER = (
    "similarity_score reflects literal venue identity (the exact same venue_id), not a computed "
    "distance metric -- there is no partial-similarity concept for venues in this dimension."
)

_CONTEXT_DIMENSIONS_USED = ("venue_id", "venue_type", "stadium")


def compute_venue_context(
    *,
    game: dict | None,
    venue: dict | None,
    other_games_sharing_venue: list[dict],
    now: datetime | None = None,
) -> ContextualDimensionResult:
    """Pure function over already-fetched rows -- no I/O, directly
    unit-testable."""
    now = now or datetime.now(timezone.utc)

    if game is None:
        return ContextualDimensionResult(
            dimension="venue",
            context_dimensions_used=(),
            sample_size=0,
            similarity_score=None,
            recency_weighting=None,
            confidence=None,
            confounders=(_STANDING_CONFOUNDER,),
            insufficient_evidence=True,
            insufficient_evidence_reason="game not found",
            provenance=(),
            facts={},
        )

    facts = {
        "venue_id": game.get("venue_id"),
        "stadium": game.get("stadium"),
        "venue_type": game.get("venue_type"),
        "venue_lat": game.get("venue_lat"),
        "venue_long": game.get("venue_long"),
        "venue_name": venue.get("name") if venue else None,
        "venue_city": venue.get("city") if venue else None,
        "venue_state": venue.get("state") if venue else None,
    }

    venue_id = game.get("venue_id")
    if venue_id is None:
        return ContextualDimensionResult(
            dimension="venue",
            context_dimensions_used=_CONTEXT_DIMENSIONS_USED,
            sample_size=0,
            similarity_score=None,
            recency_weighting=None,
            confidence=None,
            confounders=(_STANDING_CONFOUNDER, "this game has no canonical venue_id resolved yet"),
            insufficient_evidence=True,
            insufficient_evidence_reason="no canonical venue_id resolved for this game yet",
            provenance=(),
            facts=facts,
        )

    sample_size = len(other_games_sharing_venue)
    timestamps = sorted(parse_ts(g["scheduled_start"]) for g in other_games_sharing_venue if g.get("scheduled_start"))
    provenance = (
        ProvenanceRef(
            table="venues",
            source=None,
            row_count=1,
            earliest_at=None,
            latest_at=None,
        ),
        ProvenanceRef(
            table="games",
            source=None,
            row_count=sample_size,
            earliest_at=timestamps[0].isoformat() if timestamps else None,
            latest_at=timestamps[-1].isoformat() if timestamps else None,
        ),
    )

    if sample_size < INSUFFICIENT_SAMPLE_FLOOR:
        return ContextualDimensionResult(
            dimension="venue",
            context_dimensions_used=_CONTEXT_DIMENSIONS_USED,
            sample_size=sample_size,
            similarity_score=None,
            recency_weighting=None,
            confidence=None,
            confounders=(
                _STANDING_CONFOUNDER,
                _IDENTITY_CONFOUNDER,
                f"fewer than {INSUFFICIENT_SAMPLE_FLOOR} other real tracked games share this exact venue",
            ),
            insufficient_evidence=True,
            insufficient_evidence_reason=(
                f"only {sample_size} other real tracked game(s) share this venue "
                f"(minimum {INSUFFICIENT_SAMPLE_FLOOR} required)"
            ),
            provenance=provenance,
            facts=facts,
        )

    weights = [recency_weight(ts, now=now) for ts in timestamps]
    avg_recency = sum(weights) / len(weights)
    confidence = confidence_score(sample_size=sample_size, avg_recency_weight=avg_recency, consistency=1.0)

    return ContextualDimensionResult(
        dimension="venue",
        context_dimensions_used=_CONTEXT_DIMENSIONS_USED,
        sample_size=sample_size,
        similarity_score=1.0,
        recency_weighting=round(avg_recency, 4),
        confidence=confidence,
        confounders=(_STANDING_CONFOUNDER, _IDENTITY_CONFOUNDER),
        insufficient_evidence=False,
        insufficient_evidence_reason=None,
        provenance=provenance,
        facts=facts,
    )


__all__ = ["compute_venue_context"]
