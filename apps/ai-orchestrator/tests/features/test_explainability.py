"""Tests for app.features.explainability (Milestone 5.2). Hand-computed
examples, not derived from the module under test."""
from __future__ import annotations

from app.features.explainability import (
    AgentContribution,
    ALWAYS_UNAVAILABLE_DISCLOSURE,
    build_biggest_risks,
    build_contributing_agents,
    build_data_limitations,
    build_strongest_evidence,
    build_why_not_other_shapes,
    build_why_selected,
    build_why_this_shape,
    contributing_agents_to_json,
    rejected_alternatives_to_json,
    select_would_change_mind_if,
)
from app.features.strategy import EvaluatedCandidate, RejectedCandidate, RejectionReason


def _candidate(**overrides) -> EvaluatedCandidate:
    defaults = dict(
        game_id="g1",
        recommendation_id="rec-1",
        consensus_snapshot_id="snap-1",
        candidate_key="g1:draftkings:moneyline:Home Team:none",
        market_type="moneyline",
        selection="Home Team",
        sportsbook="draftkings",
        american_odds=-110,
        point=None,
        decimal_odds=1.909,
        ev_per_dollar=0.05,
        final_aggregate_confidence=0.71,
    )
    defaults.update(overrides)
    return EvaluatedCandidate(**defaults)


def _agent_row(**overrides) -> dict:
    defaults = dict(
        agent_name="injury_intelligence_agent",
        directional_lean="home",
        confidence=0.6,
        evidence_classification="data_backed",
        weight_applied=1.0,
        would_change_mind_if="If the starting QB is ruled out.",
    )
    defaults.update(overrides)
    return defaults


# --- build_contributing_agents ---


def test_contributing_agents_includes_only_voting_agents():
    rows = [
        _agent_row(agent_name="a_support", directional_lean="home"),
        _agent_row(agent_name="b_oppose", directional_lean="away"),
        _agent_row(agent_name="c_no_opinion", directional_lean="none"),
    ]
    contributions = build_contributing_agents(rows, candidate_direction="home")
    names = {c.agent_name for c in contributions}
    assert names == {"a_support", "b_oppose"}
    supports_by_name = {c.agent_name: c.supports for c in contributions}
    assert supports_by_name == {"a_support": True, "b_oppose": False}


def test_contributing_agents_all_successful_participation_status():
    rows = [_agent_row()]
    contributions = build_contributing_agents(rows, candidate_direction="home")
    assert contributions[0].participation_status == "successful"


def test_contributing_agents_empty_for_prop_candidate_direction_none():
    rows = [_agent_row(directional_lean="home")]
    assert build_contributing_agents(rows, candidate_direction=None) == []


def test_contributing_agents_to_json_excludes_internal_supports_field():
    contributions = [
        AgentContribution(
            agent_name="a", weight_applied=1.0, confidence=0.6, directional_lean="home",
            evidence_classification="data_backed", participation_status="successful", supports=True,
        )
    ]
    json_rows = contributing_agents_to_json(contributions)
    assert json_rows == [{
        "agent_name": "a", "weight_applied": 1.0, "confidence": 0.6, "directional_lean": "home",
        "evidence_classification": "data_backed", "participation_status": "successful",
    }]
    assert "supports" not in json_rows[0]


# --- select_would_change_mind_if ---


def test_would_change_mind_if_quotes_highest_weighted_supporter_verbatim():
    rows = [
        _agent_row(agent_name="low_weight", directional_lean="home", weight_applied=0.5, would_change_mind_if="low weight reason"),
        _agent_row(agent_name="high_weight", directional_lean="home", weight_applied=1.5, would_change_mind_if="high weight reason"),
    ]
    assert select_would_change_mind_if(rows, candidate_direction="home") == "high weight reason"


def test_would_change_mind_if_none_when_no_supporting_agent():
    rows = [_agent_row(directional_lean="away")]
    assert select_would_change_mind_if(rows, candidate_direction="home") is None


def test_would_change_mind_if_never_uses_an_opposing_agent():
    rows = [_agent_row(agent_name="opposer", directional_lean="away", weight_applied=5.0, would_change_mind_if="should never appear")]
    assert select_would_change_mind_if(rows, candidate_direction="home") is None


# --- build_strongest_evidence ---


