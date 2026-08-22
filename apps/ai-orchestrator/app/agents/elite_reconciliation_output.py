"""The Elite second-pass reconciliation's dedicated output contract
(Milestone 4.7, Decision K). Deliberately NOT `MetaAgentOutput` -- Mac's
explicit instruction: "Meta Agent and Elite reconciliation perform
different jobs and should remain semantically separate." Kept minimal --
only the fields actually needed, no speculative additions.

Same hard rule as `MetaAgentOutput.confidence_adjustment` (Milestone 4.2)
and for the identical reason: reconciliation may preserve confidence
(0) or reduce it, never increase it. Enforced at construction time, not
left to prompt instructions alone.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EliteReconciliationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1)
    candidate_key: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    confidence_adjustment: float
    supporting_evidence: list[str]
    would_change_mind_if: str = Field(min_length=1)

    @field_validator("confidence_adjustment")
    @classmethod
    def confidence_adjustment_must_not_be_positive(cls, value: float) -> float:
        """Hard rule, identical in spirit to MetaAgentOutput's own
        (Milestone 4.2, Volume 4 Section 2.6): Elite reconciliation may
        never increase a candidate's confidence."""
        if value > 0:
            raise ValueError(f"confidence_adjustment must be <= 0, got {value!r}")
        return value
