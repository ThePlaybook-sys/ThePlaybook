"""The smallest deterministic historical Context Assembly package
(Phase 8 Historical Context Assembly V1 pass, 2026-09-15, HQ-authorized
"MANSA -- PHASE 8 HISTORICAL CONTEXT ASSEMBLY V1"). Wraps an already-built
`ContextualIntelligenceResult` (`engine.build_contextual_intelligence`)
into one summary object answering, for every one of its ten dimensions:
**JOINED, PARTIAL, or UNAVAILABLE, and why** -- the package-level
completeness contract the 2026-09-09 design doc first proposed and the
Player Performance Context Foundation pass first implemented (as a
per-dimension field, `data_completeness`), now generalized to every
dimension and rolled up into one assembly-level object.

**This module performs zero I/O and zero new computation over raw data
-- it is a pure, read-only summary of a result the engine already
computed.** Nothing here re-derives `insufficient_evidence`/`confidence`/
`similarity_score`, nothing here scores a prediction, and nothing here is
wired into `build_evidence()` or any recommendation path (see this
module's own "Boundary" note below).

**Completeness describes evidence availability, never prediction
confidence -- restated here because this is the first place all ten
dimensions' completeness states are compared side by side, making the
distinction more important, not less.** A package can (and today, for
the JSN/SEA@NE proof, does) contain JOINED dimensions with zero
computed `confidence` anywhere in the underlying result -- that is
correct, not a bug: "we found real evidence" and "we have enough of it
to trust a derived score" are different questions, and this module never
conflates them. There is deliberately no prediction/probability field
anywhere on `ContextPackage`.

**Derivation rule (generic, applies uniformly to all ten dimensions, no
per-dimension special-casing):**

    if result.data_completeness is not None:      # player_performance already sets this
        completeness = result.data_completeness
    elif not result.insufficient_evidence:
        completeness = "joined"                    # a full, real, sample-adequate result
    elif result.facts:
        completeness = "partial"                    # some real evidence exists, but with a
                                                      # named caveat (e.g. real target-game
                                                      # weather/venue found, too few real
                                                      # comparables to score similarity)
    else:
        completeness = "unavailable"                 # no real row, no code path, or schema-only
                                                       # (this is exactly how every `unsupported.py`
                                                       # stub -- facts={} unconditionally -- already
                                                       # resolves, with zero special-casing needed)

This rule requires no change to `weather.py`/`market.py`/`news.py`/
`venue.py`/`unsupported.py` -- it is derived entirely from fields those
modules already, correctly compute (`insufficient_evidence`, `facts`).

**Point-in-time discipline is inherited, not re-implemented.** Every
dimension already enforces its own point-in-time safety before this
module ever sees the result (`player_performance.py`'s explicit
`target_event_timestamp` rule; `weather.py`/`market.py`/`news.py`/
`venue.py`'s real-data-only, current-game-scoped reads). This module
does not re-verify point-in-time correctness -- it surfaces each real
dimension's own `insufficient_evidence_reason` (when set) as part of
`known_limitations`, and separately exposes `target_event_timestamp`
verbatim so a reader can see exactly what moment this package claims to
be honest "as of."

**Boundary (per this pass's explicit HQ instruction):** does not modify
`app.agents.probability_modeling.ProbabilityModelingAgent.build_evidence`,
does not change recommendation behavior, computes no prediction/
probability/confidence score of its own, makes no provider calls, and
requires no schema change (built entirely from data the engine already
fetches)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.context_intelligence.models import ContextualDimensionResult, ContextualIntelligenceResult, ProvenanceRef

#: Mirrors `models.DATA_COMPLETENESS_VALUES` -- every dimension in a real
#: `ContextPackage` resolves to exactly one of these three, never a
#: fourth value, never omitted.
COMPLETENESS_VALUES = ("joined", "partial", "unavailable")


@dataclass(frozen=True)
class DimensionCompleteness:
    """One dimension's real completeness verdict, with the join identity/
    provenance/reason a reader needs to trust it without re-deriving it
    from the raw `ContextualDimensionResult` themselves."""

    dimension: str
    completeness: str  # one of COMPLETENESS_VALUES
    reason: str | None  # the real insufficient_evidence_reason, when set; None for "joined"
    sample_size: int
    provenance: tuple[ProvenanceRef, ...]

    def to_json(self) -> dict:
        return {
            "dimension": self.dimension,
            "completeness": self.completeness,
            "reason": self.reason,
            "sample_size": self.sample_size,
            "provenance": [
                {
                    "table": p.table,
                    "source": p.source,
                    "row_count": p.row_count,
                    "earliest_at": p.earliest_at,
                    "latest_at": p.latest_at,
                }
                for p in self.provenance
            ],
        }


@dataclass(frozen=True)
class ContextPackage:
    """The package-level summary -- evidence completeness, never model
    confidence. No prediction/probability field exists anywhere on this
    type, deliberately."""

    game_id: str
    player_id: str | None
    generated_at: str
    target_event_timestamp: str
    joined_dimensions: tuple[str, ...]
    partial_dimensions: tuple[str, ...]
    unavailable_dimensions: tuple[str, ...]
    dimension_completeness: dict[str, DimensionCompleteness]
    known_limitations: tuple[str, ...]
    intelligence: ContextualIntelligenceResult = field(repr=False)

    def to_json(self) -> dict:
        return {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "generated_at": self.generated_at,
            "target_event_timestamp": self.target_event_timestamp,
            "joined_dimensions": list(self.joined_dimensions),
            "partial_dimensions": list(self.partial_dimensions),
            "unavailable_dimensions": list(self.unavailable_dimensions),
            "dimension_completeness": {name: dc.to_json() for name, dc in self.dimension_completeness.items()},
            "known_limitations": list(self.known_limitations),
            "intelligence": self.intelligence.to_json(),
        }


def _derive_completeness(result: ContextualDimensionResult) -> str:
    """The one generic derivation rule -- see module docstring. Never
    special-cases a dimension by name."""
    if result.data_completeness is not None:
        return result.data_completeness
    if not result.insufficient_evidence:
        return "joined"
    if result.facts:
        return "partial"
    return "unavailable"


def assemble_context_package(
    intelligence: ContextualIntelligenceResult,
    *,
    player_id: str | None,
    target_event_timestamp: str,
) -> ContextPackage:
    """Pure function over an already-built `ContextualIntelligenceResult`
    -- no I/O, directly unit-testable, matching every other module in
    this package's own convention. Never raises: every dimension already
    present on `intelligence.dimensions` (all ten, always, per `engine.
    build_contextual_intelligence`'s own "never silently omit" guarantee)
    is classified, none skipped, none invented."""
    joined: list[str] = []
    partial: list[str] = []
    unavailable: list[str] = []
    dimension_completeness: dict[str, DimensionCompleteness] = {}
    limitations: set[str] = set()

    for name, result in intelligence.dimensions.items():
        completeness = _derive_completeness(result)
        if completeness == "joined":
            joined.append(name)
        elif completeness == "partial":
            partial.append(name)
        else:
            unavailable.append(name)

        dimension_completeness[name] = DimensionCompleteness(
            dimension=name,
            completeness=completeness,
            reason=result.insufficient_evidence_reason,
            sample_size=result.sample_size,
            provenance=result.provenance,
        )

        if result.insufficient_evidence_reason:
            limitations.add(result.insufficient_evidence_reason)

    return ContextPackage(
        game_id=intelligence.game_id,
        player_id=player_id,
        generated_at=intelligence.generated_at,
        target_event_timestamp=target_event_timestamp,
        joined_dimensions=tuple(sorted(joined)),
        partial_dimensions=tuple(sorted(partial)),
        unavailable_dimensions=tuple(sorted(unavailable)),
        dimension_completeness=dimension_completeness,
        known_limitations=tuple(sorted(limitations)),
        intelligence=intelligence,
    )


__all__ = [
    "COMPLETENESS_VALUES",
    "DimensionCompleteness",
    "ContextPackage",
    "assemble_context_package",
]
