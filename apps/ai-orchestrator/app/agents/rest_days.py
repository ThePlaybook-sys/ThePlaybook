"""Rest Days Agent (Milestone 4.4, Volume 4 Section 2.2).

DETERMINISTIC FACT (Decision 6): `rest_days`/`season_opener` are already
fully computed by Master Refresh (Phase 3E-2) -- read verbatim from
`daily_game_intelligence.rest`. This agent recomputes nothing; its only
job is interpreting whether a given rest-days differential matters for
this specific matchup.
"""
from __future__ import annotations

from app.agents.base_agent import ContextDataAgent
from app.agents.context import AgentContext


class RestDaysAgent(ContextDataAgent):
    agent_name = "rest_days_agent"
    task_type = "rest_days_analysis"

    def build_evidence(self, context: AgentContext) -> dict:
        return {"rest": context.rest}
