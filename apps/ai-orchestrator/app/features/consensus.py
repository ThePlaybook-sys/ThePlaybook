"""Deterministic Consensus Engine math (Milestone 4.7). Pure functions
only -- no I/O, mirroring every other `app.features` module's separation
of computation from persistence.

**Decision I (approved 2026-08-22) -- candidate-anchored consensus, an
intentional Blueprint evolution.** Volume 4 Section 4.1 was written
before any candidate concept existed: `directional_agreement[i]` is
defined there as "1.0 if the agent's `directional_lean` matches THE
MAJORITY LEAN" -- a self-referential vote among the fan-out committee,
with no reference to a specific wager. Milestone 4.6 introduced
candidate-scoped evaluation, which Section 4.1's text never anticipated,
and taken literally would let off-axis agents (e.g. a totals-relevant
lean) outvote on-axis ones for a moneyline candidate. Per Mac's explicit
decision, this module answers a different, candidate-anchored question
instead: "how strongly does the available committee support THIS
SPECIFIC CANDIDATE?" -- every agent's lean is compared against the
candidate's own resolved direction, never against a self-referential
committee majority. No separate game-level majority score is maintained.

**The exact deterministic three-state formula (documented per Mac's own
"if the denominator treatment becomes ambiguous, stop and document it"
instruction -- Volume 4's original formula has no accommodation for a
third "no directional opinion" state):**

- An agent's `directional_lean` exactly matches the candidate's resolved
  direction -> `lean_factor = 1.0` ("supports").
- An agent's `directional_lean` is the exact opposite value on the SAME
  axis (home<->away, over<->under) -> `lean_factor = 0.3` ("opposes").
- An agent's `directional_lean == "none"`, OR its lean is on a
  DIFFERENT axis than the candidate's own (e.g. a home/away lean
  compared against a totals candidate) -> `lean_factor = None` ("no
  directional vote"). This extends Mac's explicit "none is not
  opposition" rule to the off-axis case by the same reasoning: an
  agent that never expressed an opinion on this candidate's actual
  question cannot honestly be counted as support or opposition either.

**Non-voting agents are excluded from both the numerator and
denominator of `aggregate_confidence` and from `agreement_variance`'s
sample** -- not assigned a neutral 1.0 (which Mac's instruction
explicitly forbids treating as the same thing as genuine support), and
not fabricated a value the original formula has no slot for. They
remain visible in `ParticipationMetadata` (unaffected by this module)
and in the caller's own accounting of `voting_agent_count`/
`non_voting_agent_count` (below) -- their existence is never hidden,
only excluded from a calculation their answer doesn't speak to.

**`agreement_variance` has no formula given anywhere in Volume 3 or 4**
(confirmed by direct grep) -- implemented here as the population
variance of the voting agents' own `lean_factor` values (a measure of
how uniformly the committee agreed vs. disagreed on this candidate),
consistent with the EV/Kelly precedent (Milestone 4.6) of using standard
mathematics and flagging it explicitly as an implementation decision
where the Blueprint is imprecise, not a verbatim Blueprint formula.

**Player-prop candidates are excluded from directional agreement
entirely** (Decision I) -- `resolve_candidate_direction` returns `None`
for `market_type == "prop"`, which makes every agent a non-voter,
which makes `aggregate_confidence` `None` for a prop candidate. This is
an honest, undecided result, not a fabricated number -- Player Prop
Agent and player-prop directional semantics are not yet built.
"""
from __future__ import annotations

from dataclasses import dataclass

#: CONFIRMED FROM app.agents.contract.DirectionalLean -- the exact
#: five-value vocabulary every AgentOutput uses.
_OPPOSITE = {"home": "away", "away": "home", "over": "under", "under": "over"}


class CandidateDirectionError(ValueError):
    """Raised when a moneyline/spread/total candidate's `selection`
    cannot be resolved against the game's actual home_team/away_team (or
    against "Over"/"Under" for a total) -- malformed data, never
    silently treated as a non-voting case. Per Mac's explicit
    instruction: never infer team side from array position or text
    ordering -- resolution is exact-string-match against the
    authoritative home_team/away_team identity only."""


def resolve_candidate_direction(*, market_type: str, selection: str, home_team: str, away_team: str) -> str | None:
    """Returns `"home"`/`"away"`/`"over"`/`"under"` for a resolvable
    moneyline/spread/total candidate, or `None` for a `"prop"` (or any
    other unrecognized) market_type -- deliberately excluded from
    directional agreement, not malformed. Raises `CandidateDirectionError`
    for a moneyline/spread/total candidate whose `selection` doesn't
    match any legal value -- that IS malformed, never silently
    downgraded to "no vote"."""
    if market_type in ("moneyline", "spread"):
        if selection == home_team:
            return "home"
        if selection == away_team:
            return "away"
        raise CandidateDirectionError(
            f"selection {selection!r} matches neither home_team={home_team!r} nor away_team={away_team!r}"
        )
    if market_type == "total":
        if selection == "Over":
            return "over"
        if selection == "Under":
            return "under"
        raise CandidateDirectionError(f"total candidate selection must be 'Over' or 'Under', got {selection!r}")
    return None  # prop or any other market_type -- deliberately excluded (Decision I), not malformed


