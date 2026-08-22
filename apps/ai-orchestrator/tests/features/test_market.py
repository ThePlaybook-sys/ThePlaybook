"""Tests for app.features.market (Milestone 4.5). All fixtures use the
real production `{"outcomes": [...]}` shape (The Odds API v4), never the
demo-only `{"home": ..., "away": ...}` convenience shape."""
from __future__ import annotations

from app.features.market import LineMovementFeatures, compute_line_movement, parse_outcomes


def _snapshot(sportsbook: str, market_type: str, outcomes: list[dict], captured_at: str) -> dict:
    return {"sportsbook": sportsbook, "market_type": market_type, "line_data": {"outcomes": outcomes}, "captured_at": captured_at}


# --- parse_outcomes ---


def test_parse_outcomes_extracts_price_and_point_by_name():
    line_data = {"outcomes": [{"name": "BUF", "price": -150, "point": -3.5}, {"name": "KC", "price": 130, "point": 3.5}]}
    result = parse_outcomes(line_data)
    assert result == {"BUF": {"price": -150, "point": -3.5}, "KC": {"price": 130, "point": 3.5}}


def test_parse_outcomes_handles_totals_over_under():
    line_data = {"outcomes": [{"name": "Over", "price": -110, "point": 47.5}, {"name": "Under", "price": -110, "point": 47.5}]}
    result = parse_outcomes(line_data)
    assert result["Over"]["point"] == 47.5
    assert result["Under"]["point"] == 47.5


def test_parse_outcomes_missing_outcomes_key_returns_empty():
    assert parse_outcomes({}) == {}


def test_parse_outcomes_non_dict_line_data_returns_empty():
    assert parse_outcomes(None) == {}
    assert parse_outcomes("not a dict") == {}


def test_parse_outcomes_malformed_outcome_entries_are_skipped_not_fatal():
    line_data = {"outcomes": [{"name": "BUF", "price": -150, "point": -3.5}, "not a dict", {"price": 100}]}
    result = parse_outcomes(line_data)
    assert result == {"BUF": {"price": -150, "point": -3.5}}


def test_parse_outcomes_rejects_demo_only_shape_silently_not_by_crashing():
    # The demo-only {"home": ..., "away": ...} shape never reaches
    # production -- confirm it produces no outcomes rather than raising,
    # so a stray demo-shaped row degrades safely instead of crashing.
    assert parse_outcomes({"home": -120, "away": 100}) == {}


# --- compute_line_movement: single snapshot -> insufficient history, never 0 ---


def test_single_snapshot_produces_insufficient_history_not_zero_movement():
    snapshots = [_snapshot("DraftKings", "spread", [{"name": "BUF", "price": -150, "point": -3.5}], "2026-09-20T12:00:00+00:00")]
    features = compute_line_movement(snapshots)
    assert len(features) == 1
    feature = features[0]
    assert feature.insufficient_history is True
    assert feature.sample_count == 1
    assert feature.price_movement is None
    assert feature.point_movement is None
    assert feature.direction is None
    assert feature.opening_price is None  # no known distinct "opening" with only one observation
    assert feature.latest_price == -150  # but the current fact IS known


def test_empty_snapshots_returns_empty_list():
    assert compute_line_movement([]) == []


# --- compute_line_movement: multiple snapshots, hand-verified deltas ---


def test_two_snapshots_widening_line_movement_direction_and_magnitude():
    snapshots = [
        _snapshot("DraftKings", "spread", [{"name": "BUF", "price": -150, "point": -3.5}, {"name": "KC", "price": 130, "point": 3.5}], "2026-09-18T12:00:00+00:00"),
        _snapshot("DraftKings", "spread", [{"name": "BUF", "price": -130, "point": -2.5}, {"name": "KC", "price": 110, "point": 2.5}], "2026-09-20T12:00:00+00:00"),
    ]
    features = {f.side: f for f in compute_line_movement(snapshots)}
    buf = features["BUF"]
    assert buf.sample_count == 2
    assert buf.insufficient_history is False
    assert buf.opening_point == -3.5
    assert buf.latest_point == -2.5
    assert buf.point_movement == 1.0  # -2.5 - (-3.5)
    assert buf.opening_price == -150
    assert buf.latest_price == -130
    assert buf.price_movement == 20  # -130 - (-150)
    assert buf.direction == "up"

    kc = features["KC"]
    assert kc.point_movement == -1.0  # 2.5 - 3.5
    assert kc.direction == "down"


