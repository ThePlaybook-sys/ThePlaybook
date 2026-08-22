"""The Elite second-pass reconciliation agent (Milestone 4.7, Volume 4
Section 4.3). Triggered only when `agreement_variance > 0.25` AND the
requesting user's subscription tier is exactly `"elite"` -- never for
free/pro, never for an unknown/missing tier.

**Evidence, per Section 4.3's own literal text** ("given all 21 [built:
6] fan-out agents' raw outputs plus the Meta Agent's reasoning field"):
this agent does NOT re-run the fan-out committee -- it reasons over the
same already-persisted findings the Meta Agent saw, plus the Meta
Agent's own `reasoning`. Routes via the `consensus_reconciliation`
task_type, already seeded in dev config since Milestone 4.1 (the
strongest model tier, used sparingly and only when triggered)."""
from __future__ import annotations

from app.agents.consensus_review_base import ConsensusReviewAgent
from app.agents.consensus_review_context import ConsensusReviewContext
from app.agents.elite_reconciliation_output import EliteReconciliationOutput


class EliteReconciliationAgent(ConsensusReviewAgent):
    agent_name = "consensus_reconciliation_agent"
    task_type = "consensus_reconciliation"
    response_model = EliteReconciliationOutput

    def build_evidence(self, context: ConsensusReviewContext) -> dict:
        return {
            "candidate_key": context.candidate_key,
            "agent_findings": list(context.agent_findings),
            "meta_reasoning": context.meta_reasoning,
            "aggregate_confidence": context.aggregate_confidence,
            "agreement_variance": context.agreement_variance,
        }
