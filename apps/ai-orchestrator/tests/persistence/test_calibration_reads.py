"""Tests for `app.persistence.calibration_reads` (Phase 8 Probability Calibration
Ledger, 2026-09-15) -- the join from frozen prediction to authoritative grade.

All Supabase reads are respx-mocked. Dev currently holds ZERO real settled
predictions (0 recommendation_legs, 0 grade events, live-verified), so these
prove the join contract for when real rows exist."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.calibration_reads import CalibrationReadError, read_settled_predictions

SUPABASE_URL = "https://test-project.supabase.co"
AGENT_ID = "a-prob-1"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _leg(**overrides) -> dict:
    base = {
        "id": "leg-1", "recommendation_id": "rec-1", "candidate_key": "g1:DraftKings:moneyline:KC:none",
        "game_id": "game-1", "market_type": "moneyline", "selection": "Kansas City Chiefs",
        "sportsbook": "DraftKings", "american_odds": -125, "point": None,
        "created_at": "2026-09-15T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def _probability_output_row(*, modeled_probability=0.57, context_provenance=None, **overrides) -> dict:
    raw_output = {
        "probability_output": {
            "agent_name": "probability_modeling_agent", "candidate_key": "g1:DraftKings:moneyline:KC:none",
            "selection": "Kansas City Chiefs", "modeled_probability": modeled_probability,
            "confidence_in_probability": 0.72, "reasoning": "r", "supporting_evidence": [],
            "would_change_mind_if": "x",
        }
    }
    if context_provenance is not None:
        raw_output["context_provenance"] = context_provenance
    base = {
        "id": "out-1", "raw_output": raw_output, "prompt_name": "probability_modeling_agent",
        "prompt_version": 3, "model_name": "claude-opus-5", "provider": "anthropic",
        "created_at": "2026-09-15T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def _grade(**overrides) -> dict:
    base = {
        "id": "ge-1", "outcome": "WIN", "graded_at": "2026-09-16T00:00:00+00:00", "grading_version": "v1",
        "is_correction": False, "corrects_grade_event_id": None,
    }
    base.update(overrides)
    return base


def _mock(*, legs, outputs, grades, scheduled_start="2026-09-15T17:00:00+00:00"):
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=legs))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": leg["game_id"], "scheduled_start": scheduled_start} for leg in legs])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": AGENT_ID}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=outputs))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=grades))


@pytest.mark.asyncio
@respx.mock
async def test_joins_frozen_prediction_to_authoritative_grade():
    _mock(legs=[_leg()], outputs=[_probability_output_row()], grades=[_grade()])

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        predictions = await read_settled_predictions(client, _headers())

    assert len(predictions) == 1
    prediction = predictions[0]
    # Frozen prediction side -- read, never recomputed.
    assert prediction.modeled_probability == 0.57
    assert prediction.confidence_in_probability == 0.72
    assert prediction.prompt_version == 3
    assert prediction.model_name == "claude-opus-5" and prediction.provider == "anthropic"
    assert prediction.predicted_at == "2026-09-15T00:00:00+00:00"
    # Frozen bet side.
    assert prediction.candidate_key == "g1:DraftKings:moneyline:KC:none"
    assert prediction.american_odds == -125
    # Book break-even derived deterministically from the frozen price: 125/225.
    assert prediction.sportsbook_implied_probability == pytest.approx(125 / 225)
    # Authoritative outcome side.
    assert prediction.outcome == "WIN"
    assert prediction.graded_at == "2026-09-16T00:00:00+00:00"
    assert prediction.grade_event_id == "ge-1"


@pytest.mark.asyncio
@respx.mock
async def test_empty_ledger_when_no_legs_exist():
    """Dev's real state today -- must return an empty list, never an error."""
    _mock(legs=[], outputs=[], grades=[])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        assert await read_settled_predictions(client, _headers()) == []


@pytest.mark.asyncio
@respx.mock
async def test_pending_grade_is_not_a_settled_prediction():
    """An unresolved bet must never enter the ledger."""
    _mock(legs=[_leg()], outputs=[_probability_output_row()], grades=[_grade(outcome="PENDING_MISSING_DATA")])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        assert await read_settled_predictions(client, _headers()) == []


@pytest.mark.asyncio
@respx.mock
async def test_leg_without_a_probability_prediction_is_skipped():
    _mock(legs=[_leg()], outputs=[], grades=[_grade()])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        assert await read_settled_predictions(client, _headers()) == []


