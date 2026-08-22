"""The provider-neutral betting-candidate identity (Milestone 4.6,
Decision G). Introduced because nothing in Volume 4 specifies which
market/selection a committee run's Probability Modeling Agent is
actually producing a probability *for* -- `AgentOutput.directional_lean`
can only speak to one side (home/away/over/under) at a time, so one
sequential-chain run must be scoped to exactly one concrete wager.

Distinct from `recommendation_id` (Mac's own words): `candidate_key`
identifies *the potential wager being evaluated*; `recommendation_id`
identifies *the overall recommendation-analysis cycle* it was evaluated
within. One cycle may evaluate many candidates -- Phase 5 later compares
them to decide the actual recommendation shape (single/parlay/no-bet),
which stays entirely out of this milestone's scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarketCandidate:
    """One concrete, priced wager -- e.g. "KC moneyline -125" or "Over
    47.5 -105". `point` is `None` for moneyline (no line, just a price)."""

    game_id: str
    sportsbook: str
    market_type: str  # 'moneyline' | 'spread' | 'total' | 'prop'
    selection: str  # team name, "Over"/"Under", or a player+prop description
    american_odds: int | None
    point: float | None
    observed_at: datetime


def candidate_key(candidate: MarketCandidate) -> str:
    """A deterministic, stable string identity for one candidate --
    used both as `recommendation_agent_outputs.candidate_key` and
    embedded in every persisted deterministic payload for auditability.
    Two candidates with identical (game_id, sportsbook, market_type,
    selection, point) are the same candidate, even if observed at
    different times -- `observed_at` is deliberately excluded from the
    key so repeated evaluations of the same wager over time share one
    key, matching the "history may legitimately repeat" design (no
    uniqueness constraint) approved for this column."""
    point_component = "none" if candidate.point is None else str(candidate.point)
    return f"{candidate.game_id}:{candidate.sportsbook}:{candidate.market_type}:{candidate.selection}:{point_component}"
