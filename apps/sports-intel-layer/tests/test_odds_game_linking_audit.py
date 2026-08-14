"""Odds/Player Props pre-implementation compatibility audit (Phase 3E-3).

Proves, against the real already-captured The Odds API fixture and only
already-built primitives (`team_identity.resolve_team_ids`,
`games.list_games_in_window`), that deterministic game linking is now
possible with no fuzzy matching -- the exact question Mac's 3E-3
checkpoint asked to have answered before 3E-4 (the Odds/Player Props
Worker) is built.

**This is proof-of-mechanism only, not the Odds/Props Worker's own
linking implementation** -- per Mac's explicit instruction, the actual
production linking heuristic belongs to 3E-4, not this foundation phase.
The resolution steps below are written inline in the test, not exported
as a reusable app/ module, so nothing here is mistakenly importable as
"the real thing" by a future worker.

**Audit findings (see also the 3E-3 completion report):**
1. The Odds API identifies a game's teams via `event["home_team"]`/
   `event["away_team"]` as full team names -- CONFIRMED directly from
   `tests/fixtures/the_odds_api/bulk_odds_multi_game.json`. Note: neither
   `TheOddsApiOddsAdapter` nor `OddsLine`/`PlayerProp` currently expose
   these fields at all (only the event id is normalized) -- a real gap
   3E-4 will need to close, not solved here.
2. Those names resolve to internal `teams.id` via
   `team_identity.resolve_team_ids(provider_name="the_odds_api", ...)`.
3. `games.home_team`/`.away_team` hold SportsDataIO's abbreviation text
   (Master Refresh's Schedule ingestion writes `ScheduleEntry.home_team`/
   `.away_team` verbatim, which come from SportsDataIO's `HomeTeam`/
   `AwayTeam` fields) -- resolving a game by team therefore requires a
   *second*, reverse lookup: `team_identity.resolve_team_ids(
   provider_name="sportsdataio", ...)` against `games.home_team`/
   `.away_team`'s own text, then comparing the two resolved `teams.id`
   values for equality -- never comparing raw team-name strings directly.
   `games.home_team`/`.away_team` are plain text, not FK columns to
   `teams.id` -- confirmed by direct inspection of the Phase 1 migration
   -- so this two-hop comparison is required today; a future
   `home_team_id`/`away_team_id` FK migration (not proposed here) could
   remove the need for it later.
4. Given both hops resolve, matching on {home team_id, away team_id,
   scheduled_start tolerance} is fully deterministic -- no fuzzy string
   matching required in the fixture case exercised below.
5. Remaining ambiguous/fuzzy case: a provider event whose team name has
   no team_provider_ids mapping at all (an unrecognized/misspelled name,
   or a team never linked). That case must be surfaced as unresolved, not
   guessed -- consistent with `resolve_team_ids` already returning an
   absence rather than a guess for an unmapped id.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx

from app.persistence.games import list_games_in_window
from app.persistence.team_identity import resolve_team_ids

SUPABASE_URL = "https://test-project.supabase.co"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "the_odds_api" / "bulk_odds_multi_game.json"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_odds_api_event_deterministically_links_to_existing_sportsdataio_game():
    with open(FIXTURE_PATH) as f:
        events = json.load(f)
    event = events[0]  # real fixture: home_team "Kansas City Chiefs", away_team "Baltimore Ravens"
    assert event["home_team"] == "Kansas City Chiefs"
    assert event["away_team"] == "Baltimore Ravens"

    kc_team_id = "team-kc"
    bal_team_id = "team-bal"
    game_id = "game-kc-bal"

    # Step 2: resolve The Odds API's team names to internal teams.id.
    def _team_provider_respond(request: httpx.Request) -> httpx.Response:
        provider_name = request.url.params["provider_name"]
        ids_param = request.url.params["provider_team_id"]
        rows_by_provider = {
            "eq.the_odds_api": [
                {"team_id": kc_team_id, "provider_team_id": "Kansas City Chiefs"},
                {"team_id": bal_team_id, "provider_team_id": "Baltimore Ravens"},
            ],
            "eq.sportsdataio": [
                {"team_id": kc_team_id, "provider_team_id": "KC"},
                {"team_id": bal_team_id, "provider_team_id": "BAL"},
            ],
        }
        rows = [r for r in rows_by_provider[provider_name] if r["provider_team_id"] in ids_param]
        return httpx.Response(200, json=rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(side_effect=_team_provider_respond)

    # Step 3: games.home_team/away_team hold SportsDataIO abbreviations.
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": game_id,
                    "external_provider_id": None,
                    "home_team": "KC",
                    "away_team": "BAL",
                    "scheduled_start": event["commence_time"],
                    "stadium": "Arrowhead Stadium",
                    "status": "scheduled",
                    "season_type": "regular",
                    "week": 2,
                }
            ],
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        odds_team_ids = await resolve_team_ids(
            client, _headers(), provider_name="the_odds_api",
            provider_team_ids=[event["home_team"], event["away_team"]],
        )
        event_home_team_id = odds_team_ids[event["home_team"]]
        event_away_team_id = odds_team_ids[event["away_team"]]

        commence = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
        candidate_games = await list_games_in_window(
            client, _headers(),
            start=(commence - timedelta(days=1)).date(),
            end=(commence + timedelta(days=1)).date(),
        )

        sdio_abbrevs = sorted({g["home_team"] for g in candidate_games} | {g["away_team"] for g in candidate_games})
        sdio_team_ids = await resolve_team_ids(
            client, _headers(), provider_name="sportsdataio", provider_team_ids=sdio_abbrevs
        )

        matched = [
            g for g in candidate_games
            if sdio_team_ids.get(g["home_team"]) == event_home_team_id
            and sdio_team_ids.get(g["away_team"]) == event_away_team_id
        ]

    # Step 4: fully deterministic -- exactly one match, no fuzzy matching used.
    assert len(matched) == 1
    assert matched[0]["id"] == game_id


@pytest.mark.asyncio
@respx.mock
async def test_unrecognized_team_name_is_unresolved_not_guessed():
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_team_ids(
            client, _headers(), provider_name="the_odds_api", provider_team_ids=["Some Expansion Team"]
        )
    # Finding 5: an unmapped provider team name resolves to nothing -- the
    # caller must treat it as unresolved, never guess a match.
    assert result == {}
