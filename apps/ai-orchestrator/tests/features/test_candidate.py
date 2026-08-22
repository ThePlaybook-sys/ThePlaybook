"""Tests for app.features.candidate (Milestone 4.6, Decision G)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.features.candidate import MarketCandidate, candidate_key


def _candidate(**overrides) -> MarketCandidate:
    base = dict(
        game_id="g1",
        sportsbook="DraftKings",
        market_type="moneyline",
        selection="Kansas City Chiefs",
        american_odds=-125,
        point=None,
        observed_at=datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return MarketCandidate(**base)


def test_candidate_key_is_deterministic():
    a = _candidate()
    b = _candidate()
    assert candidate_key(a) == candidate_key(b)


def test_candidate_key_ignores_observed_at():
    a = _candidate(observed_at=datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc))
    b = _candidate(observed_at=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc))
    assert candidate_key(a) == candidate_key(b)


def test_candidate_key_differs_by_selection():
    a = _candidate(selection="Kansas City Chiefs")
    b = _candidate(selection="Buffalo Bills")
    assert candidate_key(a) != candidate_key(b)


def test_candidate_key_differs_by_market_type():
    a = _candidate(market_type="moneyline")
    b = _candidate(market_type="spread")
    assert candidate_key(a) != candidate_key(b)


def test_candidate_key_differs_by_point():
    a = _candidate(market_type="total", selection="Over", point=47.5)
    b = _candidate(market_type="total", selection="Over", point=48.0)
    assert candidate_key(a) != candidate_key(b)


def test_candidate_key_handles_none_point():
    candidate = _candidate(point=None)
    assert "none" in candidate_key(candidate)


def test_candidate_is_frozen():
    candidate = _candidate()
    try:
        candidate.selection = "Buffalo Bills"  # type: ignore[misc]
        assert False, "expected FrozenInstanceError"
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
