"""Tests for app.context_intelligence.venue (Phase 8.1 Foundation Pass)
-- pure function, no I/O."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.context_intelligence.venue import compute_venue_context

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def _game(*, venue_id="venue-1", venue_type="outdoor"):
    return {
        "id": "g1",
        "home_team": "SEA",
        "away_team": "NE",
        "venue_id": venue_id,
        "venue_lat": 47.5,
        "venue_long": -122.3,
        "venue_type": venue_type,
        "stadium": "Lumen Field",
        "scheduled_start": NOW.isoformat(),
    }


def test_missing_game_is_insufficient_evidence():
    result = compute_venue_context(game=None, venue=None, other_games_sharing_venue=[], now=NOW)
    assert result.insufficient_evidence is True
    assert result.insufficient_evidence_reason == "game not found"


def test_no_venue_id_resolved_is_insufficient_evidence():
    game = _game(venue_id=None)
    result = compute_venue_context(game=game, venue=None, other_games_sharing_venue=[], now=NOW)
    assert result.insufficient_evidence is True
    assert "no canonical venue_id" in result.insufficient_evidence_reason
    # Facts (venue_type etc.) are still reported even when insufficient.
    assert result.facts["venue_type"] == "outdoor"


def test_sofi_unresolved_venue_type_stays_null_never_coerced():
    game = _game(venue_type=None)
    result = compute_venue_context(game=game, venue=None, other_games_sharing_venue=[], now=NOW)
    assert result.facts["venue_type"] is None


def test_sparse_venue_history_is_insufficient_evidence():
    game = _game()
    other = [{"id": "g2", "scheduled_start": (NOW - timedelta(days=10)).isoformat()}]
    result = compute_venue_context(game=game, venue=None, other_games_sharing_venue=other, now=NOW)
    assert result.sample_size == 1
    assert result.insufficient_evidence is True


def test_sufficient_venue_history_reports_literal_similarity():
    game = _game()
    venue = {"id": "venue-1", "name": "Lumen Field", "city": "Seattle", "state": "WA"}
    other = [
        {"id": "g2", "scheduled_start": (NOW - timedelta(days=10)).isoformat()},
        {"id": "g3", "scheduled_start": (NOW - timedelta(days=20)).isoformat()},
    ]
    result = compute_venue_context(game=game, venue=venue, other_games_sharing_venue=other, now=NOW)
    assert result.insufficient_evidence is False
    assert result.sample_size == 2
    assert result.similarity_score == 1.0
    assert result.confidence is not None
    assert result.facts["venue_name"] == "Lumen Field"
