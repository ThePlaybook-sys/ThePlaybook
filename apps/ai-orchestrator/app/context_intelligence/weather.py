"""Weather contextual dimension (Phase 8.1 Foundation Pass, 2026-09-08).
Real data source: `weather_snapshots`, real and active since Phase 8.0.5
Weather Activation (2026-09-07).

**Comparable pool: other real weather observations sharing the same
dome/indoor status.** `is_dome` (`True`/`False`/`None` -- SoFi's own
genuinely-unresolved roof type stays `None`, never coerced, per Phase
8.0.5 Pass 2's locked precedent) is the single most meaningful weather-
relevance boundary this codebase already establishes (`app.workers.
weather_worker.venue_is_dome`, sports-intel-layer) -- comparing a dome
game's weather to an outdoor game's would be comparing conditions that
were never going to be relevant to either game in the first place.
Bucket membership is exact-match only: `None` compares only to other
`None` (unresolved-roof) games, never silently folded into the outdoor
bucket.

**Fixture exclusion.** Every real row carries `weather_data.source ==
"weatherapi"` (Phase 8.0.5 Weather Activation's own provenance fix); the
one pre-existing fixture row does not. Both the target lookup and the
comparable pool filter on this explicitly -- fixture data can never enter
either side of a comparison."""
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

#: Disclosed-conservative per-field "beyond this difference, treat as
#: maximally dissimilar" policy defaults -- see `scoring.py`'s own module
#: docstring. Not empirically derived.
TEMP_SCALE_F = 25.0
WIND_SCALE_MPH = 15.0
PRECIP_SCALE_PCT = 50.0

_NUMERIC_FIELDS = (("temperature_f", TEMP_SCALE_F), ("wind_mph", WIND_SCALE_MPH), ("precipitation_pct", PRECIP_SCALE_PCT))

_STANDING_CONFOUNDER = (
    "No real completed-game outcome data exists for any tracked game yet -- this describes "
    "contextual similarity to other tracked games' real weather observations only, never a "
    "predictive or outcome-linked claim."
)

_CONTEXT_DIMENSIONS_USED = ("temperature_f", "wind_mph", "precipitation_pct", "is_dome")


def _is_real(row: dict) -> bool:
    data = row.get("weather_data")
    return isinstance(data, dict) and data.get("source") == "weatherapi"


def compute_weather_context(
    all_weather_rows: list[dict], *, game_id: str, now: datetime | None = None
) -> ContextualDimensionResult:
    """Pure function over already-fetched `weather_snapshots` rows (any
    game, any real/fixture mix) -- no I/O, directly unit-testable."""
    now = now or datetime.now(timezone.utc)
    real_rows = [row for row in all_weather_rows if _is_real(row)]

    target = next((row for row in real_rows if row.get("game_id") == game_id), None)
    if target is None:
        return ContextualDimensionResult(
            dimension="weather",
            context_dimensions_used=(),
            sample_size=0,
            similarity_score=None,
            recency_weighting=None,
            confidence=None,
            confounders=(_STANDING_CONFOUNDER,),
            insufficient_evidence=True,
            insufficient_evidence_reason="no real WeatherAPI observation exists for this game yet",
            provenance=(ProvenanceRef(table="weather_snapshots", source="weatherapi", row_count=len(real_rows), earliest_at=None, latest_at=None),),
            facts={},
        )

    target_data = target["weather_data"]
    target_is_dome = target_data.get("is_dome")
    facts = {
        "temperature_f": target_data.get("temperature_f"),
        "wind_mph": target_data.get("wind_mph"),
        "precipitation_pct": target_data.get("precipitation_pct"),
        "conditions": target_data.get("conditions"),
        "is_dome": target_is_dome,
        "observed_at": target_data.get("observed_at"),
    }

    comparables = [
        row for row in real_rows if row.get("game_id") != game_id and row["weather_data"].get("is_dome") == target_is_dome
    ]
    timestamps = sorted(parse_ts(row["weather_data"].get("observed_at") or row["captured_at"]) for row in comparables)
    provenance = (
        ProvenanceRef(
            table="weather_snapshots",
            source="weatherapi",
            row_count=len(comparables),
            earliest_at=timestamps[0].isoformat() if timestamps else None,
            latest_at=timestamps[-1].isoformat() if timestamps else None,
        ),
    )

    if len(comparables) < INSUFFICIENT_SAMPLE_FLOOR:
        return ContextualDimensionResult(
            dimension="weather",
            context_dimensions_used=_CONTEXT_DIMENSIONS_USED,
            sample_size=len(comparables),
            similarity_score=None,
            recency_weighting=None,
            confidence=None,
            confounders=(
                _STANDING_CONFOUNDER,
                f"fewer than {INSUFFICIENT_SAMPLE_FLOOR} comparable real weather observations exist "
                f"sharing this game's dome status (is_dome={target_is_dome!r})",
            ),
            insufficient_evidence=True,
            insufficient_evidence_reason=(
                f"only {len(comparables)} comparable real weather observation(s) available "
                f"(minimum {INSUFFICIENT_SAMPLE_FLOOR} required)"
            ),
            provenance=provenance,
            facts=facts,
        )

    weights: list[float] = []
    sims: list[float] = []
    for row in comparables:
        data = row["weather_data"]
        observed_at = parse_ts(data.get("observed_at") or row["captured_at"])
        weight = recency_weight(observed_at, now=now)
        weights.append(weight)
        field_sims = [
            numeric_similarity(target_data[field], data[field], scale=scale)
            for field, scale in _NUMERIC_FIELDS
            if target_data.get(field) is not None and data.get(field) is not None
        ]
        sims.append(sum(field_sims) / len(field_sims) if field_sims else 0.0)

    similarity = weighted_mean(list(zip(sims, weights)))
    avg_recency = sum(weights) / len(weights)
    consistency = 1.0 - dispersion(sims)
    confidence = confidence_score(sample_size=len(comparables), avg_recency_weight=avg_recency, consistency=consistency)

    return ContextualDimensionResult(
        dimension="weather",
        context_dimensions_used=_CONTEXT_DIMENSIONS_USED,
        sample_size=len(comparables),
        similarity_score=round(similarity, 4) if similarity is not None else None,
        recency_weighting=round(avg_recency, 4),
        confidence=confidence,
        confounders=(_STANDING_CONFOUNDER,),
        insufficient_evidence=False,
        insufficient_evidence_reason=None,
        provenance=provenance,
        facts=facts,
    )


__all__ = ["compute_weather_context", "TEMP_SCALE_F", "WIND_SCALE_MPH", "PRECIP_SCALE_PCT"]
