"""Resolves which SportsDataIO season string ("{year}REG") Master Refresh
should request, from the existing `seasons`/`leagues` tables -- Phase 3E-2.

Mac's explicit instruction: "database/internal season context -> provider
adapter converts to SportsDataIO request representation. Do not scatter
hardcoded '2026REG' values into production worker code." This module is
that internal-context layer; only `SportsDataIOScheduleAdapter` itself
knows the provider's own string format.

No schema change: `seasons.start_date`/`end_date` already exist (Volume 3
§4.0, Phase 1). The resolver is a pure function of (today, seasons rows) --
tested without any DB dependency -- plus a thin DB-reading wrapper that
supplies those rows from Supabase.

Only regular-season is normalizable right now (3E-1's `_SEASON_TYPE_MAP`
maps SportsDataIO SeasonType 1 only), so this resolver deliberately only
ever produces a "{year}REG" string -- it does not attempt to distinguish
preseason/postseason windows within a season's start/end range, since
nothing downstream could use that distinction yet.
"""
from __future__ import annotations

from datetime import date

import httpx


class SeasonResolutionError(Exception):
    """Raised when the current season can't be determined from `seasons`
    data alone -- deliberately distinct from ProviderError/PersistenceError:
    this is neither a vendor failure nor a write failure, it's "the data
    needed to even start doesn't exist yet," which Master Refresh treats
    as a blocking failure (same category as a Schedule fetch failure)."""


def resolve_current_season_year(today: date, seasons: list[dict]) -> int:
    """Pure function: given today's date and a list of {year, start_date,
    end_date} rows (already scoped to one league), returns the year whose
    [start_date, end_date] range contains today.

    Zero matches raises -- e.g. during the real off-season gap before a
    season's start_date, which is exactly the state this project's own dev
    data is in as of 2026-08-13 (the only seasons row starts 2026-09-04).
    This is a legitimate, expected state, not a bug: it means no current
    season exists to request a Schedule for, and Master Refresh should
    fail the run rather than guess.

    More than one match raises too -- seasons rows for one league aren't
    expected to have overlapping [start_date, end_date] ranges; if they
    ever do, guessing which one is "current" would be exactly the kind of
    invented behavior this codebase's established discipline avoids.
    """
    matches = [
        row["year"]
        for row in seasons
        if row["start_date"] is not None
        and row["end_date"] is not None
        and date.fromisoformat(row["start_date"]) <= today <= date.fromisoformat(row["end_date"])
    ]
    if not matches:
        raise SeasonResolutionError(
            f"no seasons row covers {today.isoformat()} -- either the "
            "current season hasn't started yet or its seasons row is "
            "missing/misconfigured"
        )
    if len(matches) > 1:
        raise SeasonResolutionError(
            f"{len(matches)} seasons rows cover {today.isoformat()} "
            f"({matches}) -- ambiguous, not guessed"
        )
    return matches[0]


async def fetch_current_season_string(
    client: httpx.AsyncClient, headers: dict, *, league_code: str, today: date
) -> str:
    """DB-backed wrapper: resolves `league_code` (e.g. "nfl") to a
    `leagues.id`, reads that league's `seasons` rows, and returns the
    SportsDataIO season string ("{year}REG") for `today` via
    `resolve_current_season_year`.
    """
    league_response = await client.get(
        "/rest/v1/leagues",
        params={"code": f"eq.{league_code}", "select": "id"},
        headers=headers,
    )
    if league_response.status_code != 200:
        raise SeasonResolutionError(
            f"failed to resolve league {league_code!r}: "
            f"{league_response.status_code} {league_response.text}"
        )
    league_rows = league_response.json()
    if not league_rows:
        raise SeasonResolutionError(f"no league row for code={league_code!r}")
    league_id = league_rows[0]["id"]

    seasons_response = await client.get(
        "/rest/v1/seasons",
        params={"league_id": f"eq.{league_id}", "select": "year,start_date,end_date"},
        headers=headers,
    )
    if seasons_response.status_code != 200:
        raise SeasonResolutionError(
            f"failed to read seasons for league {league_code!r}: "
            f"{seasons_response.status_code} {seasons_response.text}"
        )
    year = resolve_current_season_year(today, seasons_response.json())
    return f"{year}REG"
