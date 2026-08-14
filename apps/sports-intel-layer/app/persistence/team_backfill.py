"""Explicit, one-time team-identity backfill mapping (Phase 3E-3, 2026-08-13).

**Not a runtime fuzzy-matching mechanism.** `TEAM_BACKFILL` is a static,
manually-curated table -- the single place a provider's team
representation is decided, so no worker ever normalizes team names or
abbreviations ad hoc. Mac's explicit instruction: "If a one-time
deterministic backfill mapping is needed, it must be explicit,
documented, tested, not scattered across worker code."

Provenance: NFL team abbreviations and full names are public, standard,
unambiguous naming facts -- not vendor-specific data requiring a live
provider call to confirm. `sportsdataio` values are confirmed directly
from this project's own already-captured fixture
(`tests/fixtures/sportsdataio/rosters_normal.json`'s `"Team": "KC"`).
`the_odds_api` values are confirmed from
`tests/fixtures/the_odds_api/bulk_odds_multi_game.json`'s
`"home_team": "Kansas City Chiefs"`.

Currently covers only the six teams seeded in dev (`supabase/seed.sql`).
Extending to all 32 NFL teams is a mechanical, non-controversial follow-up
(same abbreviation/full-name pattern) -- not needed until Phase 3
onboards the full league, so not built ahead of that need.
"""
from __future__ import annotations

import httpx

from app.persistence.team_identity import link_provider_team_id

TEAM_BACKFILL: dict[str, dict[str, str]] = {
    "Kansas City Chiefs": {"sportsdataio": "KC", "the_odds_api": "Kansas City Chiefs"},
    "Buffalo Bills": {"sportsdataio": "BUF", "the_odds_api": "Buffalo Bills"},
    "San Francisco 49ers": {"sportsdataio": "SF", "the_odds_api": "San Francisco 49ers"},
    "Philadelphia Eagles": {"sportsdataio": "PHI", "the_odds_api": "Philadelphia Eagles"},
    "Dallas Cowboys": {"sportsdataio": "DAL", "the_odds_api": "Dallas Cowboys"},
    "Baltimore Ravens": {"sportsdataio": "BAL", "the_odds_api": "Baltimore Ravens"},
}


async def backfill_known_teams(client: httpx.AsyncClient, headers: dict) -> int:
    """Links every team in `teams` whose `name` matches `TEAM_BACKFILL` to
    its known provider representations. Idempotent (via
    `link_provider_team_id`'s upsert-on-conflict) -- safe to call more
    than once. Returns the number of (team, provider) links written.
    """
    response = await client.get("/rest/v1/teams", params={"select": "id,name"}, headers=headers)
    response.raise_for_status()
    teams = response.json()

    linked = 0
    for team in teams:
        mapping = TEAM_BACKFILL.get(team["name"])
        if mapping is None:
            continue
        for provider_name, provider_team_id in mapping.items():
            await link_provider_team_id(
                client,
                headers,
                team_id=team["id"],
                provider_name=provider_name,
                provider_team_id=provider_team_id,
            )
            linked += 1
    return linked
