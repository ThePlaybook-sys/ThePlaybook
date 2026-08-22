"""Vegas Line Agent (Milestone 4.5, Volume 4 Section 2.4).

RAW FACTS: the full `odds_snapshots` history for this game (every
sportsbook/market_type observation, oldest first), read verbatim from
`context.odds_history` -- never recomputed here.

DETERMINISTIC FEATURES (Blueprint v5.0 Section 1.1 -- application math,
never left to the model): `context.line_movement`, one
`LineMovementFeatures` per `(sportsbook, market_type, side)` combination,
computed by `app.features.market.compute_line_movement`.

AI REASONING (this agent's actual job): "What is the current line
actually implying, and is that implication sound?" -- interpreting market
significance and pricing context from the facts/features above. It does
NOT calculate movement itself; every number it reasons over is already
computed."""
from __future__ import annotations

from dataclasses import asdict

from app.agents.base_agent import ContextDataAgent
from app.agents.context import AgentContext


class VegasLineAgent(ContextDataAgent):
    agent_name = "vegas_line_agent"
    task_type = "vegas_line_analysis"

    def build_evidence(self, context: AgentContext) -> dict:
        return {
            "odds_history": context.odds_history,
            "line_movement": (
                [asdict(feature) for feature in context.line_movement] if context.line_movement is not None else None
            ),
        }
