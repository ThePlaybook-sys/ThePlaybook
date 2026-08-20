"""Read-only `games` access + Phase 4 proactive-generation eligibility
(Milestone 4.1, Decision 7).

**CONFIRMED FROM VOLUME 3 Section 4:** `games.status` is exactly one of
five values -- `scheduled`, `live`, `final`, `postponed`, `canceled`.

**ASSUMED, not directly stated by any Phase 4 blueprint text -- flagged
here for Mac's confirmation rather than treated as settled, per this
project's existing CONFIRMED/ASSUMED discipline:** which of those five
statuses the *proactive* Recommendation Worker (Volume 2 Section 4.4,
Volume 4 Section 3.1) should trigger real committee fan-out for at all.
Volume 4's own execution flow never conditions eligibility on
`games.status`. This module's default answer, until told otherwise:

- `scheduled` -- **eligible.** The only status a pregame recommendation
  is meaningfully about.
- `postponed` / `canceled` -- **ineligible**, per Decision 7 (2026-08-20,
  this milestone's own explicit instruction): nothing to recommend on a
  game that is not being played, or not known to be played, as
  scheduled. This is a Phase-4-side eligibility filter only -- it does
  not change, and this module does not touch, any Phase 3 worker's own
  polling behavior for a postponed/canceled game (that behavior is
  recorded separately as a Phase 3 product consideration, per the same
  Decision).
- `live` -- **ineligible.** Volume 1's own Technical Debt & Feature
  Backlog lists "Live betting" under "Future" (not yet scoped) --  no
  documented proactive-recommendation behavior exists for an in-progress
  game at MLP stage.
- `final` -- **ineligible.** The game has already happened; there is no
  future bet a proactive recommendation could usefully inform once a
  game is final.

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

#: ASSUMED (see module docstring) -- ports Decision 7 (postponed/canceled
#: ineligible) plus this module's own default answer for live/final into
#: one settable policy, so a future confirmed answer is a one-line change
#: here, not a rewrite of the callers below.
PHASE4_ELIGIBLE_STATUSES = frozenset({"scheduled"})


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


def is_phase4_eligible(game: dict) -> bool:
    """Pure eligibility check against an already-fetched `games` row.
    Raises `GameStatusUnrecognizedError` for a missing/unrecognized
    status rather than guessing -- callers that need a safe boolean for a
    possibly-missing game should use `check_phase4_eligibility` below."""
    status = game.get("status")
    if status not in ALL_GAME_STATUSES:
        raise GameStatusUnrecognizedError(f"unrecognized or missing games.status: {status!r}")
    return status in PHASE4_ELIGIBLE_STATUSES


async def check_phase4_eligibility(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> tuple[bool, str]:
    """The safe, all-cases-covered entry point the Recommendation Worker
    (a later milestone) will actually call. Returns `(eligible, reason)`.

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
        eligible = is_phase4_eligible(game)
    except GameStatusUnrecognizedError as exc:
        return False, f"invalid_status: {exc}"
    return (eligible, "eligible") if eligible else (eligible, f"ineligible_status:{game['status']}")
