"""Read-only `games` access + pregame-workflow eligibility (Milestone 4.1,
Decision 7; rescoped Milestone 4.2 per Mac's clarification).

**CONFIRMED FROM VOLUME 3 Section 4:** `games.status` is exactly one of
five values -- `scheduled`, `live`, `final`, `postponed`, `canceled`.

**This module's eligibility policy is scoped to the current Phase 4
*pregame recommendation* workflow -- not a permanent, platform-wide claim
that The Playbook can never process a live game.** Mac's explicit
clarification (2026-08-20, approving Milestone 4.2): treat
`PREGAME_WORKFLOW_ELIGIBLE_STATUSES` as one named workflow's eligibility
set, not a global constant every future consumer must share. A later,
separately-scoped live-game intelligence/recommendation workflow (not
built here, not scheduled by any current milestone) would define its own
eligible-status set against the same `ALL_GAME_STATUSES` vocabulary and
the same `get_game`/safe-rejection pattern below -- nothing in this
module needs to be undone or generalized retroactively to support that;
the naming below is deliberately workflow-specific from the start so that
day never requires an "un-scoping" migration.

**ASSUMED, not directly stated by any Phase 4 blueprint text -- flagged
here for Mac's confirmation rather than treated as settled, per this
project's existing CONFIRMED/ASSUMED discipline:** which of the five
statuses the *pregame* Recommendation Worker (Volume 2 Section 4.4,
Volume 4 Section 3.1) should trigger real committee fan-out for. Volume 4
never conditions eligibility on `games.status` at all. This workflow's
approved policy (Mac, 2026-08-20):

- `scheduled` -- **eligible.** The only status a pregame recommendation
  is meaningfully about.
- `postponed` / `canceled` -- **ineligible.** Nothing to recommend on a
  game that is not being played, or not known to be played, as
  scheduled. This is a Phase-4-side eligibility filter only -- it does
  not change, and this module does not touch, any Phase 3 worker's own
  polling behavior for a postponed/canceled game (recorded separately as
  a Phase 3 product consideration).
- `live` -- **ineligible for this pregame workflow specifically**, not
  ineligible forever. Volume 1's own Technical Debt & Feature Backlog
  lists "Live betting" under "Future" (not yet scoped) -- no documented
  in-play recommendation behavior exists yet for any workflow to trigger.
- `final` -- **ineligible.** The game has already happened; there is no
  future bet a pregame recommendation could usefully inform once a game
  is final.

This module reads `games.status` directly from `games` -- it never reads,
infers, or fabricates a status signal from `daily_game_intelligence`,
which carries no status field of its own (see this package's
`daily_game_intelligence` module docstring).
"""
from __future__ import annotations

import httpx

#: CONFIRMED FROM VOLUME 3 Section 4 -- the complete `games.status` check
#: constraint vocabulary. Any other value is a data error, never silently
#: treated as either eligible or ineligible.
ALL_GAME_STATUSES = frozenset({"scheduled", "live", "final", "postponed", "canceled"})

#: ASSUMED (see module docstring) -- this workflow's own approved
#: eligibility set, not a platform-wide rule. Named for the one workflow
#: it governs so a future, separately-scoped live-game workflow can
#: define its own set alongside this one without implying either
#: supersedes the other.
PREGAME_WORKFLOW_ELIGIBLE_STATUSES = frozenset({"scheduled"})


class GamesReadError(Exception):
    """Raised when a `games` read fails on Supabase's side."""


class GameStatusUnrecognizedError(Exception):
    """Raised when a `games` row's `status` is missing or outside
    `ALL_GAME_STATUSES` -- fails loud rather than silently defaulting to
    either eligible or ineligible, since either default could be wrong in
    a way nobody would notice."""


async def get_game(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> dict | None:
    """Reads one `games` row by internal id. Returns `None` when no row
    exists -- never a synthesized shape, matching this package's
    `daily_game_intelligence` reader's exact convention."""
    response = await client.get(
        "/rest/v1/games",
        params={
            "id": f"eq.{game_id}",
            "select": "id,status,scheduled_start,home_team,away_team,season_type,week",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GamesReadError(f"failed to read game {game_id}: {response.status_code} {response.text}")
    rows = response.json()
    return rows[0] if rows else None


def is_pregame_workflow_eligible(game: dict) -> bool:
    """Pure eligibility check against an already-fetched `games` row, for
    the pregame recommendation workflow specifically (see module
    docstring). Raises `GameStatusUnrecognizedError` for a
    missing/unrecognized status rather than guessing -- callers that need
    a safe boolean for a possibly-missing game should use
    `check_pregame_workflow_eligibility` below."""
    status = game.get("status")
    if status not in ALL_GAME_STATUSES:
        raise GameStatusUnrecognizedError(f"unrecognized or missing games.status: {status!r}")
    return status in PREGAME_WORKFLOW_ELIGIBLE_STATUSES


async def check_pregame_workflow_eligibility(
    client: httpx.AsyncClient, headers: dict, *, game_id: str
) -> tuple[bool, str]:
    """The safe, all-cases-covered entry point the pregame Recommendation
    Worker (a later milestone) will actually call. Returns `(eligible,
    reason)`.

    Never raises: a missing game is rejected safely (`False,
    "game_not_found"`), matching this milestone's explicit testing
    requirement -- a crash here would be worse than a correctly-refused
    fan-out. An unrecognized status is likewise rejected safely rather
    than propagating `GameStatusUnrecognizedError` to a caller that only
    wants a yes/no answer to trigger fan-out with.
    """
    game = await get_game(client, headers, game_id=game_id)
    if game is None:
        return False, "game_not_found"
    try:
        eligible = is_pregame_workflow_eligible(game)
    except GameStatusUnrecognizedError as exc:
        return False, f"invalid_status: {exc}"
    return (eligible, "eligible") if eligible else (eligible, f"ineligible_status:{game['status']}")
