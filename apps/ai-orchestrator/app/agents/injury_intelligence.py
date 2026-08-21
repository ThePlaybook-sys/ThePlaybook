"""Injury Intelligence Agent (Milestone 4.4, Volume 4 Section 2.2).

RAW FACTS (Decision 6): injury designation, description, player
identity, roster/depth-chart position -- all read verbatim from
`daily_game_intelligence.injuries` (Milestone 3E-5's real Injury
Worker), never recomputed here.

AI REASONING (this agent's actual job): likely football significance,
positional impact, replacement context, uncertainty -- never fabricated
if the raw evidence is missing.
"""
from __future__ import annotations

from app.agents.base_agent import ContextDataAgent
from app.agents.context import AgentContext


class InjuryIntelligenceAgent(ContextDataAgent):
    agent_name = "injury_intelligence_agent"
    task_type = "injury_analysis"

    def build_evidence(self, context: AgentContext) -> dict:
        return {"injuries": context.injuries}
