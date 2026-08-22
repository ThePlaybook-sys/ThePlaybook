"""The Probability Modeling Agent (Milestone 4.6, Decision B). First step
of the sequential Decision & Advisory chain -- consumes the fan-out
committee's own outputs plus honest participation metadata, produces a
`ProbabilityModelOutput` (not `AgentOutput`) scoped to one specific
`MarketCandidate`.
"""
from __future__ import annotations

from app.agents.committee_context import SequentialDecisionContext
from app.agents.probability_output import ProbabilityModelOutput
from app.agents.sequential_base import SequentialDecisionAgent
from app.features.candidate import candidate_key


class ProbabilityModelingAgent(SequentialDecisionAgent):
    agent_name = "probability_modeling_agent"
    task_type = "probability_modeling_analysis"
    response_model = ProbabilityModelOutput

    def build_evidence(self, context: SequentialDecisionContext) -> dict:
        return {
            "candidate": {
                "candidate_key": candidate_key(context.candidate),
                "game_id": context.candidate.game_id,
                "sportsbook": context.candidate.sportsbook,
                "market_type": context.candidate.market_type,
                "selection": context.candidate.selection,
                "american_odds": context.candidate.american_odds,
                "point": context.candidate.point,
            },
            "upstream_findings": [output.model_dump(mode="json") for output in context.upstream_outputs],
            "participation": {
                "configured_agent_count": len(context.participation.configured_agents),
                "built_agent_count": len(context.participation.built_agents),
                "deferred_agents": sorted(context.participation.deferred_agents),
                "successful_agents": sorted(context.participation.successful_agents),
                "failed_agents": sorted(context.participation.failed_agents),
                "fan_out_status": context.participation.fan_out_status,
                "committee_completeness": context.participation.committee_completeness,
            },
        }
