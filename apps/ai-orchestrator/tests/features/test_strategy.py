"""Tests for app.features.strategy (Milestone 5.1, Decisions X/Y/Z/AA/AB/
AC/AM/AN). Hand-computed examples, not derived from the module under test."""
from __future__ import annotations

from app.features.strategy import (
    EvaluatedCandidate,
    GameCandidates,
    compute_strategy_decision,
    qualifies,
    rank_key,
    resolve_market_conflicts,
)


def _candidate(
    *,
    game_id: str = "game-1",
    recommendation_id: str = "rec-1",
    consensus_snapshot_id: str = "snap-1",
    candidate_key: str = "cand-1",
    market_type: str = "moneyline",
    selection: str = "Home Team",
    sportsbook: str = "draftkings",
    american_odds: int = -110,
    point: float | None = None,
    decimal_odds: float = 1.909,
    ev_per_dollar: float = 0.05,
    final_aggregate_confidence: float = 0.71,
) -> EvaluatedCandidate:
    return EvaluatedCandidate(
        game_id=game_id,
        recommendation_id=recommendation_id,
        consensus_snapshot_id=consensus_snapshot_id,
        candidate_key=candidate_key,
        market_type=market_type,
        selection=selection,
        sportsbook=sportsbook,
        american_odds=american_odds,
        point=point,
        decimal_odds=decimal_odds,
        ev_per_dollar=ev_per_dollar,
        final_aggregate_confidence=final_aggregate_confidence,
    )


# --- qualifies: Decision X, both gates required ---


def test_qualifies_when_both_gates_pass():
    assert qualifies(_candidate(ev_per_dollar=0.01, final_aggregate_confidence=0.55)) is True


def test_does_not_qualify_below_confidence_floor():
    assert qualifies(_candidate(ev_per_dollar=0.10, final_aggregate_confidence=0.5499)) is False


def test_does_not_qualify_zero_ev():
    assert qualifies(_candidate(ev_per_dollar=0.0, final_aggregate_confidence=0.90)) is False


def test_does_not_qualify_negative_ev_even_with_high_confidence():
    assert qualifies(_candidate(ev_per_dollar=-0.01, final_aggregate_confidence=0.99)) is False


def test_confidence_exactly_at_floor_qualifies():
    assert qualifies(_candidate(ev_per_dollar=0.01, final_aggregate_confidence=0.55)) is True


# --- rank_key: Decision AM's exact hierarchy ---


def test_rank_key_orders_by_ev_first():
    high_ev = _candidate(candidate_key="z", ev_per_dollar=0.10, final_aggregate_confidence=0.60)
    low_ev = _candidate(candidate_key="a", ev_per_dollar=0.05, final_aggregate_confidence=0.99)
    assert sorted([low_ev, high_ev], key=rank_key) == [high_ev, low_ev]


def test_rank_key_breaks_ev_ties_by_confidence():
    high_conf = _candidate(candidate_key="z", ev_per_dollar=0.05, final_aggregate_confidence=0.80)
    low_conf = _candidate(candidate_key="a", ev_per_dollar=0.05, final_aggregate_confidence=0.60)
    assert sorted([low_conf, high_conf], key=rank_key) == [high_conf, low_conf]


def test_rank_key_breaks_full_ties_by_candidate_key_ascending():
    b = _candidate(candidate_key="b", ev_per_dollar=0.05, final_aggregate_confidence=0.60)
    a = _candidate(candidate_key="a", ev_per_dollar=0.05, final_aggregate_confidence=0.60)
    assert sorted([b, a], key=rank_key) == [a, b]


# --- resolve_market_conflicts: Decision AC ---


def test_opposing_moneyline_sides_keep_only_the_better_ranked_one():
    home = _candidate(candidate_key="home-ml", selection="Home Team", ev_per_dollar=0.08, final_aggregate_confidence=0.60)
    away = _candidate(candidate_key="away-ml", selection="Away Team", ev_per_dollar=0.03, final_aggregate_confidence=0.90)
    resolved = resolve_market_conflicts([home, away])
    assert resolved == [home]