def test_narrowing_line_direction_is_down():
    snapshots = [
        _snapshot("FanDuel", "spread", [{"name": "BUF", "price": -110, "point": -1.0}], "2026-09-18T12:00:00+00:00"),
        _snapshot("FanDuel", "spread", [{"name": "BUF", "price": -150, "point": -3.0}], "2026-09-20T12:00:00+00:00"),
    ]
    feature = compute_line_movement(snapshots)[0]
    assert feature.point_movement == -2.0
    assert feature.direction == "down"


def test_zero_movement_produces_none_direction_not_a_fabricated_label():
    snapshots = [
        _snapshot("FanDuel", "total", [{"name": "Over", "price": -110, "point": 47.5}], "2026-09-18T12:00:00+00:00"),
        _snapshot("FanDuel", "total", [{"name": "Over", "price": -110, "point": 47.5}], "2026-09-20T12:00:00+00:00"),
    ]
    feature = compute_line_movement(snapshots)[0]
    assert feature.point_movement == 0
    assert feature.direction is None


def test_reversing_line_uses_first_and_last_only_not_max_swing():
    snapshots = [
        _snapshot("DraftKings", "spread", [{"name": "BUF", "price": -110, "point": -1.0}], "2026-09-15T12:00:00+00:00"),
        _snapshot("DraftKings", "spread", [{"name": "BUF", "price": -200, "point": -6.0}], "2026-09-17T12:00:00+00:00"),
        _snapshot("DraftKings", "spread", [{"name": "BUF", "price": -120, "point": -1.5}], "2026-09-20T12:00:00+00:00"),
    ]
    feature = compute_line_movement(snapshots)[0]
    assert feature.sample_count == 3
    assert feature.opening_point == -1.0
    assert feature.latest_point == -1.5
    assert feature.point_movement == -0.5  # first vs last only, not the -6.0 midpoint swing
    assert feature.direction == "down"


# --- multiple books/markets stay distinct, no synthetic consensus ---


def test_book_specific_movement_remains_distinct_no_blending():
    snapshots = [
        _snapshot("DraftKings", "spread", [{"name": "BUF", "price": -150, "point": -3.5}], "2026-09-18T12:00:00+00:00"),
        _snapshot("DraftKings", "spread", [{"name": "BUF", "price": -130, "point": -2.5}], "2026-09-20T12:00:00+00:00"),
        _snapshot("FanDuel", "spread", [{"name": "BUF", "price": -145, "point": -3.0}], "2026-09-18T12:05:00+00:00"),
        _snapshot("FanDuel", "spread", [{"name": "BUF", "price": -160, "point": -4.0}], "2026-09-20T12:05:00+00:00"),
    ]
    features = compute_line_movement(snapshots)
    by_book = {f.sportsbook: f for f in features}
    assert by_book["DraftKings"].point_movement == 1.0
    assert by_book["FanDuel"].point_movement == -1.0
    assert by_book["DraftKings"].direction == "up"
    assert by_book["FanDuel"].direction == "down"


def test_different_market_types_stay_separate_groups():
    snapshots = [
        _snapshot("DraftKings", "spread", [{"name": "BUF", "price": -150, "point": -3.5}], "2026-09-18T12:00:00+00:00"),
        _snapshot("DraftKings", "moneyline", [{"name": "BUF", "price": -180}], "2026-09-18T12:00:00+00:00"),
    ]
    features = compute_line_movement(snapshots)
    market_types = {f.market_type for f in features}
    assert market_types == {"spread", "moneyline"}


def test_line_movement_features_is_frozen():
    feature = LineMovementFeatures(
        sportsbook="DraftKings", market_type="spread", side="BUF", opening_price=None, latest_price=-150,
        price_movement=None, opening_point=None, latest_point=-3.5, point_movement=None, direction=None,
        sample_count=1, insufficient_history=True,
    )
    with_error = False
    try:
        feature.latest_price = -999  # type: ignore[misc]
    except Exception:
        with_error = True
    assert with_error
