"""HQ "EMPTY NO-BET SAFETY FIX" (2026-09-20) — worker-side half.

Two things are held here:

1. **The relay** must never hand a failed game's empty candidate list to the
   Strategy Engine, because `compute_strategy_decision` turns an empty list
   into `no_bet` and cannot tell failure from "nothing qualified".
2. **The census** must be able to see candidate-level failures at all. Before
   this fix it scanned only top-level collections, and candidates live at
   `games[].response.candidates[]` — two levels down.
"""
from __future__ import annotations

from app.cron_dispatch import _FAILURE_STATUSES, _NESTED_RESULT_KEYS, _nested_failure_census
from app.recommendation_worker import _NON_STRATEGY_GAME_STATUSES


# -------------------------------------------------------------------- relay
def test_analysis_incomplete_is_withheld_from_strategy():
    """The core guarantee. A game whose analysis produced nothing must not
    reach the Strategy Engine, or it becomes an ACTIVE No Bet."""
    assert "analysis_incomplete" in _NON_STRATEGY_GAME_STATUSES


def test_already_computed_is_still_withheld():
    """The pre-existing rule must survive the change — it contributed its
    strategy input in an earlier cycle."""
    assert "skipped_already_computed" in _NON_STRATEGY_GAME_STATUSES


def test_normal_computed_game_still_reaches_strategy():
    """A healthy game must NOT be withheld — otherwise the fix would block
    every legitimate recommendation and No Bet."""
    assert "computed" not in _NON_STRATEGY_GAME_STATUSES
    assert None not in _NON_STRATEGY_GAME_STATUSES


# ------------------------------------------------------------------- census
def test_candidates_is_a_scanned_collection():
    assert "candidates" in _NESTED_RESULT_KEYS


def test_analysis_incomplete_counts_as_failure():
    assert "analysis_incomplete" in _FAILURE_STATUSES
    assert "failed" in _FAILURE_STATUSES
    assert "evaluated" not in _FAILURE_STATUSES


def test_census_descends_into_nested_candidates():
    """The shape the Recommendation Worker actually returns. Before the fix
    this scanned clean and the run reported success."""
    result = {
        "status": "completed",
        "games": [
            {
                "game_id": "g1",
                "response": {
                    "status": "analysis_incomplete",
                    "candidates": [
                        {"status": "analysis_incomplete"},
                        {"status": "analysis_incomplete"},
                    ],
                },
            }
        ],
    }
    census = _nested_failure_census(result)
    assert census is not None
    failed, total, sample = census
    assert failed == 2
    assert "analysis_incomplete" in sample


def test_census_stays_silent_on_a_genuinely_healthy_run():
    """A real No Bet — analysis completed, candidates evaluated, none
    qualified — must remain silent. If this fires, every clean cycle becomes
    a Sentry event and the alert stops meaning anything."""
    result = {
        "status": "completed",
        "games": [
            {
                "game_id": "g1",
                "response": {
                    "status": "computed",
                    "candidates": [{"status": "evaluated"}, {"status": "evaluated"}],
                },
            }
        ],
    }
    assert _nested_failure_census(result) is None


def test_partial_candidate_failure_surfaces_without_hiding_the_survivor():
    """HQ STATE 4: one candidate fails, another survives. The survivor keeps
    the game valid; the failure is still counted and visible."""
    result = {
        "games": [
            {
                "game_id": "g1",
                "response": {
                    "status": "computed",
                    "candidates": [
                        {"status": "evaluated"},
                        {"status": "analysis_incomplete"},
                    ],
                },
            }
        ]
    }
    census = _nested_failure_census(result)
    assert census is not None
    failed, total, _ = census
    assert (failed, total) == (1, 3)  # 1 game entry + 2 candidate entries scanned


def test_top_level_collections_still_scanned():
    """Regression: the original flat behaviour must not be lost to the
    descent."""
    result = {"legs": [{"status": "failed", "error": "boom"}]}
    census = _nested_failure_census(result)
    assert census is not None
    assert census[0] == 1
    assert census[2] == "boom"
