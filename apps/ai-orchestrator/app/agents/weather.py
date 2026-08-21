"""Weather Agent (Milestone 4.4, Volume 4 Section 2.2).

RAW FACTS (Decision 6): temperature, wind, precipitation, conditions,
venue type -- read verbatim from `daily_game_intelligence.weather` and
`.stadium` (real Weather Worker, Milestone 3E-6), never recomputed here.

AI REASONING (this agent's actual job): likely football/game-market
significance of the raw weather facts -- never invented if the evidence
is missing (e.g. a dome game correctly has no weather to reason about
at all, and that is itself the reasoning, not a gap to fill in).
"""
from __future__ import annotations

from app.agents.base_agent import ContextDataAgent
from app.agents.context import AgentContext


class WeatherAgent(ContextDataAgent):
    agent_name = "weather_agent"
    task_type = "weather_analysis"

    def build_evidence(self, context: AgentContext) -> dict:
        return {"weather": context.weather, "stadium": context.stadium}
