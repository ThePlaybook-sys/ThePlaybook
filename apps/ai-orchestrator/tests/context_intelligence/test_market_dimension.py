"""Tests for app.context_intelligence.market (Phase 8.1 Foundation
Pass) -- pure function, no I/O. Real `line_data` shape throughout
(`{"outcomes": [...]}`, The Odds API v4 -- see `app.features.market`'s
own module docstring for why the friendlier `{"home":..., "away":...}`
demo shape never appears here)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.context_intelligence.market import compute_market_context

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def _snapshot(*, game_id, point, price, hours_ago, sportsbook="draftkings", market_type="spread"):
    ts = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {
        "game_id": game_id,
        "sportsbook": sportsbook,
        "market_type": market_type,
        "line_data": {"outcomes": [{"name": "Home", "point": point, "price": price}, {"name": "Away", "point": -point, "price": -price}]},
        "captured_at": ts,
    }


def test_no_target_history_is_insufficient_evidence():
    result = compute_market_context(game_id="g1", target_snapshots=[], all_odds_rows=[], now=NOW)
    assert result.insufficient_evidence is True
    assert result.sample_size == 0


def test_single_snapshot_no_computable_movement_is_insufficient_evidence():
    target = [_snapshot(game_id="g1", point=3.5, price=-110, hours_ago=1)]
    result = compute_market_context(game_id="g1", target_snapshots=target, all_odds_rows=target, now=NOW)
    assert result.insufficient_evidence is True
    assert "no computable point-based movement" in result.insufficient_evidence_reason


def test_sparse_comparable_pool_is_insufficient_evidence():
    target = [
        _snapshot(game_id="g1", point=3.5, price=-110, hours_ago=10),
        _snapshot(game_id="g1", point=2.5, price=-115, hours_ago=1),
    ]
    other_game = [
        _snapshot(game_id="g2", point=4.0, price=-110, hours_ago=10),
        _snapshot(game_id="g2", point=3.0, price=-115, hours_ago=1),
    ]
    all_rows = target + other_game
    result = compute_market_context(game_id="g1", target_snapshots=target, all_odds_rows=all_rows, now=NOW)
    assert result.sample_size == 1
    assert result.insufficient_evidence is True


def test_sufficient_evidence_with_similar_movement_pool():
    target = [
        _snapshot(game_id="g1", point=3.5, price=-110, hours_ago=10),
        _snapshot(game_id="g1", point=2.5, price=-115, hours_ago=1),
    ]
    g2 = [
        _snapshot(game_id="g2", point=4.0, price=-110, hours_ago=10),
        _snapshot(game_id="g2", point=3.0, price=-115, hours_ago=1),
    ]
    g3 = [
        _snapshot(game_id="g3", point=6.0, price=-110, hours_ago=10),
        _snapshot(game_id="g3", point=5.0, price=-115, hours_ago=1),
    ]
    all_rows = target + g2 + g3
    result = compute_market_context(game_id="g1", target_snapshots=target, all_odds_rows=all_rows, now=NOW)
    assert result.insufficient_evidence is False
    assert result.sample_size == 2
    assert result.similarity_score is not None
    assert result.confidence is not None
    assert result.facts["movement_groups"][0]["point_movement"] == -1.0


def test_market_movement_with_no_explanatory_context():
    """A qualifying (WATCH+) real movement with zero weather/news
    evidence in its window must report explained=False, never a
    fabricated explanation."""
    target = [
        _snapshot(game_id="g1", point=3.0, price=-110, hours_ago=10),
        _snapshot(game_id="g1", point=0.5, price=-110, hours_ago=1),  # 2.5 point move -> ELEVATED
    ]
    g2 = [
        _snapshot(game_id="g2", point=4.0, price=-110, hours_ago=10),
        _snapshot(game_id="g2", point=1.5, price=-110, hours_ago=1),
    ]
    all_rows = target + g2
    result = compute_market_context(
        game_id="g1", target_snapshots=target, all_odds_rows=all_rows,
        weather_snapshots_for_game=[], news_articles_for_teams=[], now=NOW,
    )
    evidence = result.facts["explanatory_evidence"]
    assert len(evidence) == 2  # both sides (Home/Away) of the one spread group
    for entry in evidence.values():
        assert entry["classification"] in ("WATCH", "ELEVATED", "SEVERE")
        assert entry["explained"] is False
        assert entry["matched_categories"] == []


def test_market_movement_with_real_explanatory_weather_evidence():
    target = [
        _snapshot(game_id="g1", point=3.0, price=-110, hours_ago=10),
        _snapshot(game_id="g1", point=0.5, price=-110, hours_ago=1),
    ]
    g2 = [
        _snapshot(game_id="g2", point=4.0, price=-110, hours_ago=10),
        _snapshot(game_id="g2", point=1.5, price=-110, hours_ago=1),
    ]
    weather_evidence = [{"id": "w1", "captured_at": (NOW - timedelta(hours=2)).isoformat()}]
    result = compute_market_context(
        game_id="g1", target_snapshots=target, all_odds_rows=target + g2,
        weather_snapshots_for_game=weather_evidence, news_articles_for_teams=[], now=NOW,
    )
    evidence = result.facts["explanatory_evidence"]
    key = next(iter(evidence))
    assert evidence[key]["explained"] is True
    assert "weather" in evidence[key]["matched_categories"]


def _moneyline_snapshot(*, game_id, home_price, away_price, hours_ago):
    ts = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {
        "game_id": game_id,
        "sportsbook": "draftkings",
        "market_type": "moneyline",
        "line_data": {"outcomes": [{"name": "Home", "price": home_price}, {"name": "Away", "price": away_price}]},
        "captured_at": ts,
    }


def test_moneyline_only_movement_excluded_from_similarity_but_reported_in_facts():
    """A group with only price movement (no point movement) contributes
    nothing to the cross-game point-based similarity, but its real facts
    are still reported, never silently dropped."""
    target = [
        _moneyline_snapshot(game_id="g1", home_price=-110, away_price=-110, hours_ago=10),
        _moneyline_snapshot(game_id="g1", home_price=-150, away_price=130, hours_ago=1),
    ]
    # No point-based group exists at all for this game -> insufficient evidence,
    # but the moneyline facts must still be present.
    result = compute_market_context(game_id="g1", target_snapshots=target, all_odds_rows=target, now=NOW)
    assert result.insufficient_evidence is True
    price_movements = {g["price_movement"] for g in result.facts["movement_groups"]}
    assert -40 in price_movements
