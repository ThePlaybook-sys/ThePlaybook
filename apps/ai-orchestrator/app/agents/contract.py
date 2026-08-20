"""The shared agent output contract (Volume 4 Section 2.1) and the Meta
Agent's distinct post-consensus contract (Volume 4 Section 2.6),
implemented as Pydantic models -- Milestone 4.2.

**CONFIRMED FROM VOLUME 4 Section 2.1 -- the shared contract's exact JSON
shape**, every fan-out agent (all 21, every functional group) must return:

    {
      "agent_name": "injury_intelligence_agent",
      "finding": "short plain-language summary",
      "supporting_evidence": ["specific data points used"],
      "evidence_classification": "data_backed | inference | assumption",
      "directional_lean": "home | away | over | under | none",
      "confidence": 0.0,
      "would_change_mind_if": "explicit invalidation condition"
    }

Every field above is required in the blueprint's own example -- none is
shown as optional or nullable. **This module's own design decision,
flagged explicitly rather than left implicit:** no field on `AgentOutput`
is nullable. An agent facing degraded or missing upstream input (e.g. a
`daily_game_intelligence` category Milestone 4.1 read back as `None`)
must still resolve that into a complete, valid judgment -- typically a
low `confidence`, `evidence_classification="assumption"`, and a
`finding`/`would_change_mind_if` that names the missing data -- rather
than the contract accepting a partial/null shape as a substitute for that
judgment. This is the null-not-neutral discipline Milestone 4.1 preserves
on the *read* side, carried through to what an agent is allowed to
*emit*: a `None` may flow into an agent's input, but never out of its
contract-validated output unresolved.

**DERIVED, not verbatim-stated -- `confidence` and `polarization_score`
bounds.** Volume 4 never states "confidence is a 0.0-1.0 float" in so
many words in Section 2.1 itself, but every other place the document
discusses a confidence-shaped number treats it as exactly that range: the
0.55 "No Bet Today" floor (Section 4.2), the calibration buckets ("0.55-
0.60, 0.60-0.65", Section 5), and the schema's own
`numeric(5,4)`-typed confidence columns (Volume 3 Section 5). This module
enforces `0.0 <= confidence <= 1.0` and `0.0 <= polarization_score <=
1.0` on that basis -- a DERIVED constraint, not a blind guess, but
flagged here in case Mac wants it loosened or tightened once real agent
output exists to check it against.

**CONFIRMED FROM VOLUME 4 Section 2.6 -- the Meta Agent's distinct,
smaller contract** (the 22nd agent, runs after Consensus, never a
fan-out participant):

    {
      "agent_name": "meta_agent",
      "polarization_score": 0.0,
      "uncertainty_flag": false,
      "confidence_adjustment": 0.0,
      "reasoning": "plain-language summary of committee health for this
      recommendation"
    }

**CONFIRMED, hard rule, enforced here as a validator, not a convention:**
`confidence_adjustment` "can only ever be zero or negative" (Section
2.6's own words) -- "This is a hard rule, not a convention: letting the
Meta Agent boost confidence would create a backdoor around the anti-
overfitting guardrails already built into the adaptive weighting system."
A positive value raises here, at construction time, not downstream in the
Consensus Engine (Milestone 4.7) where the mistake would be far more
expensive to trace back to its source.

`agent_name` is typed as a non-empty `str` on `AgentOutput`, not an enum
of the real 22-agent roster -- Volume 4 Section 2 gives the committee's
Title Case names and functional grouping, not a canonical machine-
readable slug for all 22 (only two snake_case examples appear anywhere in
the blueprint text: `injury_intelligence_agent` and `meta_agent`).
Constraining this field to an exact enum belongs to whichever later
milestone actually assigns real slugs to all 22 agents (Milestone 4.4/
4.5's own build work, not this contract-only milestone) -- inventing 20
slugs here would be exactly the kind of unauthorized decision this
project's discipline exists to avoid making silently.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceClassification(str, Enum):
    """CONFIRMED FROM VOLUME 4 Section 2.1 -- exact three-value vocabulary."""

    DATA_BACKED = "data_backed"
    INFERENCE = "inference"
    ASSUMPTION = "assumption"


class DirectionalLean(str, Enum):
    """CONFIRMED FROM VOLUME 4 Section 2.1 -- exact five-value vocabulary."""

    HOME = "home"
    AWAY = "away"
    OVER = "over"
    UNDER = "under"
    NONE = "none"


class AgentOutput(BaseModel):
    """The shared fan-out agent output contract -- Volume 4 Section 2.1.
    Applies identically to all 21 fan-out agents (Context & Data, Matchup
    & Form, Market, Decision & Advisory) -- Volume 4 states no per-
    category variation on this shape anywhere.
    """

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1)
    finding: str = Field(min_length=1)
    supporting_evidence: list[str]
    evidence_classification: EvidenceClassification
    directional_lean: DirectionalLean
    confidence: float = Field(ge=0.0, le=1.0)
    would_change_mind_if: str = Field(min_length=1)


class MetaAgentOutput(BaseModel):
    """The Meta Agent's distinct post-consensus contract -- Volume 4
    Section 2.6. The 22nd agent; never a fan-out participant, never
    validated against `AgentOutput`."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1)
    polarization_score: float = Field(ge=0.0, le=1.0)
    uncertainty_flag: bool
    confidence_adjustment: float
    reasoning: str = Field(min_length=1)

    @field_validator("confidence_adjustment")
    @classmethod
    def confidence_adjustment_must_not_be_positive(cls, value: float) -> float:
        """CONFIRMED FROM VOLUME 4 Section 2.6 -- hard rule: 'can only
        ever be zero or negative.' Enforced at construction time so a
        violation is caught the instant the Meta Agent produces it, not
        somewhere downstream in the Consensus Engine."""
        if value > 0:
            raise ValueError(
                f"confidence_adjustment must be <= 0 (Volume 4 Section 2.6's hard rule), got {value!r}"
            )
        return value
