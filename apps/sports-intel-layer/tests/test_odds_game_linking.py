"""Tests for app.persistence.odds_game_linking (Phase 3E-4C).

Promotes the fixture-proven mechanism from tests/test_odds_game_linking_audit.py
(Phase 3E-3) into coverage of the real production module, plus every
explicit failure mode Mac's 3E-4 checkpoint named: unknown team, missing
provider mapping, zero matching games, multiple matching games, reversed
home/away, kickoff-time mismatch, rescheduled game, malformed provider
event/lookup failure isolation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.persistence.game_identity import GameIdentityError
from app.persistence.games import GamesQueryError
from app.persistence.odds_game_linking import (
    GameLinkingError,
    LinkedEvent,
    ProviderEventIdentity,
    UnresolvedEvent,
    resolve_and_link_odds_events,
    resolve_odds_event_game_id,
)

SUPABASE_URL = "https://test-project.supabase.co"

KC_TEAM_ID = "team-kc"
BAL_TEAM_ID = "team-bal"
GAME_ID = "game-kc-bal"
KICKOFF = datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc)


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _mock_team_provider_ids(rows_by_provider: dict) -> None:
    def _respond(request: httpx.Request) -> httpx.Response:
        provider_name = request.url.params["provider_name"]
        ids_param = request.url.params["provider_team_id"]
        rows = [r for r in rows_by_provider.get(provider_name, []) if r["provider_team_id"] in ids_param]
        return httpx.Response(200, json=rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(side_effect=_respond)


def _game_row(*, game_id: str, home: str, away: str, scheduled_start: datetime) -> dict:
    return {
        "id": game_id,
        "external_provider_id": None,
        "home_team": home,
        "away_team": away,
        "scheduled_start": scheduled_start.isoformat(),
        "stadium": "Some Stadium",
        "status": "scheduled",
        "season_type": "regular",
        "week": 2,
    }


_STANDARD_TEAM_ROWS = {
    "eq.the_odds_api": [
        {"team_id": KC_TEAM_ID, "provider_team_id": "Kansas City Chiefs"},
        {"team_id": BAL_TEAM_ID, "provider_team_id": "Baltimore Ravens"},
    ],
    "eq.sportsdataio": [
        {"team_id": KC_TEAM_ID, "provider_team_id": "KC"},
        {"team_id": BAL_TEAM_ID, "provider_team_id": "BAL"},
    ],
}


@pytest.mark.asyncio
@respx.mock
async def test_deterministic_resolution_of_a_single_unambiguous_event():
    _mock_team_provider_ids(_STANDARD_TEAM_ROWS)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200, json=[_game_row(game_id=GAME_ID, home="KC", away="BAL", scheduled_start=KICKOFF)]
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_odds_event_game_id(
            client,
            _headers(),
            provider_game_id="event-1",
            home_team="Kansas City Chiefs",
            away_team="Baltimore Ravens",
            commence_time=KICKOFF,
        )

    assert result == LinkedEvent(provider_game_id="event-1", game_id=GAME_ID)


@pytest.mark.asyncio
@respx.mock
async def test_unknown_team_fails_safely_not_guessed():
    _mock_team_provider_ids({"eq.the_odds_api": [], "eq.sportsdataio": []})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_odds_event_game_id(
            client,
            _headers(),
            provider_game_id="event-unknown",
            home_team="Some Expansion Team",
            away_team="Baltimore Ravens",
            commence_time=KICKOFF,
        )

    assert isinstance(result, UnresolvedEvent)
    assert "unknown team" in result.reason


@pytest.mark.asyncio
@respx.mock
async def test_zero_matching_games_fails_safely():
    _mock_team_provider_ids(_STANDARD_TEAM_ROWS)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_odds_event_game_id(
            client,
            _headers(),
            provider_game_id="event-none",
            home_team="Kansas City Chiefs",
            away_team="Baltimore Ravens",
            commence_time=KICKOFF,
        )

    assert isinstance(result, UnresolvedEvent)
    assert "zero candidate games" in result.reason


@pytest.mark.asyncio
@respx.mock
async def test_multiple_matching_games_is_ambiguous_and_unresolved():
    """Two candidate games both match {home_team_id, away_team_id} AND both
    fall within kickoff tolerance -- must never guess which one is right."""
    _mock_team_provider_ids(_STANDARD_TEAM_ROWS)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200,
            json=[
                _game_row(game_id="game-a", home="KC", away="BAL", scheduled_start=KICKOFF),
                _game_row(game_id="game-b", home="KC", away="BAL", scheduled_start=KICKOFF + timedelta(minutes=5)),
            ],
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_odds_event_game_id(
            client,
            _headers(),
            provider_game_id="event-ambiguous",
            home_team="Kansas City Chiefs",
            away_team="Baltimore Ravens",
            commence_time=KICKOFF,
        )

    assert isinstance(result, UnresolvedEvent)
    assert "ambiguous" in result.reason


@pytest.mark.asyncio
@respx.mock
async def test_reversed_home_away_does_not_incorrectly_match():
    """The stored game has KC home / BAL away; the event reports the exact
    opposite. Strict ordered matching must produce zero matches, never a
    false-positive match against the same pairing reversed."""
    _mock_team_provider_ids(_STANDARD_TEAM_ROWS)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200, json=[_game_row(game_id=GAME_ID, home="KC", away="BAL", scheduled_start=KICKOFF)]
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_odds_event_game_id(
            client,
            _headers(),
            provider_game_id="event-reversed",
            home_team="Baltimore Ravens",  # reversed vs. the stored game
            away_team="Kansas City Chiefs",
            commence_time=KICKOFF,
        )

    assert isinstance(result, UnresolvedEvent)
    assert "zero games match" in result.reason


@pytest.mark.asyncio
@respx.mock
async def test_kickoff_time_mismatch_does_not_incorrectly_match():
    """Team identity matches, but the stored scheduled_start is well
    outside tolerance of the event's own commence_time -- must not match
    just because the teams line up."""
    _mock_team_provider_ids(_STANDARD_TEAM_ROWS)
    far_off_start = KICKOFF + timedelta(hours=20)  # inside the +/-1 day candidate window, outside 6h tolerance
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200, json=[_game_row(game_id=GAME_ID, home="KC", away="BAL", scheduled_start=far_off_start)]
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_odds_event_game_id(
            client,
            _headers(),
            provider_game_id="event-mismatch",
            home_team="Kansas City Chiefs",
            away_team="Baltimore Ravens",
            commence_time=KICKOFF,
        )

    assert isinstance(result, UnresolvedEvent)
    assert "ambiguous" in result.reason  # 1 team-matched candidate, 0 within tolerance


@pytest.mark.asyncio
@respx.mock
async def test_rescheduled_game_outside_candidate_window_is_unresolved_not_guessed():
    """The game's stored scheduled_start has moved far enough (e.g. a
    multi-day reschedule) that it falls outside the +/-1 day candidate
    window entirely -- correctly unresolved until Master Refresh's next
    Schedule fetch updates the stored time, never guessed against a stale
    window."""
    _mock_team_provider_ids(_STANDARD_TEAM_ROWS)
    rescheduled_start = KICKOFF + timedelta(days=3)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_odds_event_game_id(
            client,
            _headers(),
            provider_game_id="event-rescheduled",
            home_team="Kansas City Chiefs",
            away_team="Baltimore Ravens",
            commence_time=KICKOFF,
        )

    assert isinstance(result, UnresolvedEvent)
    assert "zero candidate games" in result.reason
    assert rescheduled_start > KICKOFF  # sanity: this really is the "moved far away" case being modeled


@pytest.mark.asyncio
@respx.mock
async def test_games_lookup_failure_raises_game_linking_error():
    _mock_team_provider_ids(_STANDARD_TEAM_ROWS)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(GameLinkingError):
            await resolve_odds_event_game_id(
                client,
                _headers(),
                provider_game_id="event-error",
                home_team="Kansas City Chiefs",
                away_team="Baltimore Ravens",
                commence_time=KICKOFF,
            )


# ---------------------------------------------------------------------------
# resolve_and_link_odds_events -- batch entry point, isolation, persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_batch_resolves_and_persists_link_for_a_successful_event():
    _mock_team_provider_ids(_STANDARD_TEAM_ROWS)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200, json=[_game_row(game_id=GAME_ID, home="KC", away="BAL", scheduled_start=KICKOFF)]
        )
    )
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(201))

    events = [
        ProviderEventIdentity(
            provider_game_id="event-1",
            home_team="Kansas City Chiefs",
            away_team="Baltimore Ravens",
            commence_time=KICKOFF,
        )
    ]

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_and_link_odds_events(client, _headers(), events)

    assert result.linked == [LinkedEvent(provider_game_id="event-1", game_id=GAME_ID)]
    assert result.unresolved == []
    assert link_route.called


@pytest.mark.asyncio
@respx.mock
async def test_batch_isolates_one_failing_event_and_continues_the_rest():
    """One event whose lookup raises GameLinkingError (simulating a
    malformed/unlookupable provider event) must not prevent a second,
    well-formed event in the same batch from resolving and linking."""
    call_count = {"n": 0}

    def _games_respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(500)  # first event: simulated lookup failure
        return httpx.Response(
            200, json=[_game_row(game_id=GAME_ID, home="KC", away="BAL", scheduled_start=KICKOFF)]
        )

    _mock_team_provider_ids(_STANDARD_TEAM_ROWS)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_games_respond)
    respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(201))

    events = [
        ProviderEventIdentity(
            provider_game_id="event-broken",
            home_team="Kansas City Chiefs",
            away_team="Baltimore Ravens",
            commence_time=KICKOFF,
        ),
        ProviderEventIdentity(
            provider_game_id="event-good",
            home_team="Kansas City Chiefs",
            away_team="Baltimore Ravens",
            commence_time=KICKOFF,
        ),
    ]

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_and_link_odds_events(client, _headers(), events)

    assert [e.provider_game_id for e in result.linked] == ["event-good"]
    assert [e.provider_game_id for e in result.unresolved] == ["event-broken"]
    assert "lookup failure" in result.unresolved[0].reason


@pytest.mark.asyncio
@respx.mock
async def test_batch_treats_link_persistence_failure_as_unresolved_not_a_crash():
    _mock_team_provider_ids(_STANDARD_TEAM_ROWS)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200, json=[_game_row(game_id=GAME_ID, home="KC", away="BAL", scheduled_start=KICKOFF)]
        )
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(409))

    events = [
        ProviderEventIdentity(
            provider_game_id="event-1",
            home_team="Kansas City Chiefs",
            away_team="Baltimore Ravens",
            commence_time=KICKOFF,
        )
    ]

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_and_link_odds_events(client, _headers(), events)

    assert result.linked == []
    assert len(result.unresolved) == 1
    assert "failed to persist link" in result.unresolved[0].reason