def test_different_markets_on_same_game_both_survive():
    ml = _candidate(candidate_key="ml", market_type="moneyline")
    total = _candidate(candidate_key="total", market_type="total", selection="Over")
    resolved = resolve_market_conflicts([ml, total])
    assert set(resolved) == {ml, total}


def test_multiple_props_never_conflict_with_each_other():
    prop_a = _candidate(candidate_key="prop-a", market_type="prop", selection="Mahomes Over 1.5 TDs")
    prop_b = _candidate(candidate_key="prop-b", market_type="prop", selection="Kelce Over 65.5 Yds")
    resolved = resolve_market_conflicts([prop_a, prop_b])
    assert set(resolved) == {prop_a, prop_b}


# --- compute_strategy_decision: the full decision tree ---


def test_zero_games_considered_is_bankroll_preservation():
    result = compute_strategy_decision([])
    assert result.outcome == "bankroll_preservation"
    assert result.legs == ()


def test_all_games_no_bet_is_slate_wide_bankroll_preservation():
    games = [
        GameCandidates(game_id="g1", recommendation_id="r1", candidates=(_candidate(game_id="g1", final_aggregate_confidence=0.40),)),
        GameCandidates(game_id="g2", recommendation_id="r2", candidates=()),
    ]
    result = compute_strategy_decision(games)
    assert result.outcome == "bankroll_preservation"
    assert result.legs == ()
    assert {d.game_id: d.outcome for d in result.game_decisions} == {"g1": "no_bet", "g2": "no_bet"}


def test_exactly_one_qualifying_candidate_in_slate_is_single():
    games = [
        GameCandidates(game_id="g1", recommendation_id="r1", candidates=(_candidate(game_id="g1", candidate_key="only"),)),
        GameCandidates(game_id="g2", recommendation_id="r2", candidates=(_candidate(game_id="g2", final_aggregate_confidence=0.10),)),
    ]
    result = compute_strategy_decision(games)
    assert result.outcome == "single"
    assert [c.candidate_key for c in result.legs] == ["only"]
    decisions = {d.game_id: d.outcome for d in result.game_decisions}
    assert decisions == {"g1": "qualified", "g2": "no_bet"}


def test_two_qualifying_candidates_across_games_is_multiple_singles_ranked_by_ev():
    weaker = _candidate(game_id="g1", recommendation_id="r1", candidate_key="weak", ev_per_dollar=0.02, final_aggregate_confidence=0.60)
    stronger = _candidate(game_id="g2", recommendation_id="r2", candidate_key="strong", ev_per_dollar=0.09, final_aggregate_confidence=0.60)
    games = [
        GameCandidates(game_id="g1", recommendation_id="r1", candidates=(weaker,)),
        GameCandidates(game_id="g2", recommendation_id="r2", candidates=(stronger,)),
    ]
    result = compute_strategy_decision(games)
    assert result.outcome == "multiple_singles"
    assert [c.candidate_key for c in result.legs] == ["strong", "weak"]


def test_one_game_contributing_two_legs_from_different_markets_is_multiple_singles():
    ml = _candidate(game_id="g1", recommendation_id="r1", candidate_key="ml", market_type="moneyline")
    total = _candidate(game_id="g1", recommendation_id="r1", candidate_key="total", market_type="total", selection="Over")
    games = [GameCandidates(game_id="g1", recommendation_id="r1", candidates=(ml, total))]
    result = compute_strategy_decision(games)
    assert result.outcome == "multiple_singles"
    assert {c.candidate_key for c in result.legs} == {"ml", "total"}
    assert len(result.game_decisions) == 1
    assert result.game_decisions[0].outcome == "qualified"


def test_omitted_non_qualifying_candidates_do_not_appear_as_legs():
    qualifying = _candidate(candidate_key="q", ev_per_dollar=0.05, final_aggregate_confidence=0.60)
    non_qualifying = _candidate(candidate_key="nq", market_type="total", selection="Over", ev_per_dollar=-0.01, final_aggregate_confidence=0.90)
    games = [GameCandidates(game_id="g1", recommendation_id="r1", candidates=(qualifying, non_qualifying))]
    result = compute_strategy_decision(games)
    assert result.outcome == "single"
    assert [c.candidate_key for c in result.legs] == ["q"]
