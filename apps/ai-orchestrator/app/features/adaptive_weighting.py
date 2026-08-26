"""Milestone 5.5's deterministic Adaptive Agent Weighting engine (Decisions
1-27, approved 2026-08-27). Pure functions only -- no I/O, no model calls
-- exactly mirroring `app.features.grading`/`app.features.postgame_review`
before it. `app.orchestration.adaptive_weighting` ties this to persistence.

**V1 is PROPOSE-ONLY (Decision 2).** Nothing in this module, or anywhere
in this milestone, writes `agents.current_weight`. Every function here
computes what a weight change WOULD be; applying one is a separate,
not-yet-authorized future capability.

**IMPLEMENTATION VALIDATION vs. EMPIRICAL VALIDATION (Decision 25) --
read this before trusting any output of this module in production.** This
engine is proven correct against deterministic fixture/synthetic evidence
(the same testing discipline used throughout Phase 5). As of this
milestone, ZERO real graded recommendations exist anywhere in this
system (live-verified during the Milestone 5.5 inspection). A weight
PROPOSAL this engine computes is never a claim that any agent's
performance has been empirically validated, that the algorithm improves
betting outcomes, or that any agent deserves a real-world adjustment --
those claims require real graded evidence this system has not yet
produced.

**`learning_rate = 0.25` (Decision 9/28) is an INITIAL PRODUCT-POLICY
DEFAULT, not an empirically-derived or optimal value.** It is frozen
onto every persisted evaluation (`adaptive_weight_proposals.learning_rate`)
specifically so a future change to this constant is historically
traceable, never silently reinterpreting old proposals under a new rate.

**Classifiable-observation population (Decision 1), reusing Milestone
5.4's own established boundary, not a new rule:** an observation counts
only when the leg has an authoritative deterministic grade producing a
realized direction (`WIN`/`LOSS` only -- `app.features.postgame_review.
realized_direction` already returns `None` for anything else), the
agent's own output for that leg's game-level committee run succeeded,
and the agent's `directional_lean` is on-axis (matches or opposes the
realized direction) per `app.features.consensus.lean_factor`'s existing
three-state rule. `PUSH`/`VOID_NO_ACTION`/`PENDING_MISSING_DATA`/
`NOT_APPLICABLE` legs, `no_bet`/`bankroll_preservation` products,
unsupported `player_prop` legs (never graded at all), failed agents, and
off-axis/abstaining agents are never observations -- they are absent,
never a fabricated zero.

**Scope boundary, disclosed, not silently assumed:** only the nine
GAME-LEVEL committee-voting agents (the ones fan-out persists with
`candidate_key IS NULL` and a real `directional_lean`) can ever produce a
classifiable observation. Probability Modeling, Expected Value, Risk
Manager, Bankroll Coach (candidate-level), and Meta/Elite-reconciliation
(review, not directional-vote) agents will always evaluate to
`sample_size = 0` under this V1 methodology -- not because they're
excluded by name, but because they structurally never emit a comparable
directional call. Every agent in `agents` is still evaluated every cycle
(Decision 14's "preserve the fact rather than silently drop" extended
here) -- a zero-sample result for a non-voting agent is an honest,
persisted fact, not a hidden omission.

**ROI (Return on Investment) is a disclosed approximation (Decision 4),
not real trading P&L (Profit and Loss) -- exact where the graded leg's
own price makes it exact, a flat-unit proxy elsewhere:** the graded leg's
frozen `decimal_odds` is the price of the RECOMMENDED side only -- there
is no second, independently-priced line anywhere in this system for the
opposite side of that same market. So:

- An agent whose lean matches whichever side the graded leg's own
  `decimal_odds` actually prices (i.e. `correct` on a `WIN`, or
  `underperforming` on a `LOSS` -- both cases mean "this agent's lean
  equals the recommended side") gets that leg's own EXACT realized
  profit/loss (`decimal_odds - 1` on a win, a flat `-1.0` on a loss --
  losing a flat stake always costs exactly the stake, regardless of odds).
- An agent whose lean is the OPPOSITE of the recommended side (`correct`
  on a `LOSS` -- this agent leaned the side that actually won, but that
  side is not the graded leg, so its real price is unknown; or
  `underperforming` on a `WIN` -- this agent leaned the side that lost,
  whose real price is likewise unknown) gets a flat `+1.0`/`-1.0`
  unit-stake proxy instead, since no real price exists to use.

This is model-performance accounting, not a claim about what either side
would have actually paid out at a real sportsbook -- documented
explicitly per Decision 4's own "represents MODEL PERFORMANCE, not user
gambling results" framing. Losing a flat stake is always exactly `-1.0`
regardless of which side lost or what its odds were -- that half of the
rule is not an approximation, it is exact by definition of a flat-stake
bet."""
from __future__ import annotations