@pytest.mark.asyncio
@respx.mock
async def test_ungraded_leg_is_skipped_so_unsupported_markets_stay_unsupported():
    """A market this codebase cannot grade produces no grade event, so it simply
    never becomes a settled prediction -- no prop grading is invented here."""
    _mock(legs=[_leg(market_type="prop", selection="Jaxon Smith-Njigba Over 65.5")], outputs=[_probability_output_row()], grades=[])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        assert await read_settled_predictions(client, _headers()) == []


@pytest.mark.asyncio
@respx.mock
async def test_correction_is_the_authoritative_grade_and_stays_visible():
    """A corrected grade is a NEW row superseding the old one. The ledger must
    take the correction as authoritative AND carry the correction chain forward
    rather than flattening it into an ordinary grade."""
    correction = _grade(id="ge-2", outcome="LOSS", is_correction=True, corrects_grade_event_id="ge-1")
    _mock(legs=[_leg()], outputs=[_probability_output_row()], grades=[correction])

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        predictions = await read_settled_predictions(client, _headers())

    assert len(predictions) == 1
    assert predictions[0].outcome == "LOSS"  # the correction wins, not the original
    assert predictions[0].grade_is_correction is True
    assert predictions[0].corrects_grade_event_id == "ge-1"


@pytest.mark.asyncio
@respx.mock
async def test_context_provenance_travels_forward_when_captured():
    provenance = {
        "target_event_timestamp": "2026-09-15T10:30:00+00:00",
        "dimensions": {"market": {"completeness": "joined", "sample_size": 6}},
    }
    _mock(legs=[_leg()], outputs=[_probability_output_row(context_provenance=provenance)], grades=[_grade()])

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        predictions = await read_settled_predictions(client, _headers())

    assert predictions[0].context_provenance == provenance


@pytest.mark.asyncio
@respx.mock
async def test_prediction_made_before_provenance_capture_is_honestly_none():
    """Never backfilled, never fabricated -- an older row simply has None."""
    _mock(legs=[_leg()], outputs=[_probability_output_row()], grades=[_grade()])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        predictions = await read_settled_predictions(client, _headers())
    assert predictions[0].context_provenance is None


@pytest.mark.asyncio
@respx.mock
async def test_missing_probability_agent_row_fails_loud():
    """Silently returning an empty ledger here would look identical to "no bets
    have settled yet" -- a configuration gap must not masquerade as data."""
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=[_leg()]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "game-1", "scheduled_start": "2026-09-15T17:00:00+00:00"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(CalibrationReadError, match="probability_modeling_agent"):
            await read_settled_predictions(client, _headers())


@pytest.mark.asyncio
@respx.mock
async def test_read_failure_raises_rather_than_returning_a_partial_ledger():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(CalibrationReadError):
            await read_settled_predictions(client, _headers())


# --------------------------------------------------------------------------
# Forward-looking timing contract plumbing (2026-09-15).
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_scheduled_start_is_read_and_makes_a_pre_kickoff_prediction_eligible():
    _mock(
        legs=[_leg()],
        outputs=[_probability_output_row(created_at="2026-09-15T12:00:00+00:00")],
        grades=[_grade()],
        scheduled_start="2026-09-15T17:00:00+00:00",
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        predictions = await read_settled_predictions(client, _headers())

    assert predictions[0].scheduled_start == "2026-09-15T17:00:00+00:00"
    assert predictions[0].predicted_before_kickoff is True
    assert predictions[0].is_scoreable is True


@pytest.mark.asyncio
@respx.mock
async def test_post_event_prediction_is_returned_not_filtered_away():
    """Filtering it at read time would hide a process problem. It must come back
    with the kickoff time that disqualifies it and an explicit reason."""
    _mock(
        legs=[_leg()],
        outputs=[_probability_output_row(created_at="2026-09-16T03:00:00+00:00")],
        grades=[_grade()],
        scheduled_start="2026-09-15T17:00:00+00:00",
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        predictions = await read_settled_predictions(client, _headers())

    assert len(predictions) == 1  # retained
    assert predictions[0].is_scoreable is False
    assert predictions[0].calibration_exclusion_reason == "predicted_at_not_before_scheduled_start"


@pytest.mark.asyncio
@respx.mock
async def test_game_without_scheduled_start_yields_none_not_a_silent_pass():
    _mock(legs=[_leg()], outputs=[_probability_output_row()], grades=[_grade()], scheduled_start=None)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        predictions = await read_settled_predictions(client, _headers())

    assert predictions[0].scheduled_start is None
    assert predictions[0].calibration_exclusion_reason == "missing_event_scheduled_start"
