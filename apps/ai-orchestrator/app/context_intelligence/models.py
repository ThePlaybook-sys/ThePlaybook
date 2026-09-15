"""Shared output shape for every context-intelligence dimension (Phase
8.1 Foundation Pass, 2026-09-08). One `ContextualDimensionResult` per
dimension (weather/market/news/venue -- real; player_performance/
injuries/roster_role/team_performance/depth_lineup/game_state_pbp --
insufficient-evidence stubs), assembled into one `ContextualIntelligenceResult`
per game by `engine.build_contextual_intelligence`.

**Every field here is required on every dimension, supported or not** --
an insufficient-evidence dimension still returns a complete
`ContextualDimensionResult` with `insufficient_evidence=True` and an
honest empty/`None` payload elsewhere, never a missing key. This is the
concrete mechanism behind HQ's "do not silently omit them in a way that
implies MANSA considered them" instruction: a consumer that iterates
`ContextualIntelligenceResult.dimensions` sees all ten dimensions every
time, each explicitly self-describing whether it has anything real to
say."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

#: The `data_completeness` vocabulary (Player Performance Context
#: Foundation pass, 2026-09-15 -- first recommended by `docs/ops/phase-8-
#: context-assembly-integration-design-2026-09-09.md` Section 1, never
#: implemented until now). Describes **evidence availability**, never
#: prediction confidence -- a dimension can be "joined" (real evidence
#: found) with `confidence=None` (too little of it to say anything about
#: consistency/trend yet), and the two must never be conflated:
#: - `"joined"`: a real row/observation exists for the exact target
#:   entity (or the fact is static/time-invariant), retrieval code
#:   exists, nothing fabricated.
#: - `"partial"`: real data exists but with a named caveat -- current-only
#:   when historical is needed, coverage begins only after some
#:   activation date, or the join resolves at a coarser granularity than
#:   asked for.
#: - `"unavailable"`: no real row, no code path, or schema-only.
#: A dimension that sets this field must never use it to imply anything
#: about `confidence`/`similarity_score` -- those stay exactly what they
#: already were: `None` whenever there isn't enough real evidence to
#: compute them honestly, never inflated because a field merely exists.
DATA_COMPLETENESS_VALUES = ("joined", "partial", "unavailable")


@dataclass(frozen=True)
class ProvenanceRef:
    """One real, traceable data source this dimension's result was
    derived from -- never a fabricated or inferred reference. `source`
    is the provider name (`"weatherapi"`/`"the_odds_api"`/`"gnews"`) when
    the underlying rows carry one, `None` when the table itself has no
    single-provider concept (e.g. `venues`, `games`)."""

    table: str
    source: str | None
    row_count: int
    earliest_at: str | None  # ISO timestamp, or None when not applicable
    latest_at: str | None


@dataclass(frozen=True)
class ContextualDimensionResult:
    dimension: str
    #: The specific real sub-facets actually used to compute this result
    #: (e.g. `("temperature_f", "wind_mph")`) -- empty for an
    #: insufficient-evidence/unsupported dimension, since nothing was
    #: actually used.
    context_dimensions_used: tuple[str, ...]
    #: Count of real comparable historical data points used (excluding
    #: the target game's own row) -- the literal, honest sample size,
    #: never inflated.
    sample_size: int
    #: `None` exactly when `insufficient_evidence` is `True` -- never a
    #: fabricated 0.0 standing in for "we don't know."
    similarity_score: float | None
    recency_weighting: float | None
    confidence: float | None
    #: Standing + dimension-specific caveats, always populated (even a
    #: sufficient-evidence result carries at least the standing
    #: no-outcome-data confounder -- see each dimension module).
    confounders: tuple[str, ...]
    insufficient_evidence: bool
    insufficient_evidence_reason: str | None
    provenance: tuple[ProvenanceRef, ...]
    #: Real, verbatim facts this dimension read for the target game
    #: itself (e.g. its own weather reading) -- never a derived/modeled
    #: value, always traceable back to a real row.
    facts: dict = field(default_factory=dict)
    #: One of `DATA_COMPLETENESS_VALUES`, or `None` for a dimension built
    #: before this field existed (2026-09-08 pass's four real dimensions
    #: and six unsupported stubs are not retrofitted by this pass -- see
    #: `player_performance.py`'s own module docstring for the first real
    #: consumer). `None` here means "not yet classified," never
    #: "unavailable" -- a caller must not treat a missing value as a
    #: negative signal.
    data_completeness: str | None = None

    def to_json(self) -> dict:
        data = asdict(self)
        data["context_dimensions_used"] = list(self.context_dimensions_used)
        data["confounders"] = list(self.confounders)
        data["provenance"] = [asdict(p) for p in self.provenance]
        return data


@dataclass(frozen=True)
class ContextualIntelligenceResult:
    game_id: str
    generated_at: str  # ISO timestamp
    dimensions: dict[str, ContextualDimensionResult]

    def to_json(self) -> dict:
        return {
            "game_id": self.game_id,
            "generated_at": self.generated_at,
            "dimensions": {name: result.to_json() for name, result in self.dimensions.items()},
        }


__all__ = ["ProvenanceRef", "ContextualDimensionResult", "ContextualIntelligenceResult", "DATA_COMPLETENESS_VALUES"]
