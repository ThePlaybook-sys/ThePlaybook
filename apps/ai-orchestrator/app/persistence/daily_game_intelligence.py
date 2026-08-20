"""Read-only `daily_game_intelligence` access for the AI Orchestrator
(Milestone 4.1).

Mirrors `apps/sports-intel-layer/app/persistence/daily_game_intelligence.
read_daily_game_intelligence` exactly -- full-row read (`select=*`),
`None` when no row exists yet for the game, never a synthesized empty
shape. Per Volume 4 Section 3.1 step 1, this is the *first* place a Phase
4 agent looks for game intelligence, falling back to individual
supporting tables only for a field not yet reflected here -- Milestone
4.1 builds only this first read, since `daily_game_intelligence` already
carries every category Phase 3 populates (`teams`, `players`, `odds`,
`props`, `weather`, `injuries`, `news`, `rest`, `stadium`) plus the two
categories it deliberately leaves null (`travel`, `public_betting`,
`sharp_money`) -- no supporting-table fallback read was genuinely
necessary to satisfy this milestone's scope.

**Null-not-neutral, preserved exactly as read -- this module's one hard
rule.** Every jsonb category Phase 3 wrote as `null` (`travel`,
`public_betting`, `sharp_money`, or any category with no snapshot yet)
comes back here as Python `None`, verbatim. Zero transformation, zero
defaulting, zero "null becomes 0 / neutral / healthy / no-injury /
no-sharp-money / no-public-betting / no-travel-impact" logic exists
anywhere in this module. A degraded/missing-input decision belongs to
whichever later-milestone agent consumes the value, never to this read
layer.

**A populated category's metadata object may not carry every key Volume 3
Section 4.1 documents.** That section's own shape example lists
`{value, source, confidence, last_updated, status}`, but
`sports-intel-layer`'s actual assembly code
(`app.persistence.daily_game_intelligence.build_payload` there, confirmed
by direct inspection) never writes `confidence` -- its own docstring:
"deliberately omitted... Phase 3 has no basis to compute [it]". This
module does not require, assume, synthesize, or default a `confidence`
key -- it returns the row exactly as Supabase stores it, present keys and
absent keys alike. A caller that needs `confidence` must handle its
absence, not assume this module guarantees it.

**`daily_game_intelligence` itself carries no `games.status` field.**
Confirmed by direct inspection of both the schema (Volume 3 Section 4.1)
and the real assembly code (`app.master_refresh.game_refresh`, which
never writes a status key into any DGI payload). A caller needing to know
whether a game is postponed/canceled/live/final must read `games.status`
directly -- see `app.persistence.games` in this same package -- never
infer it from anything in this row.
"""
from __future__ import annotations

import httpx


class DailyGameIntelligenceReadError(Exception):
    """Raised when a `daily_game_intelligence` read fails on Supabase's side."""


async def read_daily_game_intelligence(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/daily_game_intelligence",
        params={"game_id": f"eq.{game_id}", "select": "*"},
        headers=headers,
    )
    if response.status_code != 200:
        raise DailyGameIntelligenceReadError(
            f"failed to read daily_game_intelligence for game {game_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None
