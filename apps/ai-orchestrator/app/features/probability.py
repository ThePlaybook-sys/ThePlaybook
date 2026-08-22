"""American-odds conversions (Milestone 4.6, Decision C). Pure,
deterministic, no I/O -- standard sportsbook mathematics, not verbatim
Blueprint text (Volume 4 never states these formulas numerically;
flagged and approved as an implementation decision, 2026-08-22).

American odds of exactly `0` are not a legal price on any real
sportsbook -- rejected here, not silently coerced, matching this
codebase's existing "fail loud on malformed, degrade only on missing"
convention (e.g. `app.persistence.games.GameStatusUnrecognizedError`).
"""
from __future__ import annotations


class InvalidOddsError(ValueError):
    """Raised for a structurally invalid American odds value (e.g. `0`)
    -- never silently coerced into a decimal odds or probability."""


def american_to_decimal(american_odds: int) -> float:
    """Standard American -> decimal odds conversion."""
    if american_odds == 0:
        raise InvalidOddsError(f"american_odds cannot be 0: {american_odds!r}")
    if american_odds > 0:
        return 1 + american_odds / 100
    return 1 + 100 / abs(american_odds)


def implied_probability(american_odds: int) -> float:
    """The book's own single-sided "breakeven" probability implied by
    the price alone -- includes the vig, is NOT a de-vigged/fair market
    probability (Decision C: de-vigging is a deliberate future
    refinement, not built here)."""
    if american_odds == 0:
        raise InvalidOddsError(f"american_odds cannot be 0: {american_odds!r}")
    if american_odds > 0:
        return 100 / (american_odds + 100)
    return abs(american_odds) / (abs(american_odds) + 100)