def lean_factor(agent_lean: str, candidate_direction: str | None) -> float | None:
    """Returns `1.0` (supports), `0.3` (opposes), or `None` (no
    directional vote -- see module docstring for the exact three-state
    rule, including the off-axis extension)."""
    if candidate_direction is None:
        return None
    if agent_lean == "none":
        return None
    if agent_lean == candidate_direction:
        return 1.0
    if agent_lean == _OPPOSITE.get(candidate_direction):
        return 0.3
    return None  # off-axis: e.g. a home/away lean against a totals candidate


@dataclass(frozen=True)
class ConsensusResult:
    aggregate_confidence: float | None
    agreement_variance: float | None
    voting_agent_count: int
    non_voting_agent_count: int


def compute_consensus(agent_rows: list[dict], *, candidate_direction: str | None) -> ConsensusResult:
    """`agent_rows` is one game-level fan-out agent's already-persisted
    output per entry: `{"directional_lean": ..., "confidence": ...,
    "evidence_classification": ..., "weight_applied": ...}` -- read back
    from `recommendation_agent_outputs` (Decision J: the FROZEN
    persisted weight, never a fresh `agents.current_weight` join).

    Zero voting agents (including zero `agent_rows` at all, i.e. a
    FAILED fan-out cycle, or every agent being a non-voter for this
    candidate) degrades every field to `None` -- never a fabricated
    aggregate_confidence of 0.0 or 1.0."""
    voting: list[tuple[float, float, float]] = []
    non_voting_count = 0

    for row in agent_rows:
        factor = lean_factor(row["directional_lean"], candidate_direction)
        if factor is None:
            non_voting_count += 1
            continue
        effective_weight = row["weight_applied"] * (0.5 if row["evidence_classification"] == "assumption" else 1.0)
        voting.append((row["confidence"], effective_weight, factor))

    if not voting:
        return ConsensusResult(
            aggregate_confidence=None, agreement_variance=None, voting_agent_count=0, non_voting_agent_count=non_voting_count
        )

    total_weight = sum(weight for _, weight, _ in voting)
    if total_weight <= 0:
        return ConsensusResult(
            aggregate_confidence=None,
            agreement_variance=None,
            voting_agent_count=len(voting),
            non_voting_agent_count=non_voting_count,
        )

    aggregate_confidence = sum(confidence * weight * factor for confidence, weight, factor in voting) / total_weight

    factors = [factor for _, _, factor in voting]
    mean_factor = sum(factors) / len(factors)
    agreement_variance = sum((factor - mean_factor) ** 2 for factor in factors) / len(factors)

    return ConsensusResult(
        aggregate_confidence=aggregate_confidence,
        agreement_variance=agreement_variance,
        voting_agent_count=len(voting),
        non_voting_agent_count=non_voting_count,
    )


def apply_confidence_adjustment(current: float, adjustment: float) -> float:
    """`final = max(0.0, current + adjustment)` -- `adjustment` must
    already be `<= 0` (enforced by `MetaAgentOutput`/
    `EliteReconciliationOutput`'s own validators before this is ever
    called). Applying this in sequence (Meta, then conditionally Elite)
    guarantees the result can never exceed the value it started from,
    since every adjustment is non-positive and the floor clamp only ever
    lowers, never raises, the number."""
    return max(0.0, current + adjustment)


def is_below_confidence_floor(final_aggregate_confidence: float, *, floor: float = 0.55) -> bool:
    """`< floor` is below; `== floor` passes -- exact boundary, per
    Mac's explicit 0.5499/0.5500/0.5501 example."""
    return final_aggregate_confidence < floor


#: CONFIRMED FROM VOLUME 4 Section 4.3 -- exact threshold, exclusive
#: ("> 0.25", not ">="). See `should_trigger_elite_second_pass`'s
#: docstring for a real, freshly-discovered mathematical tension this
#: threshold has against this module's `agreement_variance` formula.
ELITE_VARIANCE_THRESHOLD = 0.25
ELITE_TIER = "elite"


def should_trigger_elite_second_pass(agreement_variance: float | None, tier: str | None) -> bool:
    """`agreement_variance > 0.25` AND `tier == "elite"` -- exact match,
    never a substring/case-insensitive comparison. `None` for either
    argument (no computable variance, or no/unknown/non-elite tier)
    never triggers.

    **A real mathematical tension, discovered while testing this
    milestone, flagged rather than silently worked around:** this
    module's `agreement_variance` is the population variance of
    `lean_factor` values, which only ever take one of two values (`1.0`
    supports, `0.3` opposes) once non-voters are excluded. The maximum
    possible population variance of a two-valued {1.0, 0.3} distribution
    is `p(1-p)(1.0-0.3)^2`, maximized at a 50/50 split: `0.25 * 0.49 =
    0.1225` -- meaning `agreement_variance` computed by this module can
    NEVER exceed `0.1225` for any real input, so `> 0.25` can never fire
    naturally. This ceiling is a property of Volume 4's own specified
    `0.3` fractional disagreement penalty applied to ANY binary
    agreement scheme (this predates Milestone 4.7's candidate-anchoring
    redesign entirely -- the original game-level majority-vote formula
    has the exact same two-value ceiling). This function's LOGIC is
    still implemented and tested correctly in isolation; whether the
    fractional penalty, the 0.25 threshold, or the variance formula
    itself needs to change is a real, open architecture question
    surfaced for Mac's decision, not resolved here."""
    if agreement_variance is None or tier is None:
        return False
    return agreement_variance > ELITE_VARIANCE_THRESHOLD and tier == ELITE_TIER
