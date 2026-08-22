"""The Bankroll Coach (Milestone 4.6, Decision F). Reasons over
`app.features.kelly`'s deterministic stake math -- never calculates the
authoritative numeric stake itself. `bankroll_profile=None`, or a profile
with `optional_bankroll=None` (confirmed live: every real `user_profiles`
row in dev has a `NULL` bankroll, including both Phase-1 fixture rows),
means `context.kelly.stake` is already `None` by the time this agent
runs -- it must report that honestly, never inventing a dollar amount."""
from __future__ import annotations

from app.agents.committee_context import SequentialDecisionContext
from app.agents.sequential_base import SequentialDecisionAgent


class BankrollCoachAgent(SequentialDecisionAgent):
    agent_name = "bankroll_coach_agent"
    task_type = "bankroll_coach_analysis"

    def build_evidence(self, context: SequentialDecisionContext) -> dict:
        profile = context.bankroll_profile or {}
        return {
            "candidate_selection": context.candidate.selection,
            "modeled_probability": context.probability.modeled_probability if context.probability else None,
            "ev_per_dollar": context.ev.ev_per_dollar if context.ev else None,
            "bernoulli_outcome_variance": context.risk.bernoulli_outcome_variance if context.risk else None,
            "bankroll": profile.get("optional_bankroll"),
            "risk_tolerance": profile.get("risk_tolerance"),
            "full_kelly_fraction": context.kelly.full_kelly_fraction if context.kelly else None,
            "quarter_kelly_fraction": context.kelly.quarter_kelly_fraction if context.kelly else None,
            "risk_tolerance_multiplier": context.kelly.risk_tolerance_multiplier if context.kelly else None,
            "recommended_stake": context.kelly.stake if context.kelly else None,
        }
