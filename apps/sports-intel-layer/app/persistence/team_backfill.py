"""Explicit, one-time team-identity backfill mapping (Phase 3E-3, expanded
Phase 3E-4A 2026-08-14, taken to sportsdataio full coverage 2026-08-18).

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
team_stats_week_bulk,player_stats_week_bulk,injuries,teams_active}_normal.json`'s
`Team`/`HomeTeam`/`AwayTeam`/`Key` fields. `the_odds_api` values come from
every non-error/non-malformed fixture in
`tests/fixtures/the_odds_api/`'s `home_team`/`away_team` fields.

**Retroactive correction, resolved 2026-08-18:** this table's original
3E-3 version included `sportsdataio` entries for Dallas Cowboys (`"DAL"`)
and Philadelphia Eagles (`"PHI"`) that were *not* actually confirmed
against any fixture at the time -- they were inferred from standard,
well-known NFL abbreviation conventions, and 3E-4A removed them from this
table pending verification (their already-applied `team_provider_ids`
database rows were deliberately left in place, flagged to Mac). A
single-purpose, single-endpoint live capture of `/v3/nfl/scores/json/Teams`
(`tests/fixtures/sportsdataio/teams_active_normal.json`, see
`PROVENANCE.md`) has since directly confirmed both: `Key` is `"DAL"` for
Dallas Cowboys and `"PHI"` for Philadelphia Eagles, exactly matching the
already-applied rows. Both entries are restored below with this citation.

**Coverage as of 2026-08-18:** 32 `teams` rows exist (standard current NFL
naming -- not provider data, see the 3E-4A migration's own comment for why
that distinction matters). All 32 now have a confirmed `sportsdataio`
mapping (deterministically reconciled against the full live `Teams`
capture -- exact `FullName`-to-`teams.name` match, zero fuzzy matching,
zero conflicts). 6 have a confirmed `the_odds_api` mapping (BAL, BUF, DAL,
KC, PHI, SF) -- unchanged by this round, since it captured no Odds API
evidence. The remaining 26 teams have no `the_odds_api` mapping; this is a
real, reported gap, not silently treated as resolved -- `resolve_team_ids`
correctly returns "absent" for any of these, and no code should assume
every `teams` row has a `the_odds_api` mapping.
"""
from __future__ import annotations

import httpx

from app.persistence.team_identity import link_provider_team_id

TEAM_BACKFILL: dict[str, dict[str, str]] = {
    "Kansas City Chiefs": {"sportsdataio": "KC", "the_odds_api": "Kansas City Chiefs"},
    "Buffalo Bills": {"sportsdataio": "BUF", "the_odds_api": "Buffalo Bills"},
    "San Francisco 49ers": {"sportsdataio": "SF", "the_odds_api": "San Francisco 49ers"},
    "Baltimore Ravens": {"sportsdataio": "BAL", "the_odds_api": "Baltimore Ravens"},
    # Dallas Cowboys / Philadelphia Eagles: sportsdataio confirmed
    # 2026-08-18 via the live Teams capture (see module docstring's
    # "Retroactive correction" note) -- both providers now populated.
    "Dallas Cowboys": {"sportsdataio": "DAL", "the_odds_api": "Dallas Cowboys"},
    "Philadelphia Eagles": {"sportsdataio": "PHI", "the_odds_api": "Philadelphia Eagles"},
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
    # sportsdataio-only, confirmed 2026-08-18 via the live Teams capture
    # (tests/fixtures/sportsdataio/teams_active_normal.json) -- no
    # the_odds_api fixture evidence for any of these 17.
    "Cincinnati Bengals": {"sportsdataio": "CIN"},
    "Cleveland Browns": {"sportsdataio": "CLE"},
    "Denver Broncos": {"sportsdataio": "DEN"},
    "Detroit Lions": {"sportsdataio": "DET"},
    "Green Bay Packers": {"sportsdataio": "GB"},
    "Houston Texans": {"sportsdataio": "HOU"},
    "Indianapolis Colts": {"sportsdataio": "IND"},
    "Jacksonville Jaguars": {"sportsdataio": "JAX"},
    "Las Vegas Raiders": {"sportsdataio": "LV"},
    "Los Angeles Chargers": {"sportsdataio": "LAC"},
    "Miami Dolphins": {"sportsdataio": "MIA"},
    "Minnesota Vikings": {"sportsdataio": "MIN"},
    "New York Giants": {"sportsdataio": "NYG"},
    "New York Jets": {"sportsdataio": "NYJ"},
    "Pittsburgh Steelers": {"sportsdataio": "PIT"},
    "Tennessee Titans": {"sportsdataio": "TEN"},
    "Washington Commanders": {"sportsdataio": "WAS"},
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
