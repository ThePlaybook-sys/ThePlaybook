"""Explicit insufficient-evidence stubs for every contextual dimension
Phase 8.0.5's own closeout audit confirmed MISSING/INSUFFICIENT or
IMPLEMENTED BUT BLOCKED (2026-09-07/08) -- HQ's explicit instruction:
"do not silently omit them in a way that implies MANSA considered them."

Every one of these six dimensions runs through `engine.
build_contextual_intelligence` on every call, exactly like the four real
ones -- the difference is entirely in the result they produce, not in
whether they run at all. No real data read is attempted for any of them
(there is none to read): this module returns the same fixed, honest
result shape unconditionally, never a query against
`players`/`player_stats`/`team_stats`/`roster_memberships`/
`depth_chart_snapshots`/`injury_reports`/`game_events` -- attempting a
real read against tables confirmed fixture-only or zero-row would only
risk surfacing fixture data as though it were real."""
from __future__ import annotations

from app.context_intelligence.models import ContextualDimensionResult

#: One entry per unsupported dimension, matching Phase 8.0.5's own
#: closeout matrix exactly (`docs/ops/phase-8.0.5-weather-activation-closeout-2026-09-07.md`
#: §7) -- the reason text names which of that matrix's two negative
#: buckets (MISSING/INSUFFICIENT vs. IMPLEMENTED BUT BLOCKED) applies, so
#: a reader of this output can trace it back to the real audit rather
#: than a description invented here.
UNSUPPORTED_DIMENSIONS: dict[str, str] = {
    "player_performance": (
        "No real player identity or player_stats data exists -- `players`/`player_provider_ids` "
        "are fixture/seed-only and `player_stats` rows are fixture-linked (Phase 8.0.5 closeout: "
        "MISSING/INSUFFICIENT). No player-specific contextual claim can be made honestly."
    ),
    "injuries": (
        "BALLDONTLIE Player Injuries entitlement is not currently confirmed active (the account's "
        "invoice is open/unpaid) -- the adapter is complete and correct, but real injury data cannot "
        "be fetched (Phase 8.0.5 closeout: IMPLEMENTED BUT BLOCKED)."
    ),
    "roster_role": (
        "No real roster_memberships data exists -- persistence code is complete "
        "(`app.persistence.roster_ingestion`, sports-intel-layer) but has never been invoked against "
        "a live roster provider (Phase 8.0.5 closeout: MISSING/INSUFFICIENT)."
    ),
    "team_performance": (
        "No real team_stats data exists -- all rows are fixture-linked to seed games "
        "(Phase 8.0.5 closeout: MISSING/INSUFFICIENT)."
    ),
    "depth_lineup": (
        "No real depth_chart_snapshots data exists -- persistence code is complete but has never "
        "been invoked against a live roster/depth-chart provider (Phase 8.0.5 closeout: "
        "MISSING/INSUFFICIENT)."
    ),
    "game_state_pbp": (
        "No real game_events data exists -- persistence code is deliberately raw-capture-only and "
        "explicitly deferred pending the 2026-09-09/10 live-game validation window, which has not "
        "yet occurred (Phase 8.0.5 closeout: MISSING/INSUFFICIENT, blocked by real-world timing, "
        "not by any decision or credential)."
    ),
}


def insufficient_evidence_result(dimension: str) -> ContextualDimensionResult:
    """Returns the fixed, honest insufficient-evidence result for one of
    `UNSUPPORTED_DIMENSIONS`. Raises `KeyError` for any other name --
    callers must not invent a reason for a dimension not already named
    here."""
    reason = UNSUPPORTED_DIMENSIONS[dimension]
    return ContextualDimensionResult(
        dimension=dimension,
        context_dimensions_used=(),
        sample_size=0,
        similarity_score=None,
        recency_weighting=None,
        confidence=None,
        confounders=(reason,),
        insufficient_evidence=True,
        insufficient_evidence_reason=reason,
        provenance=(),
        facts={},
    )


__all__ = ["UNSUPPORTED_DIMENSIONS", "insufficient_evidence_result"]
