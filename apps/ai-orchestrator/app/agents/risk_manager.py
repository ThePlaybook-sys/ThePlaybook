"""The Risk Manager (Milestone 4.6, Decision E). DEGRADED mode: reasons
over `app.features.risk`'s deterministic Bernoulli outcome variance --
Volume 4 Section 2.5's named primary input ("historical variance by bet
type") does not exist anywhere in this schema (confirmed by direct
grep), and `historical_bet_type_variance` is always explicitly `None`
here, never fabricated."""
from __future__ import annotations

from app.agents.committee_context import SequentialDecisionContext
from app.agents.sequential_base import SequentialDecisionAgent


class RiskManagerAgent(SequentialDecisionAgent):
    agent_name = "risk_manager_agent"
    task_type = "risk_manager_analysis"

    def build_evidence(self, context: SequentialDecisionContext) -> dict:
        return {
            "candidate_selection": context.candidate.selection,
            "market_type": context.candidate.market_type,
            "modeled_probability": context.probability.modeled_probability if context.probability else None,
            "ev_per_dollar": context.ev.ev_per_dollar if context.ev else None,
            "bernoulli_outcome_variance": context.risk.bernoulli_outcome_variance if context.risk else None,
            "historical_bet_type_variance": context.risk.historical_bet_type_variance if context.risk else None,
        }
