"""The Probability Modeling Agent's dedicated output contract (Milestone
4.6, Decision B). Deliberately NOT `AgentOutput` -- Mac's explicit
instruction: "Do NOT semantically reuse AgentOutput.confidence as
p_model." `AgentOutput.confidence` answers "how confident is this agent
in its own analysis?"; it must never be repurposed to mean "what is the
probability this wager wins?" -- those are different quantities (a
committee can be 0.80 confident in its analysis while the modeled win
probability is 0.55).

`modeled_probability` and `confidence_in_probability` are two distinct
numbers, both required, both independently bounded 0.0-1.0:
`modeled_probability` is the calibrated estimate itself;
`confidence_in_probability` is how strongly that specific estimate
should be trusted (e.g. 0.57 modeled win probability, held with only
0.72 confidence because upstream committee participation was partial).

Deliberately minimal -- trimmed from a longer conceptual field list to
avoid two fields covering the same ground (a separate
"uncertainty"/"missing-input context" field would duplicate what
`confidence_in_probability` + `would_change_mind_if` already express).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProbabilityModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1)
    #: References `app.features.candidate.candidate_key` for the exact
    #: `MarketCandidate` this probability was modeled for -- never a
    #: game-level or committee-level judgment.
    candidate_key: str = Field(min_length=1)
    #: Which side/selection `modeled_probability` applies to -- echoes
    #: the evaluated candidate's own `selection` (e.g. a team name,
    #: "Over"/"Under").
    selection: str = Field(min_length=1)
    modeled_probability: float = Field(ge=0.0, le=1.0)
    confidence_in_probability: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1)
    supporting_evidence: list[str]
    would_change_mind_if: str = Field(min_length=1)
