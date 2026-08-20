"""Tests for app.persistence.daily_game_intelligence's pure assembly logic
(Phase 3E-2) -- the field-ownership behavior is the load-bearing thing
being proven here, not just "does it produce JSON."
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.persistence.daily_game_intelligence import build_payload


def _now():
    return datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def test_phase4_5_fields_never_appear_in_payload():
    payload = build_payload(
        game_id="g1",
        teams={"home": "SEA", "away": "NE"},
        players=None,
        odds_row=None,
        props_row=None,
        injury_row=None,
        weather_row=None,
        existing_news=None,
        rest={"home": {"rest_days": None, "season_opener": True}, "away": {"rest_days": None, "season_opener": True}},
        stadium=None,
        now=_now(),
    )
    forbidden = {
        "ai_scores",
        "momentum",
        "matchup_ratings",
        "ev_calculations",
        "confidence_scores",
        "recommendation_candidates",
    }
    assert forbidden.isdisjoint(payload.keys())


def test_public_betting_and_sharp_money_are_explicit_null_not_omitted():
    payload = build_payload(
        game_id="g1",
        teams={"home": "SEA", "away": "NE"},
        players=None,
        odds_row=None,
        props_row=None,
        injury_row=None,
        weather_row=None,
        existing_news=None,
        rest={"home": {}, "away": {}},
        stadium=None,
        now=_now(),
    )
    assert "public_betting" in payload and payload["public_betting"] is None
    assert "sharp_money" in payload and payload["sharp_money"] is None


def test_missing_odds_row_is_null_not_fabricated():
    payload = build_payload(
        game_id="g1",
        teams={"home": "SEA", "away": "NE"},
        players=None,
        odds_row=None,
        props_row=None,
        injury_row=None,
        weather_row=None,
        existing_news=None,
        rest={"home": {}, "away": {}},
        stadium=None,
        now=_now(),
    )
    assert payload["odds"] is None
    assert payload["props"] is None
    assert payload["injuries"] is None
    assert payload["weather"] is None


def test_travel_always_null_for_3e2():
    payload = build_payload(
        game_id="g1",
        teams={"home": "SEA", "away": "NE"},
        players=None,
        odds_row=None,
        props_row=None,
        injury_row=None,
        weather_row=None,
        existing_news=None,
        rest={"home": {}, "away": {}},
        stadium=None,
        now=_now(),
    )
    assert payload["travel"] is None


def test_existing_news_preserved_verbatim():
    payload = build_payload(
        game_id="g1",
        teams={"home": "SEA", "away": "NE"},
        players=None,
        odds_row=None,
        props_row=None,
        injury_row=None,
        weather_row=None,
        existing_news={"headline": "already there"},
        rest={"home": {}, "away": {}},
        stadium=None,
        now=_now(),
    )
    assert payload["news"] == {"headline": "already there"}


def test_odds_row_present_gets_fresh_status_within_ttl():
    odds_row = {
        "sportsbook": "DraftKings",
        "market_type": "spread",
        "line_data": {"home": -3.5},
        "captured_at": (_now() - timedelta(seconds=30)).isoformat(),
    }
    payload = build_payload(
        game_id="g1",
        teams={"home": "SEA", "away": "NE"},
        players=None,
        odds_row=odds_row,
        props_row=None,
        injury_row=None,
        weather_row=None,
        existing_news=None,
        rest={"home": {}, "away": {}},
        stadium=None,
        now=_now(),
    )
    assert payload["odds"]["status"] == "fresh"
    assert payload["odds"]["source"] == "the_odds_api"
    assert "confidence" not in payload["odds"]


def test_odds_row_stale_beyond_three_ttls():
    odds_row = {
        "sportsbook": "DraftKings",
        "market_type": "spread",
        "line_data": {"home": -3.5},
        "captured_at": (_now() - timedelta(hours=1)).isoformat(),  # >> 60s*3
    }
    payload = build_payload(
        game_id="g1",
        teams={"home": "SEA", "away": "NE"},
        players=None,
        odds_row=odds_row,
        props_row=None,
        injury_row=None,
        weather_row=None,
        existing_news=None,
        rest={"home": {}, "away": {}},
        stadium=None,
        now=_now(),
    )
    assert payload["odds"]["status"] == "stale"


def test_stadium_name_only_when_provided():
    payload = build_payload(
        game_id="g1",
        teams={"home": "SEA", "away": "NE"},
        players=None,
        odds_row=None,
        props_row=None,
        injury_row=None,
        weather_row=None,
        existing_news=None,
        rest={"home": {}, "away": {}},
        stadium={"name": "Lumen Field"},
        now=_now(),
    )
    assert payload["stadium"] == {"name": "Lumen Field"}


def test_props_row_present_assembles_without_raising(monkeypatch):
    """Regression test for a pre-existing bug (found 2026-08-20 via
    DEMO-3's scenario-runner integration test, the first thing to ever
    drive this function with a non-null props_row): `build_payload` used
    to call `_freshness_status(..., category="props")`, but
    `CATEGORY_TTL_SECONDS` (app.adapters.cache) only defines
    `"player_props"` -- `KeyError: 'props'`, unconditionally, every time.
    Every other test in this file passes `props_row=None`, which is
    exactly why nothing caught this until a real props snapshot flowed
    all the way through."""
    props_row = {
        "sportsbook": "DraftKings",
        "market_type": "prop",
        "line_data": {"player_external_id": "p1", "prop_type": "player_pass_tds", "line": 1.5},
        "captured_at": (_now() - timedelta(seconds=30)).isoformat(),
    }
    payload = build_payload(
        game_id="g1",
        teams={"home": "SEA", "away": "NE"},
        players=None,
        odds_row=None,
        props_row=props_row,
        injury_row=None,
        weather_row=None,
        existing_news=None,
        rest={"home": {}, "away": {}},
        stadium=None,
        now=_now(),
    )
    assert payload["props"]["status"] == "fresh"
    assert payload["props"]["source"] == "the_odds_api"

    from app.adapters.cache import CATEGORY_TTL_SECONDS
    from app.persistence.daily_game_intelligence import _freshness_status

    # Proves the fix actually reads CATEGORY_TTL_SECONDS["player_props"],
    # not a hardcoded/coincidentally-matching value: changing that TTL
    # changes whether an identical props_row reads "fresh" or "stale".
    monkeypatch.setitem(CATEGORY_TTL_SECONDS, "player_props", 1)
    stale_status = _freshness_status(props_row["captured_at"], category="player_props", now=_now())
    assert stale_status == "stale"

    # And the old, buggy category name is confirmed gone, not just papered over.
    import pytest

    with pytest.raises(KeyError):
        _freshness_status(props_row["captured_at"], category="props", now=_now())
