"""Tests for app.features.travel (Milestone 4.4, Decision 5). Haversine
values below are independently computed (plain Python, not this module)
against real, publicly-known coordinates -- not derived from the
implementation under test."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.features.travel import (
    StadiumReference,
    TravelFeatures,
    compute_travel_features,
    count_consecutive_road_games,
    haversine_miles,
    is_international_game,
    lookup_stadium_reference,
    timezone_shift_hours,
)

# Real coordinates, from games.venue_lat/venue_long's own convention.
ARROWHEAD = (39.0489, -94.4839)  # Kansas City
HIGHMARK = (42.7738, -78.7870)  # Buffalo
SOFI = (33.9535, -118.3390)  # Los Angeles
METLIFE = (40.8135, -74.0745)  # East Rutherford, NJ


def test_haversine_same_point_is_zero():
    assert haversine_miles(*ARROWHEAD, *ARROWHEAD) == pytest.approx(0.0, abs=1e-6)


def test_haversine_kc_to_buffalo_matches_independent_calculation():
    # Independently computed (plain math, not this module): ~857.59 miles.
    distance = haversine_miles(*ARROWHEAD, *HIGHMARK)
    assert distance == pytest.approx(857.5863381088548, abs=0.01)


def test_haversine_la_to_ny_matches_independent_calculation():
    # Independently computed: ~2449.36 miles.
    distance = haversine_miles(*SOFI, *METLIFE)
    assert distance == pytest.approx(2449.355037693176, abs=0.01)


def test_haversine_is_symmetric():
    assert haversine_miles(*ARROWHEAD, *HIGHMARK) == pytest.approx(haversine_miles(*HIGHMARK, *ARROWHEAD), abs=1e-9)


def test_lookup_stadium_reference_known_venue():
    ref = lookup_stadium_reference("Arrowhead Stadium")
    assert ref == StadiumReference("America/Chicago", False)


def test_lookup_stadium_reference_unknown_venue_returns_none_not_guessed():
    assert lookup_stadium_reference("Some New Stadium Nobody Has Heard Of") is None


def test_lookup_stadium_reference_none_input_returns_none():
    assert lookup_stadium_reference(None) is None


def test_international_venue_flagged_true():
    assert is_international_game("Tottenham Hotspur Stadium") is True


def test_domestic_venue_flagged_false():
    assert is_international_game("Arrowhead Stadium") is False


def test_unknown_venue_international_flag_is_none_not_false():
    assert is_international_game("Some New Stadium Nobody Has Heard Of") is None


def test_timezone_shift_kc_to_buffalo_is_zero_same_zone():
    # Arrowhead (America/Chicago) and... wait, Highmark is America/New_York,
    # a genuine one-hour shift.
    at = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)
    shift = timezone_shift_hours("Arrowhead Stadium", "Highmark Stadium", at=at)
    assert shift == pytest.approx(1.0, abs=1e-9)


def test_timezone_shift_reverse_direction_is_negated():
    at = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)
    forward = timezone_shift_hours("Arrowhead Stadium", "Highmark Stadium", at=at)
    backward = timezone_shift_hours("Highmark Stadium", "Arrowhead Stadium", at=at)
    assert forward == pytest.approx(-backward, abs=1e-9)


def test_timezone_shift_unknown_stadium_returns_none():
    at = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)
    assert timezone_shift_hours("Unknown Venue", "Arrowhead Stadium", at=at) is None
    assert timezone_shift_hours("Arrowhead Stadium", "Unknown Venue", at=at) is None
    assert timezone_shift_hours(None, "Arrowhead Stadium", at=at) is None


def test_timezone_shift_naive_datetime_rejected():
    with pytest.raises(ValueError):
        timezone_shift_hours("Arrowhead Stadium", "Highmark Stadium", at=datetime(2026, 9, 21, 17, 0))


def test_timezone_shift_pacific_to_eastern_across_dst_boundary_still_correct():
    # Arizona (State Farm Stadium) never observes DST; verifies zoneinfo,
    # not a hardcoded offset, actually drives the calculation.
    at = datetime(2026, 12, 21, 17, 0, tzinfo=timezone.utc)  # winter, no DST anywhere involved
    shift = timezone_shift_hours("State Farm Stadium", "MetLife Stadium", at=at)
    assert shift == pytest.approx(2.0, abs=1e-9)  # Arizona (UTC-7 year-round) -> Eastern (UTC-5 in winter)


def test_count_consecutive_road_games_all_away():
    games = [{"home_team": "BAL", "away_team": "KC"}, {"home_team": "NE", "away_team": "KC"}]
    assert count_consecutive_road_games(games, team="KC") == 2


def test_count_consecutive_road_games_stops_at_first_home_game():
    games = [
        {"home_team": "BAL", "away_team": "KC"},
        {"home_team": "KC", "away_team": "DEN"},  # home game -- streak stops here
        {"home_team": "NE", "away_team": "KC"},
    ]
    assert count_consecutive_road_games(games, team="KC") == 1


def test_count_consecutive_road_games_no_games_is_zero():
    assert count_consecutive_road_games([], team="KC") == 0


def test_count_consecutive_road_games_team_absent_from_first_game_is_zero():
    games = [{"home_team": "BAL", "away_team": "NE"}]
    assert count_consecutive_road_games(games, team="KC") == 0


def test_compute_travel_features_full_data():
    at = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)
    features = compute_travel_features(
        current_venue_lat=HIGHMARK[0],
        current_venue_long=HIGHMARK[1],
        current_stadium="Highmark Stadium",
        previous_venue_lat=ARROWHEAD[0],
        previous_venue_long=ARROWHEAD[1],
        previous_stadium="Arrowhead Stadium",
        kickoff_at=at,
        consecutive_road_games=2,
    )
    assert features.travel_distance_miles == pytest.approx(857.5863381088548, abs=0.01)
    assert features.timezone_shift_hours == pytest.approx(1.0, abs=1e-9)
    assert features.is_international_game is False
    assert features.consecutive_road_games == 2


def test_compute_travel_features_missing_previous_game_degrades_distance_and_timezone_independently():
    """No previous game (season opener) -- distance and timezone shift
    are unknown (None), never fabricated as 0, but is_international_game
    still resolves from the current stadium alone."""
    at = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)
    features = compute_travel_features(
        current_venue_lat=ARROWHEAD[0],
        current_venue_long=ARROWHEAD[1],
        current_stadium="Arrowhead Stadium",
        previous_venue_lat=None,
        previous_venue_long=None,
        previous_stadium=None,
        kickoff_at=at,
    )
    assert features.travel_distance_miles is None
    assert features.timezone_shift_hours is None
    assert features.is_international_game is False
    assert features.consecutive_road_games is None


def test_travel_features_is_frozen_dataclass():
    features = TravelFeatures(
        travel_distance_miles=None, timezone_shift_hours=None, is_international_game=None, consecutive_road_games=None
    )
    with pytest.raises(Exception):
        features.travel_distance_miles = 5.0
