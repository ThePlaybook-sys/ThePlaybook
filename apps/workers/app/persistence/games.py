"""Read-only `games` access (Milestone 4.9). Mirrors `ai-orchestrator`'s
own `app.persistence.games` eligibility policy -- `scheduled` is the
only pregame-recommendation-eligible status (carried forward unchanged
from Milestone 4.1/4.2's approved policy; this module does not
re-derive or second-guess it, it only reads by the same filter)."""
from __future__ import annotations

import httpx


class GamesReadError(Exception):
    """Raised when a `games` read fails on Supabase's side."""


async def read_eligible_game_ids(client: httpx.AsyncClient, headers: dict) -> list[str]:
    """Returns the `id` of every currently `status='scheduled'` game --
    never `live`/`final`/`postponed`/`canceled`, matching `ai-
    orchestrator`'s `PREGAME_WORKFLOW_ELIGIBLE_STATUSES` exactly.
    Returns `[]` when none exist -- never fabricated."""
    response = await client.get(
        "/rest/v1/games",
        params={"status": "eq.scheduled", "select": "id"},
        headers=headers,
    )
    if response.status_code != 200:
        raise GamesReadError(f"failed to read eligible games: {response.status_code} {response.text}")
    return [row["id"] for row in response.json()]
