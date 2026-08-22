"""The Meta Agent (Milestone 4.7, Volume 4 Section 2.6). Reuses the
already-built `MetaAgentOutput` contract (Milestone 4.2) unchanged --
its `confidence_adjustment <= 0` validator remains authoritative,
enforced at construction time, never relied on via prompt instructions
alone."""
from __future__ import annotations

from app.agents.consensus_review_base import ConsensusReviewAgent
from app.agents.consensus_review_context import ConsensusReviewContext
from app.agents.contract import MetaAgentOutput


class MetaAgent(ConsensusReviewAgent):
    agent_name = "meta_agent"
    task_type = "meta_agent_review"
    response_model = MetaAgentOutput

    def build_evidence(self, context: ConsensusReviewContext) -> dict:
        findings_by_category: dict[str, list[dict]] = {}
        for finding in context.agent_findings:
            findings_by_category.setdefault(finding["category"], []).append(finding)
        return {
            "candidate_key": context.candidate_key,
            "aggregate_confidence": context.aggregate_confidence,
            "agreement_variance": context.agreement_variance,
            "findings_by_category": findings_by_category,
            "participation": {
                "committee_completeness": context.participation.committee_completeness,
                "fan_out_status": context.participation.fan_out_status,
                "deferred_agents": sorted(context.participation.deferred_agents),
                "failed_agents": sorted(context.participation.failed_agents),
            },
        }
