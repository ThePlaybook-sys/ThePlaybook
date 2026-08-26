"""Tests for app.persistence.postgame_grading (Milestone 5.4) -- the
create-or-correct-or-noop idempotency logic for leg/product grade
events, proven against a mocked PostgREST."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.postgame_grading import persist_leg_grade, persist_product_grade

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_persist_leg_grade_creates_when_no_existing_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(
        return_value=httpx.Response(201, json=[{"id": "grade-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        status, grade_id = await persist_leg_grade(
            client, _headers(), recommendation_leg_id="leg-1", game_id="game-1", grading_version="v1",
            outcome="WIN", authoritative_result={"final_score": {"home": 27, "away": 24}},
        )
    assert status == "created"
    assert grade_id == "grade-1"


@pytest.mark.asyncio
@respx.mock
async def test_persist_leg_grade_is_idempotent_on_retry():
    """A crashed-and-retried worker calling persist_leg_grade a second
    time with the SAME facts must not insert a second row."""
    existing = {"id": "grade-1", "outcome": "WIN", "authoritative_result": {"final_score": {"home": 27, "away": 24}}, "is_correction": False}
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=[existing]))
    post_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events")
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        status, grade_id = await persist_leg_grade(
            client, _headers(), recommendation_leg_id="leg-1", game_id="game-1", grading_version="v1",
            outcome="WIN", authoritative_result={"final_score": {"home": 27, "away": 24}},
        )
    assert status == "unchanged"
    assert grade_id == "grade-1"
    assert post_route.call_count == 0  # no insert attempted at all


@pytest.mark.asyncio
@respx.mock
async def test_persist_leg_grade_inserts_correction_when_facts_differ():
    """A stat correction landing after the original grade must produce a
    NEW append-only row referencing the one it supersedes -- never an
    UPDATE."""
    existing = {"id": "grade-1", "outcome": "WIN", "authoritative_result": {"final_score": {"home": 27, "away": 24}}, "is_correction": False}
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=[existing]))

    captured = {}

    def _post_responder(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[{"id": "grade-2"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(side_effect=_post_responder)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        status, grade_id = await persist_leg_grade(
            client, _headers(), recommendation_leg_id="leg-1", game_id="game-1", grading_version="v1",
            # Corrected final score flips the outcome to LOSS.
            outcome="LOSS", authoritative_result={"final_score": {"home": 24, "away": 27}},
        )
    assert status == "corrected"
    assert grade_id == "grade-2"
    assert captured["body"]["is_correction"] is True
    assert captured["body"]["corrects_grade_event_id"] == "grade-1"
    assert captured["body"]["correction_source"] == "stat_correction"


@pytest.mark.asyncio
@respx.mock
async def test_persist_leg_grade_recovers_from_race_lost_insert():
    """Two concurrent workers both see 'no existing row' and both try to
    insert the original -- the loser's insert 409s against the partial
    unique index; it must re-read and return the winner's row, never
    raise."""
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(
        side_effect=[
            httpx.Response(200, json=[]),  # first read: nothing yet
            httpx.Response(200, json=[{"id": "grade-winner", "outcome": "WIN", "authoritative_result": {}, "is_correction": False}]),
        ]
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(409, json={"code": "23505"}))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        status, grade_id = await persist_leg_grade(
            client, _headers(), recommendation_leg_id="leg-1", game_id="game-1", grading_version="v1",
            outcome="WIN", authoritative_result={},
        )
    assert status == "unchanged"
    assert grade_id == "grade-winner"


@pytest.mark.asyncio
@respx.mock
async def test_persist_product_grade_creates_and_is_idempotent():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(201, json=[{"id": "pgrade-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        status, grade_id = await persist_product_grade(
            client, _headers(), recommendation_product_id="prod-1", grading_version="v1",
            outcome="NOT_APPLICABLE", leg_outcome_counts=None, correction_source=None,
        )
    assert status == "created"
    assert grade_id == "pgrade-1"
