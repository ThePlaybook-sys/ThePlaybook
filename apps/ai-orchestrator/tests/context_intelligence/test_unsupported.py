"""Tests for app.context_intelligence.unsupported (Phase 8.1 Foundation
Pass) -- the fixed insufficient-evidence stubs for every real gap Phase
8.0.5's closeout audit confirmed."""
from __future__ import annotations

import pytest

from app.context_intelligence.unsupported import UNSUPPORTED_DIMENSIONS, insufficient_evidence_result

_EXPECTED_DIMENSIONS = {
    "player_performance",
    "injuries",
    "roster_role",
    "team_performance",
    "depth_lineup",
    "game_state_pbp",
}


def test_covers_exactly_the_six_named_unsupported_dimensions():
    assert set(UNSUPPORTED_DIMENSIONS.keys()) == _EXPECTED_DIMENSIONS


@pytest.mark.parametrize("dimension", sorted(_EXPECTED_DIMENSIONS))
def test_every_dimension_is_explicit_insufficient_evidence(dimension):
    result = insufficient_evidence_result(dimension)
    assert result.dimension == dimension
    assert result.insufficient_evidence is True
    assert result.sample_size == 0
    assert result.similarity_score is None
    assert result.recency_weighting is None
    assert result.confidence is None
    assert result.context_dimensions_used == ()
    assert result.provenance == ()
    assert result.facts == {}
    assert result.insufficient_evidence_reason is not None
    assert len(result.confounders) >= 1


def test_unknown_dimension_raises_rather_than_inventing_a_reason():
    with pytest.raises(KeyError):
        insufficient_evidence_result("not_a_real_dimension")


def test_injuries_reason_names_the_real_blocker_not_a_generic_gap():
    result = insufficient_evidence_result("injuries")
    assert "BALLDONTLIE" in result.insufficient_evidence_reason
    assert "unpaid" in result.insufficient_evidence_reason or "entitlement" in result.insufficient_evidence_reason
