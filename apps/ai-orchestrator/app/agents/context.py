"""The shared per-game input bundle every Context & Data agent reads from
(Milestone 4.4). Built once per game by `build_agent_context`, not
re-fetched per agent -- Volume 2 Section 1.1's "download once, reuse
everywhere" principle, applied to agent input the same way Master
Refresh already applies it to provider data.

Every field is independently `None`-able and preserved exactly as read --
this module performs zero transformation, matching Milestone 4.1's
null-not-neutral discipline on the read side and Milestone 4.2's
no-fabrication discipline on the agent-output side. An agent seeing
`context.injuries is None` must degrade explicitly, never treat it as "no
injuries."
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from app.features.travel import TravelFeatures, compute_travel_features
from app.persistence.daily_game_intelligence import read_daily_game_intelligence
from app.persistence.games import find_previous_final_game, get_game


@dataclass(frozen=True)
class AgentContext:
    game_id: str
    correlation_id: str
    injuries: dict | None
    weather: dict | None
    rest: dict | None
    stadium: dict | None
    travel: TravelFeatures


async def build_agent_context(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, correlation_id: str
) -> AgentContext:
    """Composes one `AgentContext` from Milestone 4.1's existing DGI/games
    readers plus Milestone 4.4's deterministic travel calculation. Makes
    no assumption about which categories are populated -- a game with no
    weather snapshot yet still produces a valid context, `weather=None`.
    """
    dgi = await read_daily_game_intelligence(client, headers, game_id=game_id)
    game = await get_game(client, headers, game_id=game_id)

    injuries = dgi.get("injuries") if dgi else None
    weather = dgi.get("weather") if dgi else None
    rest = dgi.get("rest") if dgi else None
    stadium = dgi.get("stadium") if dgi else None

    previous_game = None
    if game is not None and game.get("home_team"):
        # Travel is computed for the home team's previous game -- Volume
        # 3's own `rest` semantics (v4.5) already establish "the team" a
        # per-game feature is computed for defaults to the home team when
        # no other convention is stated; matched here for consistency.
        previous_game = await find_previous_final_game(
            client, headers, team=game["home_team"], before=_scheduled_start(game)
        )

    travel = compute_travel_features(
        current_venue_lat=game.get("venue_lat") if game else None,
        current_venue_long=game.get("venue_long") if game else None,
        current_stadium=game.get("stadium") if game else None,
        previous_venue_lat=previous_game.get("venue_lat") if previous_game else None,
        previous_venue_long=previous_game.get("venue_long") if previous_game else None,
        previous_stadium=previous_game.get("stadium") if previous_game else None,
        kickoff_at=_scheduled_start(game) if game else datetime.now().astimezone(),
    )

    return AgentContext(
        game_id=game_id,
        correlation_id=correlation_id,
        injuries=injuries,
        weather=weather,
        rest=rest,
        stadium=stadium,
        travel=travel,
    )


def _scheduled_start(game: dict) -> datetime:
    value = game["scheduled_start"]
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
