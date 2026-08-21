"""Travel & Fatigue Agent (Milestone 4.4, Volume 4 Section 2.2, Decision
5). Consumes `app.features.travel`'s already-computed deterministic
features -- travel distance (Haversine, application math), timezone
shift (zoneinfo-resolved, DST-correct), international-game flag, and
existing rest-days context. This agent never calculates geographic
distance or rest arithmetic itself -- both are supplied as facts; its
only job is reasoning about football/fatigue significance.
"""
from __future__ import annotations

from app.agents.base_agent import ContextDataAgent
from app.agents.context import AgentContext


class TravelFatigueAgent(ContextDataAgent):
    agent_name = "travel_fatigue_agent"
    task_type = "travel_fatigue_analysis"

    def build_evidence(self, context: AgentContext) -> dict:
        travel = context.travel
        return {
            "travel_distance_miles": travel.travel_distance_miles,
            "timezone_shift_hours": travel.timezone_shift_hours,
            "is_international_game": travel.is_international_game,
            "consecutive_road_games": travel.consecutive_road_games,
            "rest": context.rest,
        }
