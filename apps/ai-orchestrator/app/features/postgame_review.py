"""Milestone 5.4's Postgame Review narrative layer -- the deterministic
half only (pure functions, no I/O, no model calls), exactly mirroring
`app.features.explainability`'s split between deterministic derivation
(here) and orchestration (`app.orchestration.postgame_review_narrative`,
which owns the actual LLM call + persistence).

**Independent from `GRADING_VERSION`** (Decision BO) -- `POSTGAME_REVIEW_
VERSION` governs only the narrative/derivation logic in this module and
its orchestration counterpart, never the deterministic grade itself.

**Agent correctness (Decision BT) reuses `app.features.consensus.
lean_factor` verbatim** -- the exact same three-state comparison already
used to classify an agent's vote against a candidate's OWN chosen
direction (Milestone 4.7) is reused here to classify an agent's vote
against the REALIZED direction (what the game actually did), never a
new/looser comparison. `realized_direction` derives that value from
already-computed grading facts (the candidate's own direction plus its
WIN/LOSS outcome) rather than re-deriving it from final_score a second
time -- if the candidate's direction was right, reality matched it
(WIN); if wrong, reality was the opposite (LOSS). PUSH/VOID_NO_ACTION/
PENDING_MISSING_DATA have no single "reality was on this side" fact to
compare against, so `realized_direction` is `None` for those, and no
agent is classified either way -- exactly Decision BT's "where objective
comparison is unavailable, do not classify," never confidence- or
majority-based.

**`build_factual_deltas` is conservatively scoped to `None` in this
milestone** -- a real weather/injury/line-movement delta needs an
activation-time-vs-kickoff-time snapshot diff this milestone does not
build (no new snapshot-diffing infrastructure was in scope here; see the
Milestone 5.4 completion report). Returning `None` honestly reports "not
computed," never a fabricated or approximated delta -- the same
"structurally extensible but inactive" treatment already given to
player-prop grading (Decision BJ)."""
from __future__ import annotations

from pydantic import BaseModel

from app.features.consensus import lean_factor

POSTGAME_REVIEW_VERSION = "v1"

_OPPOSITE = {"home": "away", "away": "home", "over": "under", "under": "over"}

_TERMINAL_WIN_LOSS = ("WIN", "LOSS")


class PostgameReviewNarrativeOutput(BaseModel):
    """The LLM's only contract: three narrative strings. No grade,
    outcome, EV, confidence, or Explainability field is representable
    here at all -- there is structurally nothing for the model to alter
    (Decision BU)."""

    outcome_summary: str
    why_it_won_or_lost: str
    learning_notes: str


def realized_direction(*, candidate_direction: str | None, outcome: str) -> str | None:
    """`None` unless the leg's own `outcome` is `WIN` or `LOSS` AND it
    had a real `candidate_direction` in the first place (a `prop` leg,
    or any leg `resolve_candidate_direction` couldn't resolve, has
    `candidate_direction=None` -- never classified)."""
    if candidate_direction is None or outcome not in _TERMINAL_WIN_LOSS:
        return None
    return candidate_direction if outcome == "WIN" else _OPPOSITE[candidate_direction]


def classify_agent_correctness(
    agent_rows: list[dict], *, realized_direction_value: str | None
) -> tuple[list[str] | None, list[str] | None]:
    """Returns `(correct_agents, underperforming_agents)` -- both `None`
    (not `[]`) when `realized_direction_value` is `None`, distinguishing
    "we could not objectively evaluate this leg's agents at all" from
    "we evaluated them and none qualified." `agent_rows` is the same
    flattened game-level shape `app.features.explainability.
    build_contributing_agents` already consumes."""
    if realized_direction_value is None:
        return None, None
    correct: list[str] = []
    underperforming: list[str] = []
    for row in agent_rows:
        factor = lean_factor(row["directional_lean"], realized_direction_value)
        if factor == 1.0:
            correct.append(row["agent_name"])
        elif factor == 0.3:
            underperforming.append(row["agent_name"])
        # factor is None -- "none" lean or off-axis -- not classified either way.
    return correct, underperforming


def build_factual_deltas() -> dict | None:
    """See module docstring -- conservatively `None` in this milestone."""
    return None