from dataclasses import dataclass

from app.features.consensus import lean_factor

WEIGHTING_VERSION = "v1"

#: Decision 9/28 -- APPROVED V1 DEFAULT, NOT EMPIRICALLY OPTIMIZED, SUBJECT
#: TO FUTURE REVIEW. Frozen onto every persisted proposal so a future
#: change is historically traceable, never silently reinterpreted.
ADAPTIVE_WEIGHT_LEARNING_RATE = 0.25

#: Decision 10 -- Blueprint-approved, exact.
ADAPTIVE_WEIGHT_MAX_CHANGE_FRACTION = 0.10

#: Decision 1 -- Blueprint's "200 recommendations," reinterpreted for the
#: Phase 5 architecture as 200 classifiable graded-leg observations PER AGENT.
ADAPTIVE_WEIGHT_MIN_SAMPLE_SIZE = 200

#: Decision 8 -- hard minimum, never silently widened.
ADAPTIVE_WEIGHT_MIN_WINDOW_DAYS = 90

_TERMINAL_DIRECTIONAL_OUTCOMES = ("WIN", "LOSS")


class EvaluationWindowTooShortError(Exception):
    """Raised when a requested evaluation window is narrower than
    `ADAPTIVE_WEIGHT_MIN_WINDOW_DAYS` -- the whole evaluation request is
    rejected outright (Decision 8), never silently widened, and no
    per-agent proposal rows are computed or persisted for it."""


@dataclass(frozen=True)
class ObservationInput:
    """One classifiable (leg, agent) pair's already-resolved facts --
    everything `classify_and_price_observation` needs, nothing it has to
    re-derive."""

    recommendation_leg_grade_event_id: str
    directional_lean: str
    realized_direction: str
    outcome: str  # "WIN" | "LOSS" -- the graded leg's own outcome
    decimal_odds: float


@dataclass(frozen=True)
class Observation:
    recommendation_leg_grade_event_id: str
    classification: str  # "correct" | "underperforming"
    directional_lean: str
    notional_pnl: float


def leg_notional_pnl(*, outcome: str, decimal_odds: float) -> float:
    """The graded leg's own flat-1-unit realized profit/loss -- `WIN`
    returns the decimal-odds profit, `LOSS` returns a flat `-1.0`. Only
    ever called for `outcome in ("WIN", "LOSS")` -- a leg with any other
    outcome was never a classifiable observation in the first place
    (Decision 1), so this function makes no attempt to handle one."""
    if outcome == "WIN":
        return decimal_odds - 1.0
    if outcome == "LOSS":
        return -1.0
    raise ValueError(f"leg_notional_pnl only accepts WIN/LOSS outcomes, got {outcome!r}")


