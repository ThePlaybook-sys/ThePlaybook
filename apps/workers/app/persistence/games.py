"""Read-only `games` access (Milestone 4.9). Mirrors `ai-orchestrator`'s
own `app.persistence.games` eligibility policy -- `scheduled` is the
only pregame-recommendation-eligible status (carried forward unchanged
from Milestone 4.1/4.2's approved policy; this module does not
re-derive or second-guess it, it only reads by the same filter)."""
from __future__ import annotations

from datetime import datetime, timedelta

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


#: Milestone 5.4 -- how far back this worker looks for grading
#: candidates. DERIVED, not a Blueprint number (same class of decision as
#: `sports-intel-layer`'s own `_RECONCILIATION_LOOKBACK_DAYS`): wide
#: enough that a game finalized just past `ai-orchestrator`'s
#: RECONCILIATION_WINDOW_HOURS (72h) is never missed, generous enough to
#: also catch a late SportsDataIO correction arriving after that window
#: without scanning the entire table's history forever. Flagged in the
#: Milestone 5.4 completion report as an accepted MVP scope choice, not
#: an exhaustive/unbounded guarantee.
GRADING_CANDIDATE_LOOKBACK_DAYS = 14


async def read_grading_candidate_game_ids(client: httpx.AsyncClient, headers: dict, *, now: datetime) -> list[str]:
    """Returns every game_id that is a Postgame Grading candidate this
    cycle: `postponed`/`canceled` (gradeable immediately, no waiting --
    see `app.orchestration.postgame_grading`'s own reasoning for why),
    or `final` and finalized within the lookback window. `ai-
    orchestrator`'s own endpoint is the one that actually checks
    reconciliation-eligibility per game (Decision BH) -- this read is
    deliberately generous/coarse, matching the Recommendation Worker's
    own "discover broadly, let the domain service decide" split (Decision
    BY: this service never duplicates AI/business logic, including
    grading-readiness logic)."""
    window_start = (now - timedelta(days=GRADING_CANDIDATE_LOOKBACK_DAYS)).isoformat()
    response = await client.get(
        "/rest/v1/games",
        params={
            "select": "id",
            "or": (
                f"(status.eq.postponed,status.eq.canceled,"
                f"and(status.eq.final,finalized_at.gte.{window_start}))"
            ),
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GamesReadError(f"failed to read grading candidate games: {response.status_code} {response.text}")
    return [row["id"] for row in response.json()]
