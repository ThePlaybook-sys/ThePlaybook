"""Deterministic Recommendation Strategy Engine (Milestone 5.1). Pure
functions only -- no I/O, mirroring every other `app.features` module.

**Finalized rules this module implements (Decisions X/Y/Z/AA/AB/AC/AM/AN,
approved 2026-08-25 -- restated here as the authoritative version, not
re-decided):**

- **Qualification (Decision X):** a candidate qualifies only when BOTH
  `final_aggregate_confidence >= 0.55` AND `ev_per_dollar > 0`. Neither
  gate alone is sufficient.
- **Ranking / tie-break / same-market conflict resolution (Decision AM),
  one hierarchy for both purposes:** `ev_per_dollar` DESC, then
  `final_aggregate_confidence` DESC, then `candidate_key` ASC purely for
  determinism -- never a betting-quality signal (Decision Y: EV is the
  sole primary signal, confidence is secondary tie-break only, never a
  blended score).
- **Same-market exclusivity (Decision AC):** at most one candidate per
  (game, market_type) survives for moneyline/spread/total -- the two
  possible selections for one of these markets are opposing sides of the
  SAME wager and can never both be selected. Player props are exempt --
  distinct props on the same game are not opposing sides of one market.
- **Per-game `no_bet` (Decision AA):** zero qualifying candidates for a
  specific game -- a per-game fact, independent of the rest of the slate.
- **Slate-level `bankroll_preservation` (Decision AB):** zero qualifying
  candidates ANYWHERE in the entire slate -- no arbitrary percentage
  threshold, no partial-slate version of this outcome exists.
- **`single` vs `multiple_singles`:** driven purely by the total COUNT of
  selected legs across the whole slate after conflict resolution -- not
  by game count. Exactly one selected leg anywhere in the slate is
  `single` (game-scoped, tied to that leg's own game). Two or more is
  `multiple_singles` (slate-scoped) -- one game may legitimately
  contribute more than one leg (e.g. a qualifying moneyline AND a
  qualifying total are different markets, not opposing sides).
- **Parlays stay inactive (Decision AD/AN):** `same_game_parlay`/
  `multi_game_parlay` are never produced by this module -- no
  correlation, joint-probability, or combined-variance math exists
  anywhere in this codebase (confirmed by grep). This module has no
  parlay branch at all, not a disabled one.

No blended score, no new confidence thresholds, no risk_level mapping,
and no synthetic parlay calculation are invented here -- exactly per
Mac's explicit instruction accompanying Decisions X-AN.
"""
from __future__ import annotations

from dataclasses import dataclass

_DIRECTIONAL_MARKET_TYPES = ("moneyline", "spread", "total")


@dataclass(frozen=True)
class EvaluatedCandidate:
    """One candidate's Phase 4 output, as needed by the Strategy Engine --
    assembled by the caller from `MarketCandidate` (`app.features.
    candidate`), `EVResult` (`app.features.expected_value`), and the
    `consensus_snapshots` row that produced its `final_aggregate_confidence`.
    Every field here is a frozen, already-computed fact; this module never
    recomputes EV/confidence/odds itself."""

    game_id: str
    recommendation_id: str
    consensus_snapshot_id: str
    candidate_key: str
    market_type: str
    selection: str
    sportsbook: str
    american_odds: int
    point: float | None
    decimal_odds: float
    ev_per_dollar: float
    final_aggregate_confidence: float


@dataclass(frozen=True)
class GameCandidates:
    game_id: str
    recommendation_id: str
    candidates: tuple[EvaluatedCandidate, ...]


@dataclass(frozen=True)
class GameDecision:
    game_id: str
    recommendation_id: str
    outcome: str  # "no_bet" | "qualified"
    legs: tuple[EvaluatedCandidate, ...]


@dataclass(frozen=True)
class SlateStrategyResult:
    outcome: str  # "single" | "multiple_singles" | "bankroll_preservation"
    game_decisions: tuple[GameDecision, ...]
    legs: tuple[EvaluatedCandidate, ...]  # in final presentation order; empty for bankroll_preservation


def qualifies(candidate: EvaluatedCandidate, *, confidence_floor: float = 0.55) -> bool:
    """Decision X: both gates required. `confidence_floor` defaults to
    the Volume 4 §4.2 floor already established in Milestone 4.7/4.8
    (`app.features.consensus.is_below_confidence_floor`) -- exposed as a
    parameter only so a test can probe the boundary, never intended to be
    called with a different value in production."""
    return candidate.final_aggregate_confidence >= confidence_floor and candidate.ev_per_dollar > 0


def rank_key(candidate: EvaluatedCandidate) -> tuple[float, float, str]:
    """Decision AM's exact hierarchy, as a sort key for ascending sort:
    `ev_per_dollar` DESC -> negate; `final_aggregate_confidence` DESC ->
    negate; `candidate_key` ASC -> unchanged (pure determinism, never a
    quality signal)."""
    return (-candidate.ev_per_dollar, -candidate.final_aggregate_confidence, candidate.candidate_key)


def resolve_market_conflicts(qualifying: list[EvaluatedCandidate]) -> list[EvaluatedCandidate]:
    """Decision AC, applied within one game's already-qualifying
    candidates: for each directional market_type (moneyline/spread/total)
    with more than one qualifying candidate, keep only the single
    best-ranked one (Decision AM hierarchy) -- the two candidates are
    opposing sides of the SAME market and cannot both be selected. Prop
    candidates are never conflict-resolved against each other -- distinct
    props are independent markets, not opposing sides of one."""
    by_market: dict[str, list[EvaluatedCandidate]] = {}
    props: list[EvaluatedCandidate] = []
    for candidate in qualifying:
        if candidate.market_type in _DIRECTIONAL_MARKET_TYPES:
            by_market.setdefault(candidate.market_type, []).append(candidate)
        else:
            props.append(candidate)

    resolved: list[EvaluatedCandidate] = list(props)
    for group in by_market.values():
        resolved.append(min(group, key=rank_key))
    return resolved


def compute_strategy_decision(games: list[GameCandidates]) -> SlateStrategyResult:
    """The full Milestone 5.1 decision tree for one slate. `games` must
    include EVERY game considered this slate cycle, including one whose
    `candidates` is empty or contains only non-qualifying candidates --
    omitting a game here is indistinguishable from that game never having
    been analyzed, which would silently break the per-game `no_bet`
    guarantee (Decision AA)."""
    game_decisions: list[GameDecision] = []
    all_selected_legs: list[EvaluatedCandidate] = []

    for game in games:
        qualifying = [c for c in game.candidates if qualifies(c)]
        if not qualifying:
            game_decisions.append(
                GameDecision(game_id=game.game_id, recommendation_id=game.recommendation_id, outcome="no_bet", legs=())
            )
            continue
        resolved = resolve_market_conflicts(qualifying)
        game_decisions.append(
            GameDecision(
                game_id=game.game_id,
                recommendation_id=game.recommendation_id,
                outcome="qualified",
                legs=tuple(resolved),
            )
        )
        all_selected_legs.extend(resolved)

    if not all_selected_legs:
        return SlateStrategyResult(outcome="bankroll_preservation", game_decisions=tuple(game_decisions), legs=())

    ordered = tuple(sorted(all_selected_legs, key=rank_key))
    if len(ordered) == 1:
        return SlateStrategyResult(outcome="single", game_decisions=tuple(game_decisions), legs=ordered)
    return SlateStrategyResult(outcome="multiple_singles", game_decisions=tuple(game_decisions), legs=ordered)
