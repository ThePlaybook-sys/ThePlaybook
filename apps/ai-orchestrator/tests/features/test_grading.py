"""Tests for app.features.grading (Milestone 5.4) -- the deterministic
grading engine. Pure functions, no I/O -- every case here is a plain
value-in/value-out assertion."""
from __future__ import annotations

import pytest

from app.features.consensus import CandidateDirectionError
from app.features.grading import (
    GRADING_VERSION,
    MarketGradingUnsupportedError,
    grade_leg,
    rollup_product_outcome,
)

_HOME, _AWAY = "KC", "BAL"


def _final(home: float, away: float) -> dict:
    return {"home": home, "away": away}


# --- moneyline -----------------------------------------------------------


def test_moneyline_win_home_favorite_selected():
    result = grade_leg(
        market_type="moneyline", selection=_HOME, point=None, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=_final(27, 24),
    )
    assert result.outcome == "WIN"
    assert result.authoritative_result["final_score"] == {"home": 27.0, "away": 24.0}


def test_moneyline_loss_away_selected_home_wins():
    result = grade_leg(
        market_type="moneyline", selection=_AWAY, point=None, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=_final(27, 24),
    )
    assert result.outcome == "LOSS"


def test_moneyline_tie_is_push():
    result = grade_leg(
        market_type="moneyline", selection=_HOME, point=None, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=_final(20, 20),
    )
    assert result.outcome == "PUSH"


# --- spread ----------------------------------------------------------------


def test_spread_win():
    # KC -3.5, wins by 4 -> covers.
    result = grade_leg(
        market_type="spread", selection=_HOME, point=-3.5, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=_final(27, 23),
    )
    assert result.outcome == "WIN"


def test_spread_loss():
    # KC -3.5, wins by only 3 -> does not cover.
    result = grade_leg(
        market_type="spread", selection=_HOME, point=-3.5, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=_final(27, 24),
    )
    assert result.outcome == "LOSS"


def test_spread_push():
    # KC -3, wins by exactly 3 -> push.
    result = grade_leg(
        market_type="spread", selection=_HOME, point=-3, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=_final(27, 24),
    )
    assert result.outcome == "PUSH"


# --- total -------------------------------------------------------------------


def test_total_over_win():
    result = grade_leg(
        market_type="total", selection="Over", point=47.5, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=_final(27, 24),
    )
    assert result.outcome == "WIN"


def test_total_under_win():
    result = grade_leg(
        market_type="total", selection="Under", point=52.5, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=_final(27, 24),
    )
    assert result.outcome == "WIN"


def test_total_loss():
    result = grade_leg(
        market_type="total", selection="Over", point=52.5, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=_final(27, 24),
    )
    assert result.outcome == "LOSS"


def test_total_push():
    result = grade_leg(
        market_type="total", selection="Over", point=51, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=_final(27, 24),
    )
    assert result.outcome == "PUSH"


# --- non-standard game states -----------------------------------------------


def test_missing_final_data_does_not_fabricate_a_grade():
    result = grade_leg(
        market_type="moneyline", selection=_HOME, point=None, home_team=_HOME, away_team=_AWAY,
        game_status="final", final_score=None,
    )
    assert result.outcome == "PENDING_MISSING_DATA"


def test_postponed_game_is_void_no_action():
    result = grade_leg(
        market_type="moneyline", selection=_HOME, point=None, home_team=_HOME, away_team=_AWAY,
        game_status="postponed", final_score=None,
    )
    assert result.outcome == "VOID_NO_ACTION"


def test_canceled_game_is_void_no_action():
    result = grade_leg(
        market_type="spread", selection=_HOME, point=-3.5, home_team=_HOME, away_team=_AWAY,
        game_status="canceled", final_score=None,
    )
    assert result.outcome == "VOID_NO_ACTION"


# --- unsupported markets / malformed legs -----------------------------------


def test_player_prop_raises_unsupported_never_fabricates():
    with pytest.raises(MarketGradingUnsupportedError):
        grade_leg(
            market_type="prop", selection="Player X Over 249.5 passing yards", point=249.5,
            home_team=_HOME, away_team=_AWAY, game_status="final", final_score=_final(27, 24),
        )


def test_selection_matching_neither_team_raises():
    with pytest.raises(CandidateDirectionError):
        grade_leg(
            market_type="moneyline", selection="NOT_A_REAL_TEAM", point=None, home_team=_HOME, away_team=_AWAY,
            game_status="final", final_score=_final(27, 24),
        )


# --- product rollup ----------------------------------------------------------


def test_rollup_single_mirrors_the_one_leg():
    outcome, counts = rollup_product_outcome(recommendation_type="single", leg_outcomes=["WIN"])
    assert outcome == "WIN"
    assert counts is None


def test_rollup_multiple_singles_pending_while_any_leg_ungraded():
    outcome, counts = rollup_product_outcome(
        recommendation_type="multiple_singles", leg_outcomes=["WIN", "PENDING_MISSING_DATA", "LOSS"]
    )
    assert outcome == "PENDING_MISSING_DATA"
    assert counts is None


def test_rollup_multiple_singles_mixed_settled_preserves_every_leg():
    outcome, counts = rollup_product_outcome(
        recommendation_type="multiple_singles", leg_outcomes=["WIN", "WIN", "WIN", "LOSS"]
    )
    assert outcome == "MIXED_SETTLED"
    assert counts == {"WIN": 3, "LOSS": 1}


def test_grading_version_is_frozen_string():
    assert GRADING_VERSION == "v1"
