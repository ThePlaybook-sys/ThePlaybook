"""Closing Line Movement Agent (Milestone 4.5, Volume 4 Section 2.4).

RAW FACTS / DETERMINISTIC FEATURES: `context.line_movement` -- the same
`app.features.market.LineMovementFeatures` list `VegasLineAgent` reasons
over, one per `(sportsbook, market_type, side)` combination.

AI REASONING (this agent's actual job): "How has the line moved since
open, and what does that movement suggest?" -- interpreting the
already-computed `opening_*`/`latest_*`/`*_movement`/`direction` fields.

**Terminology discipline (Mac's explicit instruction, Milestone 4.5):**
this agent never sees or reasons over a "closing line," because no
reliable closing-line marker exists anywhere in this architecture yet --
the Odds Worker's cadence (Phase 3E-4) is adaptive/window-aware, not
close-triggered, so there is no signal distinguishing "the last snapshot
we happened to capture" from "the market's actual close." Every feature
here is named `latest_*`, and `closing_line_status` below makes that
limitation explicit in the evidence itself, so the model is never invited
to guess which observation was the close."""
from __future__ import annotations

from dataclasses import asdict

from app.agents.base_agent import ContextDataAgent
from app.agents.context import AgentContext

#: Deliberately explicit, not omitted -- states the real limitation
#: directly in the evidence rather than letting "latest" silently stand
#: in for "closing" (Milestone 4.5, terminology discipline above).
_CLOSING_LINE_STATUS = (
    "No confirmed closing-line marker exists in this architecture yet. "
    "Every 'latest_price'/'latest_point' below is the most recent observation "
    "captured so far, not a confirmed market close -- do not treat it as one."
)


class ClosingLineMovementAgent(ContextDataAgent):
    agent_name = "closing_line_movement_agent"
    task_type = "closing_line_movement_analysis"

    def build_evidence(self, context: AgentContext) -> dict:
        return {
            "line_movement": (
                [asdict(feature) for feature in context.line_movement] if context.line_movement is not None else None
            ),
            "closing_line_status": _CLOSING_LINE_STATUS,
        }
