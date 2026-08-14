"""Tests for app.persistence.team_identity and team_backfill (Phase 3E-3).

Mirrors test_game_identity.py's structure and the same properties Mac's
3E-1 checkpoint required for games, applied to teams: two providers'
representations resolving to the same internal id, and the database-level
proof (via live constraint checks already run against dev, see PROGRESS.md)
that a provider id can't silently map to two different teams.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.persistence.team_backfill import TEAM_BACKFILL, backfill_known_teams
from app.persistence.team_identity import TeamIdentityError, link_provider_team_id, resolve_team_ids

SUPABASE_URL = "https://test-project.supabase.co"
TEAM_ID = "b3000000-0000-0000-0000-000000000001"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_two_different_providers_resolve_to_the_same_team_id():
    rows_by_provider = {
        "eq.the_odds_api": [{"team_id": TEAM_ID, "provider_team_id": "Kansas City Chiefs"}],
        "eq.sportsdataio": [{"team_id": TEAM_ID, "provider_team_id": "KC"}],
    }

    def _respond(request: httpx.Request) -> httpx.Response:
        provider_name = request.url.params["provider_name"]
        return httpx.Response(200, json=rows_by_provider[provider_name])

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(side_effect=_respond)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        odds_api_result = await resolve_team_ids(
            client, _headers(), provider_name="the_odds_api", provider_team_ids=["Kansas City Chiefs"]
        )
        sportsdataio_result = await resolve_team_ids(
            client, _headers(), provider_name="sportsdataio", provider_team_ids=["KC"]
        )

    assert odds_api_result == {"Kansas City Chiefs": TEAM_ID}
    assert sportsdataio_result == {"KC": TEAM_ID}
    assert odds_api_result["Kansas City Chiefs"] == sportsdataio_result["KC"]


@pytest.mark.asyncio
@respx.mock
async def test_unmapped_provider_team_id_is_absent_not_guessed():
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_team_ids(
            client, _headers(), provider_name="sportsdataio", provider_team_ids=["XYZ"]
        )
    assert result == {}


@pytest.mark.asyncio
async def test_resolve_team_ids_empty_input_makes_no_call():
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_team_ids(
            client, _headers(), provider_name="sportsdataio", provider_team_ids=[]
        )
    assert result == {}


@pytest.mark.asyncio
@respx.mock
async def test_resolve_team_ids_raises_on_non_200():
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(TeamIdentityError):
            await resolve_team_ids(client, _headers(), provider_name="sportsdataio", provider_team_ids=["KC"])


@pytest.mark.asyncio
@respx.mock
async def test_link_provider_team_id_upserts_on_conflict():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(201))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await link_provider_team_id(
            client, _headers(), team_id=TEAM_ID, provider_name="sportsdataio", provider_team_id="KC"
        )
    assert route.called
    request = route.calls.last.request
    assert request.url.params["on_conflict"] == "team_id,provider_name"
    assert request.headers["Prefer"] == "resolution=merge-duplicates"
    body = json.loads(request.content)
    assert body == {"team_id": TEAM_ID, "provider_name": "sportsdataio", "provider_team_id": "KC"}


@pytest.mark.asyncio
@respx.mock
async def test_link_provider_team_id_raises_on_failure():
    respx.post(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(409))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(TeamIdentityError):
            await link_provider_team_id(
                client, _headers(), team_id=TEAM_ID, provider_name="sportsdataio", provider_team_id="KC"
            )


@pytest.mark.asyncio
@respx.mock
async def test_backfill_known_teams_links_every_matched_team():
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "t1", "name": "Kansas City Chiefs"},
                {"id": "t2", "name": "An Unknown Expansion Team"},
            ],
        )
    )
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(201))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        linked = await backfill_known_teams(client, _headers())

    assert linked == 2  # KC's two providers only -- the unknown team is skipped, not guessed
    assert link_route.call_count == 2


def test_team_backfill_table_entries_have_at_least_one_known_provider():
    # Phase 3E-4A: TEAM_BACKFILL now covers every fixture-confirmed team,
    # not just teams with both providers. Every entry must still map to a
    # real, recognized provider name, and every entry must map to at least
    # one provider (no empty mappings).
    assert len(TEAM_BACKFILL) == 15
    for team, providers in TEAM_BACKFILL.items():
        assert providers, f"{team} has no provider mapping"
        assert set(providers) <= {"sportsdataio", "the_odds_api"}


def test_team_backfill_table_provider_coverage_matches_fixture_audit():
    # Exactly 4 teams (BAL, BUF, KC, SF) are confirmed by both providers'
    # fixtures; 13 teams have a confirmed sportsdataio mapping; 6 teams have
    # a confirmed the_odds_api mapping (see module docstring for the audit).
    both = [team for team, providers in TEAM_BACKFILL.items() if set(providers) == {"sportsdataio", "the_odds_api"}]
    sportsdataio_only = [team for team, providers in TEAM_BACKFILL.items() if set(providers) == {"sportsdataio"}]
    odds_api_only = [team for team, providers in TEAM_BACKFILL.items() if set(providers) == {"the_odds_api"}]

    assert set(both) == {"Kansas City Chiefs", "Buffalo Bills", "San Francisco 49ers", "Baltimore Ravens"}
    assert set(odds_api_only) == {"Dallas Cowboys", "Philadelphia Eagles"}
    assert len(sportsdataio_only) == 9
    assert len(both) + len(sportsdataio_only) + len(odds_api_only) == len(TEAM_BACKFILL)
