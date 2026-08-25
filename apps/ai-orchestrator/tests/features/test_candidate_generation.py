"""Tests for app.features.candidate_generation (Milestone 4.9, Decision 1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.features.candidate_generation import (
    CandidateGenerationError,
    SkippedMarket,
    generate_candidates_for_game,
    max_snapshot_age_seconds,
    select_reference_sportsbook,
)

KICKOFF = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)


def _row(sportsbook: str, market_type: str, outcomes: list[dict], captured_at: datetime) -> dict:
    return {"sportsbook": sportsbook, "market_type": market_type, "line_data": {"outcomes": outcomes}, "captured_at": captured_at}


def _ml_outcomes() -> list[dict]:
    return [{"name": "KC", "price": -150}, {"name": "BAL", "price": 130}]


def _spread_outcomes() -> list[dict]:
    return [{"name": "KC", "price": -110, "point": -3.0}, {"name": "BAL", "price": -110, "point": 3.0}]


def _total_outcomes() -> list[dict]:
    return [{"name": "Over", "price": -105, "point": 47.5}, {"name": "Under", "price": -115, "point": 47.5}]


def _full_book(sportsbook: str, *, now: datetime) -> list[dict]:
    return [
        _row(sportsbook, "moneyline", _ml_outcomes(), now),
        _row(sportsbook, "spread", _spread_outcomes(), now),
        _row(sportsbook, "total", _total_outcomes(), now),
    ]


# --- max_snapshot_age_seconds / freshness tiers ---


def test_naive_datetime_raises():
    with pytest.raises(CandidateGenerationError):
        max_snapshot_age_seconds(now=datetime(2026, 9, 21, 10), kickoff=KICKOFF)


def test_far_tier_ceiling_is_24h_plus_grace():
    now = KICKOFF - timedelta(days=3)
    assert max_snapshot_age_seconds(now=now, kickoff=KICKOFF) == 86400 + 300


def test_ramp_2h_tier_ceiling():
    now = KICKOFF - timedelta(hours=1, minutes=30)
    assert max_snapshot_age_seconds(now=now, kickoff=KICKOFF) == 3600 + 300


def test_ramp_5m_tier_ceiling():
    now = KICKOFF - timedelta(minutes=2)
    assert max_snapshot_age_seconds(now=now, kickoff=KICKOFF) == 120 + 300


def test_stopped_tier_at_or_after_kickoff_reuses_ramp_5m_interval():
    assert max_snapshot_age_seconds(now=KICKOFF, kickoff=KICKOFF) == 120 + 300
    assert max_snapshot_age_seconds(now=KICKOFF + timedelta(minutes=10), kickoff=KICKOFF) == 120 + 300


# --- select_reference_sportsbook ---


def test_selects_first_preferred_book_with_fresh_data():
    now = KICKOFF - timedelta(hours=3)
    rows = _full_book("draftkings", now=now)
    result = select_reference_sportsbook(rows, reference_sportsbook_preference=["draftkings", "fanduel"], now=now, kickoff=KICKOFF)
    assert result == "draftkings"


def test_falls_back_to_next_preferred_book_when_first_has_no_data():
    now = KICKOFF - timedelta(hours=3)
    rows = _full_book("fanduel", now=now)
    result = select_reference_sportsbook(rows, reference_sportsbook_preference=["draftkings", "fanduel"], now=now, kickoff=KICKOFF)
    assert result == "fanduel"


def test_falls_back_when_first_book_data_is_stale():
    now = KICKOFF - timedelta(hours=3)
    stale_captured = now - timedelta(days=2)  # far outside the 24h+grace FAR-tier ceiling
    rows = _full_book("draftkings", now=stale_captured) + _full_book("fanduel", now=now)
    result = select_reference_sportsbook(rows, reference_sportsbook_preference=["draftkings", "fanduel"], now=now, kickoff=KICKOFF)
    assert result == "fanduel"


def test_returns_none_when_no_configured_book_has_fresh_data():
    now = KICKOFF - timedelta(hours=3)
    result = select_reference_sportsbook([], reference_sportsbook_preference=["draftkings", "fanduel"], now=now, kickoff=KICKOFF)
    assert result is None


def test_never_falls_back_to_an_unconfigured_sportsbook():
    now = KICKOFF - timedelta(hours=3)
    rows = _full_book("some_random_book_not_in_preference_list", now=now)
    result = select_reference_sportsbook(rows, reference_sportsbook_preference=["draftkings", "fanduel"], now=now, kickoff=KICKOFF)
    assert result is None


# --- generate_candidates_for_game: V1 scope, both sides, no pre-selection ---


def test_generates_all_six_v1_candidates_from_a_complete_fresh_book():
    now = KICKOFF - timedelta(hours=3)
    rows = _full_book("draftkings", now=now)
    result = generate_candidates_for_game(
        game_id="g1", home_team="KC", away_team="BAL", kickoff=KICKOFF, now=now,
        odds_rows=rows, reference_sportsbook_preference=["draftkings"],
    )
    assert result.sportsbook_used == "draftkings"
    assert result.game_skipped_reason is None
    assert len(result.candidates) == 6
    selections = {(c.market_type, c.selection, c.point) for c in result.candidates}
    assert selections == {
        ("moneyline", "KC", None), ("moneyline", "BAL", None),
        ("spread", "KC", -3.0), ("spread", "BAL", 3.0),
        ("total", "Over", 47.5), ("total", "Under", 47.5),
    }
    # No pre-selection of a "winner" -- both sides of every market are
    # independent candidates with their own real american_odds:
    ml_kc = next(c for c in result.candidates if c.market_type == "moneyline" and c.selection == "KC")
    ml_bal = next(c for c in result.candidates if c.market_type == "moneyline" and c.selection == "BAL")
    assert ml_kc.american_odds == -150
    assert ml_bal.american_odds == 130


def test_never_generates_prop_candidates():
    now = KICKOFF - timedelta(hours=3)
    rows = _full_book("draftkings", now=now) + [
        _row("draftkings", "prop", [{"name": "Mahomes Over 1.5 TDs", "price": -120}], now)
    ]
    result = generate_candidates_for_game(
        game_id="g1", home_team="KC", away_team="BAL", kickoff=KICKOFF, now=now,
        odds_rows=rows, reference_sportsbook_preference=["draftkings"],
    )
    assert all(c.market_type != "prop" for c in result.candidates)
    assert len(result.candidates) == 6  # the prop row is silently never considered, not an error


def test_partial_book_skips_missing_market_but_proceeds_with_the_rest():
    now = KICKOFF - timedelta(hours=3)
    rows = [_row("draftkings", "moneyline", _ml_outcomes(), now), _row("draftkings", "total", _total_outcomes(), now)]
    result = generate_candidates_for_game(
        game_id="g1", home_team="KC", away_team="BAL", kickoff=KICKOFF, now=now,
        odds_rows=rows, reference_sportsbook_preference=["draftkings"],
    )
    assert result.sportsbook_used == "draftkings"
    assert len(result.candidates) == 4  # 2 moneyline + 2 total, spread skipped
    assert result.skipped_markets == (SkippedMarket(market_type="spread", reason="no_snapshot"),)


def test_stale_market_within_an_otherwise_fresh_book_is_skipped_with_reason():
    now = KICKOFF - timedelta(hours=3)
    stale = now - timedelta(days=2)
    rows = [
        _row("draftkings", "moneyline", _ml_outcomes(), now),
        _row("draftkings", "spread", _spread_outcomes(), now),
        _row("draftkings", "total", _total_outcomes(), stale),
    ]
    result = generate_candidates_for_game(
        game_id="g1", home_team="KC", away_team="BAL", kickoff=KICKOFF, now=now,
        odds_rows=rows, reference_sportsbook_preference=["draftkings"],
    )
    assert len(result.candidates) == 4
    reasons = {(s.market_type, s.reason) for s in result.skipped_markets}
    assert reasons == {("total", "stale_snapshot")}


def test_no_qualifying_sportsbook_skips_the_whole_game_honestly():
    now = KICKOFF - timedelta(hours=3)
    result = generate_candidates_for_game(
        game_id="g1", home_team="KC", away_team="BAL", kickoff=KICKOFF, now=now,
        odds_rows=[], reference_sportsbook_preference=["draftkings", "fanduel"],
    )
    assert result.sportsbook_used is None
    assert result.candidates == ()
    assert result.game_skipped_reason == "no_configured_sportsbook_has_fresh_data"


def test_never_fabricates_odds_for_a_missing_market():
    now = KICKOFF - timedelta(hours=3)
    rows = [_row("draftkings", "moneyline", _ml_outcomes(), now)]
    result = generate_candidates_for_game(
        game_id="g1", home_team="KC", away_team="BAL", kickoff=KICKOFF, now=now,
        odds_rows=rows, reference_sportsbook_preference=["draftkings"],
    )
    assert len(result.candidates) == 2  # only what real data supports, never invented spread/total
    assert {s.market_type for s in result.skipped_markets} == {"spread", "total"}


def test_book_shopping_across_markets_never_happens():
    """A book earlier in preference has moneyline but NOT spread/total;
    a later book has spread/total but is never consulted for them --
    the whole game stays pinned to the FIRST qualifying book, per Mac's
    explicit 'no book-shopping' instruction."""
    now = KICKOFF - timedelta(hours=3)
    rows = [_row("draftkings", "moneyline", _ml_outcomes(), now)] + _full_book("fanduel", now=now)
    result = generate_candidates_for_game(
        game_id="g1", home_team="KC", away_team="BAL", kickoff=KICKOFF, now=now,
        odds_rows=rows, reference_sportsbook_preference=["draftkings", "fanduel"],
    )
    assert result.sportsbook_used == "draftkings"
    assert len(result.candidates) == 2  # only draftkings' moneyline -- fanduel's spread/total never used
    assert all(c.sportsbook == "draftkings" for c in result.candidates)
