"""The Expected Value Agent (Milestone 4.6, Decision C). Reasons over
`app.features.expected_value`'s already-computed deterministic numbers --
never recomputes EV/edge itself. Uses the ordinary `AgentOutput` contract
(its own `confidence` legitimately means "how confident is this agent in
its EV interpretation," which is distinct from `modeled_probability`)."""
from __future__ import annotations

from app.agents.committee_context import SequentialDecisionContext
from app.agents.sequential_base import SequentialDecisionAgent


class ExpectedValueAgent(SequentialDecisionAgent):
    agent_name = "expected_value_agent"
    task_type = "expected_value_analysis"

    def build_evidence(self, context: SequentialDecisionContext) -> dict:
        return {
            "candidate_selection": context.candidate.selection,
            "american_odds": context.candidate.american_odds,
            "modeled_probability": context.probability.modeled_probability if context.probability else None,
            "confidence_in_probability": context.probability.confidence_in_probability if context.probability else None,
            "decimal_odds": context.ev.decimal_odds if context.ev else None,
            "raw_implied_probability": context.ev.raw_implied_probability if context.ev else None,
            "raw_probability_edge": context.ev.raw_probability_edge if context.ev else None,
            "ev_per_dollar": context.ev.ev_per_dollar if context.ev else None,
        }
