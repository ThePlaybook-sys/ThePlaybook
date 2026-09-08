"""Tests for app.context_intelligence.news (Phase 8.1 Foundation Pass)
-- pure function, no I/O."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.context_intelligence.news import compute_news_context

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def _article(*, headline, hours_ago):
    ts = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {"headline": headline, "source_name": "Test Wire", "published_at": ts, "ingested_at": ts}


def _odds_snapshot(*, hours_ago, point):
    ts = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {
        "game_id": "g1",
        "sportsbook": "draftkings",
        "market_type": "spread",
        "line_data": {"outcomes": [{"name": "Home", "point": point, "price": -110}]},
        "captured_at": ts,
    }


def test_no_relevant_news_is_insufficient_evidence():
    result = compute_news_context(game_id="g1", news_articles_for_teams=[], now=NOW)
    assert result.insufficient_evidence is True
    assert result.sample_size == 0
    assert result.similarity_score is None


def test_causation_confounder_always_present_when_evidence_exists():
    articles = [_article(headline="Team signs new kicker", hours_ago=5)]
    result = compute_news_context(game_id="g1", news_articles_for_teams=articles, now=NOW)
    assert any("NOT evidence of causation" in c for c in result.confounders)


def test_category_unsupported_confounder_always_present():
    articles = [_article(headline="Team signs new kicker", hours_ago=5)]
    result = compute_news_context(game_id="g1", news_articles_for_teams=articles, now=NOW)
    assert any("category/type is not supported" in c for c in result.confounders)


def test_article_near_market_movement_window_is_flagged():
    odds = [_odds_snapshot(hours_ago=48, point=3.0), _odds_snapshot(hours_ago=1, point=1.0)]
    articles = [_article(headline="Star player questionable", hours_ago=2)]
    result = compute_news_context(game_id="g1", news_articles_for_teams=articles, target_odds_snapshots=odds, now=NOW)
    assert result.facts["articles_near_market_movement"] == 1
    assert result.similarity_score == 1.0


def test_article_far_from_market_movement_window_is_not_flagged():
    odds = [_odds_snapshot(hours_ago=48, point=3.0), _odds_snapshot(hours_ago=1, point=1.0)]
    articles = [_article(headline="Season preview", hours_ago=500)]
    result = compute_news_context(game_id="g1", news_articles_for_teams=articles, target_odds_snapshots=odds, now=NOW)
    assert result.facts["articles_near_market_movement"] == 0
    assert result.similarity_score == 0.0


def test_no_odds_history_reports_confounder_not_a_crash():
    articles = [_article(headline="Team signs new kicker", hours_ago=5)]
    result = compute_news_context(game_id="g1", news_articles_for_teams=articles, target_odds_snapshots=[], now=NOW)
    assert result.insufficient_evidence is False
    assert any("no real odds_snapshots history" in c for c in result.confounders)


def test_sample_size_matches_article_count():
    articles = [_article(headline=f"Headline {i}", hours_ago=i) for i in range(5)]
    result = compute_news_context(game_id="g1", news_articles_for_teams=articles, now=NOW)
    assert result.sample_size == 5
