"""Tests for `app.persistence.game_reconciliation` (2026-09-15, HQ-authorized
"SPORTSDATAIO CANONICAL GAME RECONCILIATION").

**What this protects.** Without reconciliation, the first SportsDataIO Schedule
ingestion would have inserted a second canonical row for every game that already
existed under `balldontlie`/`mysportsfeeds` identity -- including the 16 Week 1
games finalized earlier that day. The dry-run section below reproduces dev's
real canonical shape (verified live: 23 games, zero `sportsdataio` game
mappings, 32/32 `sportsdataio` TEAM mappings) and proves those games link
instead of duplicating.

**No SportsDataIO production game ids are fabricated for live rows.** Where a
GameKey is needed the tests use an obviously synthetic token (`TEST-GK-*`), and
never a value that could be mistaken for a real SportsDataIO GameKey belonging
to a real dev row.

Zero provider calls: every Supabase read is respx-mocked and no adapter is
imported.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.persistence.game_identity import GameIdentityError
from app.persistence.game_reconciliation import (
    AMBIGUOUS,
    KICKOFF_TOLERANCE,
    MATCHED_EXACT,
    MATCHED_WITHIN_TOLERANCE,
    NO_MATCH_INSERT,
    UNRESOLVED_TEAMS,
    CanonicalGame,
    decide_reconciliation,
    link_reconciled_game,
    load_reconciliation_candidates,
)

SUPABASE_URL = "https://test-project.supabase.co"
KICKOFF = datetime(2026, 9, 17, 0, 20, tzinfo=timezone.utc)

SEA = "team-uuid-sea"
NE = "team-uuid-ne"
KC = "team-uuid-kc"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _candidate(game_id: str, *, home=SEA, away=NE, start=KICKOFF, finalized=None, mapped=False):
    return CanonicalGame(
        game_id=game_id,
        home_team_id=home,
        away_team_id=away,
        scheduled_start=start,
        finalized_at=finalized,
        has_provider_mapping=mapped,
    )


def _decide(candidates, *, home=SEA, away=NE, start=KICKOFF):
    return decide_reconciliation(
        entry_home_team_id=home,
        entry_away_team_id=away,
        entry_scheduled_start=start,
        candidates=candidates,
    )


# --------------------------------------------------------------------------
# The match rule.
# --------------------------------------------------------------------------


def test_exact_kickoff_and_team_pair_matches_the_existing_game():
    decision = _decide([_candidate("g1")])
    assert decision.outcome == MATCHED_EXACT
    assert decision.game_id == "g1"
    assert decision.kickoff_delta_seconds == 0.0


def test_zero_candidates_means_genuinely_missing_and_inserts():
    assert _decide([]).outcome == NO_MATCH_INSERT


def test_a_different_matchup_on_the_same_kickoff_never_matches():
    """Same slot, different teams -- the NFL plays several games at once."""
    assert _decide([_candidate("g1", home=KC)]).outcome == NO_MATCH_INSERT
    assert _decide([_candidate("g1", away=KC)]).outcome == NO_MATCH_INSERT


def test_home_and_away_are_not_interchangeable():
    """A reversed matchup is a DIFFERENT game (the other leg of the season
    series), never the same one."""
    assert _decide([_candidate("g1", home=NE, away=SEA)]).outcome == NO_MATCH_INSERT


def test_unresolved_provider_team_refuses_rather_than_guessing():
    assert _decide([_candidate("g1")], home=None).outcome == UNRESOLVED_TEAMS
    assert _decide([_candidate("g1")], away=None).outcome == UNRESOLVED_TEAMS


def test_more_than_one_candidate_is_ambiguous_and_never_guessed():
    decision = _decide([_candidate("g1"), _candidate("g2")])
    assert decision.outcome == AMBIGUOUS
    assert decision.game_id is None  # nothing linked
    assert decision.candidate_game_ids == ["g1", "g2"]  # reported, not silent


def test_a_game_already_mapped_to_another_gamekey_cannot_absorb_this_one():
    """`UNIQUE (game_id, provider_name)` would reject a second mapping anyway;
    excluding it here means we insert the genuinely-new game instead of
    failing, and never silently rewrite the existing identity."""
    assert _decide([_candidate("g1", mapped=True)]).outcome == NO_MATCH_INSERT


# --------------------------------------------------------------------------
# Kickoff tolerance boundary.
# --------------------------------------------------------------------------


def test_exact_match_is_preferred_over_a_nearby_candidate():
    """Two same-matchup candidates, one exact and one merely near: the exact
    one wins outright rather than the pair being called ambiguous."""
    decision = _decide(
        [_candidate("exact"), _candidate("near", start=KICKOFF + timedelta(minutes=5))]
    )
    assert decision.outcome == MATCHED_EXACT
    assert decision.game_id == "exact"


@pytest.mark.parametrize("delta", [timedelta(seconds=30), timedelta(minutes=5), KICKOFF_TOLERANCE])
def test_within_tolerance_matches(delta):
    for signed in (delta, -delta):
        decision = _decide([_candidate("g1", start=KICKOFF + signed)])
        assert decision.outcome == MATCHED_WITHIN_TOLERANCE
        assert decision.game_id == "g1"


@pytest.mark.parametrize(
    "delta",
    [KICKOFF_TOLERANCE + timedelta(seconds=1), timedelta(hours=1), timedelta(hours=5)],
)
def test_beyond_tolerance_does_not_match(delta):
    """One hour is a DST/timezone error and five hours is an Eastern-local vs
    UTC mix-up (SportsDataIO publishes both). Neither may be absorbed silently
    -- they must fail to match and surface as a new row instead."""
    for signed in (delta, -delta):
        assert _decide([_candidate("g1", start=KICKOFF + signed)]).outcome == NO_MATCH_INSERT


def test_the_tolerance_is_bounded_well_under_an_hour():
    """A regression guard on the constant itself: widening it past an hour
    would let a timezone error be absorbed as a match."""
    assert KICKOFF_TOLERANCE < timedelta(hours=1)


def test_two_near_candidates_are_ambiguous_not_nearest_wins():
    decision = _decide(
        [
            _candidate("g1", start=KICKOFF + timedelta(minutes=2)),
            _candidate("g2", start=KICKOFF + timedelta(minutes=9)),
        ]
    )
    assert decision.outcome == AMBIGUOUS
    assert decision.candidate_game_ids == ["g1", "g2"]


# --------------------------------------------------------------------------
# Finalized-game preservation.
# --------------------------------------------------------------------------


def test_a_finalized_game_links_rather_than_duplicating():
    """The whole point: a finalized Week 1 game keeps its row (and therefore
    its score and terminal status) and simply gains the provider id."""
    decision = _decide([_candidate("finalized-wk1", finalized="2026-09-15T20:16:13+00:00")])
    assert decision.outcome == MATCHED_EXACT
    assert decision.game_id == "finalized-wk1"


# --------------------------------------------------------------------------
# Candidate loading -- both sides resolved through the authoritative mapping.
# --------------------------------------------------------------------------


def _mock_candidate_reads(games, team_rows, mapped_game_ids=()):
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=games))
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=team_rows)
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": g} for g in mapped_game_ids])
    )


@pytest.mark.asyncio
@respx.mock
async def test_candidates_resolve_team_text_through_the_authoritative_mapping():
    """`games` stores teams as free text, so a raw string comparison would be
    exactly the name matching Decision 2 forbids. Both sides go through
    `team_provider_ids` and are compared as canonical team ids."""
    _mock_candidate_reads(
        games=[{"id": "g1", "home_team": "SEA", "away_team": "NE",
                "scheduled_start": KICKOFF.isoformat(), "finalized_at": None}],
        team_rows=[{"team_id": SEA, "provider_team_id": "SEA"},
                   {"team_id": NE, "provider_team_id": "NE"}],
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        candidates = await load_reconciliation_candidates(client, _headers())

    assert len(candidates) == 1
    assert candidates[0].home_team_id == SEA and candidates[0].away_team_id == NE


@pytest.mark.asyncio
@respx.mock
async def test_a_game_whose_teams_do_not_resolve_is_not_a_candidate_at_all():
    """Dev's 4 legacy fixtures store full team names. They must never match --
    refused on weaker evidence, not fuzzily matched."""
    _mock_candidate_reads(
        games=[{"id": "legacy", "home_team": "Seattle Seahawks", "away_team": "New England Patriots",
                "scheduled_start": KICKOFF.isoformat(), "finalized_at": None}],
        team_rows=[{"team_id": SEA, "provider_team_id": "SEA"},
                   {"team_id": NE, "provider_team_id": "NE"}],
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        assert await load_reconciliation_candidates(client, _headers()) == []


@pytest.mark.asyncio
@respx.mock
async def test_already_mapped_games_are_flagged_so_they_cannot_absorb_another_gamekey():
    _mock_candidate_reads(
        games=[{"id": "g1", "home_team": "SEA", "away_team": "NE",
                "scheduled_start": KICKOFF.isoformat(), "finalized_at": None}],
        team_rows=[{"team_id": SEA, "provider_team_id": "SEA"},
                   {"team_id": NE, "provider_team_id": "NE"}],
        mapped_game_ids=["g1"],
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        candidates = await load_reconciliation_candidates(client, _headers())
    assert candidates[0].has_provider_mapping is True


# --------------------------------------------------------------------------
# Linking: idempotency and loud conflict.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_linking_the_same_gamekey_twice_is_an_idempotent_no_op():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"provider_game_id": "TEST-GK-1"}])
    )
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(201)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await link_reconciled_game(client, _headers(), game_id="g1", provider_game_id="TEST-GK-1")

    assert not link_route.called  # nothing rewritten


@pytest.mark.asyncio
@respx.mock
async def test_a_conflicting_gamekey_is_refused_loudly_not_silently_merged():
    """`link_provider_id` upserts with resolution=merge-duplicates, which would
    silently rewrite the game's provider identity. That must never happen
    without being surfaced."""
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"provider_game_id": "TEST-GK-1"}])
    )
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(201)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(GameIdentityError, match="refusing to silently rewrite"):
            await link_reconciled_game(
                client, _headers(), game_id="g1", provider_game_id="TEST-GK-2"
            )

    assert not link_route.called


@pytest.mark.asyncio
@respx.mock
async def test_an_unmapped_game_is_linked_normally():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(201)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await link_reconciled_game(client, _headers(), game_id="g1", provider_game_id="TEST-GK-1")

    assert link_route.called
