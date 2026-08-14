"""Explicit, one-time team-identity backfill mapping (Phase 3E-3, expanded
Phase 3E-4A, 2026-08-14).

**Not a runtime fuzzy-matching mechanism.** `TEAM_BACKFILL` is a static,
manually-curated table -- the single place a provider's team
representation is decided, so no worker ever normalizes team names or
abbreviations ad hoc. Mac's explicit instruction: "If a one-time
deterministic backfill mapping is needed, it must be explicit,
documented, tested, not scattered across worker code."

**Provenance discipline (tightened explicitly in 3E-4A):** every value in
this table is confirmed by a direct grep of this repository's own fixture
files -- never filled in from general/public NFL knowledge, even where
that knowledge is well-established. `sportsdataio` values come from
`tests/fixtures/sportsdataio/{schedules,rosters,depth_charts,
team_stats_week_bulk,player_stats_week_bulk,injuries}_normal.json`'s
`Team`/`HomeTeam`/`AwayTeam` fields. `the_odds_api` values come from
every non-error/non-malformed fixture in
`tests/fixtures/the_odds_api/`'s `home_team`/`away_team` fields.

**Retroactive correction, flagged rather than silently left in place:**
this table's original 3E-3 version included `sportsdataio` entries for
Dallas Cowboys (`"DAL"`) and Philadelphia Eagles (`"PHI"`) that were
*not* actually confirmed against any fixture at the time -- they were
inferred from standard, well-known NFL abbreviation conventions. Under
the provenance bar Mac made explicit in 3E-4A, those two entries do not
qualify and have been removed from this table (their `team_provider_ids`
database rows, applied in the 3E-3 migration, are left as-is rather than
retroactively dropped -- flagged to Mac as a completed-phase discrepancy
rather than unilaterally rewritten). Both teams' `the_odds_api` full-name
entries remain, since those genuinely are fixture-confirmed.

**Coverage as of 3E-4A:** 32 `teams` rows exist (standard current NFL
naming -- not provider data, see the 3E-4A migration's own comment for
why that distinction matters). Of those, 15 have a confirmed
`sportsdataio` mapping and 6 have a confirmed `the_odds_api` mapping (4
teams -- BAL, BUF, KC, SF -- have both). The remaining teams have no
provider mapping at all: 17 have zero SportsDataIO fixture evidence
(CIN, CLE, DEN, DET, GB, HOU, IND, JAX, LAC, LV, MIA, MIN, NYG, NYJ, PIT,
TEN, WAS) and 26 have zero The Odds API fixture evidence. This is a real,
reported gap (see the 3E-4 completion report), not silently treated as
resolved -- `resolve_team_ids` correctly returns "absent" for any of
these, and no code should assume every `teams` row has a provider
mapping.
"""
from __future__ import annotations

import httpx

from app.persistence.team_identity import link_provider_team_id

TEAM_BACKFILL: dict[str, dict[str, str]] = {
    "Kansas City Chiefs": {"sportsdataio": "KC", "the_odds_api": "Kansas City Chiefs"},
    "Buffalo Bills": {"sportsdataio": "BUF", "the_odds_api": "Buffalo Bills"},
    "San Francisco 49ers": {"sportsdataio": "SF", "the_odds_api": "San Francisco 49ers"},
    "Baltimore Ravens": {"sportsdataio": "BAL", "the_odds_api": "Baltimore Ravens"},
    # Dallas Cowboys / Philadelphia Eagles: the_odds_api only -- their
    # sportsdataio abbreviations are NOT fixture-confirmed (see module
    # docstring's "Retroactive correction" note). Do not add sportsdataio
    # here without a real fixture to point to.
    "Dallas Cowboys": {"the_odds_api": "Dallas Cowboys"},
    "Philadelphia Eagles": {"the_odds_api": "Philadelphia Eagles"},
    # sportsdataio-only: confirmed abbreviation, no the_odds_api fixture evidence.
    "Arizona Cardinals": {"sportsdataio": "ARI"},
    "Atlanta Falcons": {"sportsdataio": "ATL"},
    "Carolina Panthers": {"sportsdataio": "CAR"},
    "Chicago Bears": {"sportsdataio": "CHI"},
    "Los Angeles Rams": {"sportsdataio": "LAR"},
    "New England Patriots": {"sportsdataio": "NE"},
    "New Orleans Saints": {"sportsdataio": "NO"},
    "Seattle Seahawks": {"sportsdataio": "SEA"},
    "Tampa Bay Buccaneers": {"sportsdataio": "TB"},
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