def test_strongest_evidence_names_top_supporters_by_weight():
    contributions = [
        AgentContribution("weak", 0.5, 0.5, "home", "data_backed", "successful", supports=True),
        AgentContribution("strong", 2.0, 0.9, "home", "data_backed", "successful", supports=True),
        AgentContribution("dissent", 1.0, 0.8, "away", "data_backed", "successful", supports=False),
    ]
    text = build_strongest_evidence(contributions)
    assert "strong" in text
    assert text.index("strong") < text.index("weak")
    assert "dissent" not in text


def test_strongest_evidence_degrades_honestly_when_no_supporters():
    assert "Insufficient" in build_strongest_evidence([])


# --- build_biggest_risks ---


def test_biggest_risks_always_discloses_historical_variance_unavailable():
    text = build_biggest_risks({"deterministic": {"bernoulli_outcome_variance": 0.24, "historical_bet_type_variance": None}})
    assert "0.2400" in text
    assert "Historical bet-type variance data is not yet available" in text


def test_biggest_risks_degrades_honestly_when_risk_manager_unavailable():
    text = build_biggest_risks(None)
    assert "unavailable for this candidate this cycle" in text
    assert "Historical bet-type variance data is not yet available" in text


# --- build_why_selected ---


def test_why_selected_reports_gates_always():
    candidate = _candidate(ev_per_dollar=0.0721, final_aggregate_confidence=0.6432)
    text = build_why_selected(candidate, rank_position=1, total_qualifying=1, beat_same_market_conflict=False)
    assert "0.6432" in text
    assert "0.0721" in text
    assert "ranked" not in text
    assert "opposing side" not in text


def test_why_selected_reports_ranking_when_multiple_qualifying():
    candidate = _candidate()
    text = build_why_selected(candidate, rank_position=2, total_qualifying=5, beat_same_market_conflict=False)
    assert "ranked #2 of 5" in text


def test_why_selected_reports_conflict_win():
    candidate = _candidate()
    text = build_why_selected(candidate, rank_position=1, total_qualifying=1, beat_same_market_conflict=True)
    assert "opposing side of the same market" in text


# --- build_why_this_shape / build_why_not_other_shapes ---


def test_why_this_shape_single():
    assert "single recommendation" in build_why_this_shape("single")


def test_why_this_shape_multiple_singles_includes_leg_count():
    assert "3 independent candidates" in build_why_this_shape("multiple_singles", leg_count=3)


def test_why_this_shape_no_bet():
    assert "No candidate evaluated for this game" in build_why_this_shape("no_bet")


def test_why_this_shape_bankroll_preservation_includes_game_count():
    text = build_why_this_shape("bankroll_preservation", game_count=7)
    assert "7 games" in text


def test_why_not_other_shapes_none_for_no_bet_and_bankroll_preservation():
    assert build_why_not_other_shapes("no_bet") is None
    assert build_why_not_other_shapes("bankroll_preservation") is None


def test_why_not_other_shapes_mentions_inactive_parlays():
    assert "not currently active" in build_why_not_other_shapes("single")
    assert "inactive" in build_why_not_other_shapes("multiple_singles")


# --- build_data_limitations ---


def test_data_limitations_always_includes_unconditional_disclosure():
    assert build_data_limitations(None) == ALWAYS_UNAVAILABLE_DISCLOSURE


def test_data_limitations_reports_incomplete_committee():
    participation = {
        "configured_agents": ["a", "b", "c"],
        "built_agents": ["a", "b"],
        "deferred_agents": ["c"],
        "failed_agents": [],
    }
    text = build_data_limitations(participation)
    assert "2 of 3 configured committee agents" in text
    assert "missing: c" in text


def test_data_limitations_no_extra_text_when_committee_complete():
    participation = {"configured_agents": ["a"], "built_agents": ["a"], "deferred_agents": [], "failed_agents": []}
    assert build_data_limitations(participation) == ALWAYS_UNAVAILABLE_DISCLOSURE


# --- rejected_alternatives_to_json ---


def test_rejected_alternatives_to_json_shape():
    candidate = _candidate(candidate_key="ck", market_type="total", selection="Over")
    rejected = [RejectedCandidate(candidate=candidate, reasons=(RejectionReason.NON_POSITIVE_EV,))]
    assert rejected_alternatives_to_json(rejected) == [
        {"candidate_key": "ck", "market_type": "total", "selection": "Over", "reasons": ["NON_POSITIVE_EV"]}
    ]