def classify_and_price_observation(observation_input: ObservationInput) -> Observation | None:
    """Returns `None` when the agent's `directional_lean` is off-axis or
    `"none"` (not a classifiable observation at all -- `lean_factor`'s
    existing three-state rule, reused verbatim, never a new comparison
    rule). Otherwise returns the priced `Observation` -- see module
    docstring for the exact-vs-proxy pricing rationale: `correct`+`WIN`
    and `underperforming`+`LOSS` both mean "this agent's lean equals the
    recommended side," so they get that leg's own exact realized pnl;
    the other two combinations mean "this agent leaned the side the
    graded leg was never priced for," so they get a flat unit-stake
    proxy instead."""
    factor = lean_factor(observation_input.directional_lean, observation_input.realized_direction)
    if factor is None:
        return None
    leg_pnl = leg_notional_pnl(outcome=observation_input.outcome, decimal_odds=observation_input.decimal_odds)
    if factor == 1.0:
        pnl = leg_pnl if observation_input.outcome == "WIN" else 1.0
        return Observation(
            recommendation_leg_grade_event_id=observation_input.recommendation_leg_grade_event_id,
            classification="correct",
            directional_lean=observation_input.directional_lean,
            notional_pnl=pnl,
        )
    # factor == 0.3 -- the only remaining non-None case of lean_factor's three states.
    pnl = leg_pnl if observation_input.outcome == "LOSS" else -1.0
    return Observation(
        recommendation_leg_grade_event_id=observation_input.recommendation_leg_grade_event_id,
        classification="underperforming",
        directional_lean=observation_input.directional_lean,
        notional_pnl=pnl,
    )


def aggregate_roi(observations: list[Observation]) -> float | None:
    """`None` (never `0.0`) when there are zero observations -- an
    agent with no classifiable evidence has no ROI, not a neutral one."""
    if not observations:
        return None
    return sum(o.notional_pnl for o in observations) / len(observations)


def committee_average_roi(agent_rois: list[float | None]) -> float | None:
    """The simple mean of every agent's own ROI that could be computed
    (Decision: agents with `sample_size = 0` contribute no term at all,
    never a fabricated `0.0` that would drag the average toward zero).
    `None` only in the fully-degenerate case where no agent in the
    entire committee has any classifiable observation this window."""
    real_rois = [r for r in agent_rois if r is not None]
    if not real_rois:
        return None
    return sum(real_rois) / len(real_rois)


def compute_performance_delta(*, agent_roi: float | None, committee_average_roi_value: float | None) -> float | None:
    if agent_roi is None or committee_average_roi_value is None:
        return None
    return agent_roi - committee_average_roi_value


def compute_raw_proposed_weight(
    *, current_weight: float, learning_rate: float, performance_delta: float | None
) -> float | None:
    """`new_weight = current_weight * (1 + learning_rate * performance_delta)`
    -- Volume 4 Section 6.1's formula, verbatim. `None` propagates from an
    undefined `performance_delta` (zero observations) rather than
    fabricating a weight change from nothing."""
    if performance_delta is None:
        return None
    return current_weight * (1 + learning_rate * performance_delta)


def clamp_to_max_change(
    *, current_weight: float, raw_proposed_weight: float | None, max_change_fraction: float = ADAPTIVE_WEIGHT_MAX_CHANGE_FRACTION
) -> float | None:
    """Clamps `raw_proposed_weight` to within `current_weight * (1 ±
    max_change_fraction)` (Decision 10) -- the learning rate does NOT
    replace this cap; this is a separate, always-applied ceiling/floor on
    top of whatever the raw formula produced."""
    if raw_proposed_weight is None:
        return None
    lower = current_weight * (1 - max_change_fraction)
    upper = current_weight * (1 + max_change_fraction)
    return max(lower, min(upper, raw_proposed_weight))


def check_sample_size_guardrail(sample_size: int, *, minimum: int = ADAPTIVE_WEIGHT_MIN_SAMPLE_SIZE) -> bool:
    return sample_size >= minimum


def validate_evaluation_window(
    *, window_start_days_before_end: int, minimum_days: int = ADAPTIVE_WEIGHT_MIN_WINDOW_DAYS
) -> None:
    """Raises `EvaluationWindowTooShortError` for a window narrower than
    `minimum_days` (Decision 8) -- callers must call this BEFORE
    evaluating any agent; a rejected window produces zero proposal rows
    for the whole committee, not a per-agent rejection."""
    if window_start_days_before_end < minimum_days:
        raise EvaluationWindowTooShortError(
            f"evaluation window of {window_start_days_before_end} day(s) is narrower than the "
            f"{minimum_days}-day hard minimum (Decision 8) -- rejected, never silently widened"
        )
