"""Milestone 5.5 persistence for `adaptive_weight_proposals`/
`adaptive_weight_proposal_observations` (Decisions 1-27).

**Idempotent-retry vs. legitimate-correction (Decision 22), the exact
same DB-read-then-decide pattern `app.persistence.postgame_grading`
already established for grading:** `persist_proposal` reads the latest
existing row for `(agent_id, evaluation_window_start,
evaluation_window_end, weighting_version)`, compares its
`(sample_size, roi, status)` signature to what was just computed, and
only then decides: no existing row -> insert; identical signature ->
no-op (`"unchanged"`, a crashed-and-retried worker lands here); a
different signature (e.g. a Milestone 5.4 grade correction changed the
underlying evidence) -> a correction insert referencing the row it
supersedes. The partial unique index is the actual race-condition
backstop, exactly like the grading tables."""
from __future__ import annotations

import httpx


class AdaptiveWeightingPersistenceError(Exception):
    """Raised when an adaptive-weighting read/write fails on Supabase's
    side for a reason other than the expected unique-constraint race."""


async def read_all_agents(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    """Every row in `agents` -- Milestone 5.5 evaluates the whole
    committee every cycle (Decision 14's "preserve the fact rather than
    silently drop" extended to non-voting agents too, see
    `app.features.adaptive_weighting`'s own module docstring)."""
    response = await client.get("/rest/v1/agents", params={"select": "id,name,category,current_weight"}, headers=headers)
    if response.status_code != 200:
        raise AdaptiveWeightingPersistenceError(f"failed to read agents: {response.status_code} {response.text}")
    return response.json()


async def read_latest_leg_grade_events(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    """Every `recommendation_leg_grade_events` row, ordered so the
    caller can reduce to the latest (original-or-correction) row per
    `recommendation_leg_id` in Python -- PostgREST has no "latest per
    group" query. Unbounded scan, matching Milestone 5.4's own accepted
    MVP scope limitation for its bankroll_preservation sweep (flagged in
    the Milestone 5.5 completion report, not hidden)."""
    response = await client.get(
        "/rest/v1/recommendation_leg_grade_events",
        params={"select": "id,recommendation_leg_id,game_id,outcome,created_at", "order": "recommendation_leg_id.asc,created_at.asc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise AdaptiveWeightingPersistenceError(f"failed to read leg grade events: {response.status_code} {response.text}")
    return response.json()


async def read_recommendation_legs_by_ids(client: httpx.AsyncClient, headers: dict, *, leg_ids: list[str]) -> list[dict]:
    if not leg_ids:
        return []
    response = await client.get(
        "/rest/v1/recommendation_legs",
        params={"id": f"in.({','.join(leg_ids)})", "select": "id,market_type,selection,point,decimal_odds,game_id,recommendation_id"},
        headers=headers,
    )
    if response.status_code != 200:
        raise AdaptiveWeightingPersistenceError(f"failed to read recommendation_legs by ids: {response.status_code} {response.text}")
    return response.json()


async def read_latest_proposal(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    agent_id: str,
    evaluation_window_start: str,
    evaluation_window_end: str,
    weighting_version: str,
) -> dict | None:
    response = await client.get(
        "/rest/v1/adaptive_weight_proposals",
        params={
            "agent_id": f"eq.{agent_id}",
            "evaluation_window_start": f"eq.{evaluation_window_start}",
            "evaluation_window_end": f"eq.{evaluation_window_end}",
            "weighting_version": f"eq.{weighting_version}",
            "select": "id,sample_size,roi,status",
            "order": "created_at.desc",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise AdaptiveWeightingPersistenceError(
            f"failed to read latest proposal for agent_id={agent_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def persist_proposal(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    agent_id: str,
    previous_weight: float,
    raw_proposed_weight: float | None,
    guardrail_adjusted_proposed_weight: float | None,
    evaluation_window_start: str,
    evaluation_window_end: str,
    sample_size: int,
    roi: float | None,
    committee_average_roi: float | None,
    performance_delta: float | None,
    learning_rate: float,
    weighting_version: str,
    status: str,
    rejection_reason: str | None,
) -> tuple[str, str]:
    """Create-or-correct-or-noop for one agent's evaluation (Decision 22).
    Returns `(result_status, proposal_id)` where `result_status` is
    `"created"`, `"unchanged"`, or `"corrected"`. `applied_weight` is
    never set here -- always `NULL` (Decision 2/15: V1 never promotes a
    proposal into `agents.current_weight`)."""
    existing = await read_latest_proposal(
        client, headers, agent_id=agent_id, evaluation_window_start=evaluation_window_start,
        evaluation_window_end=evaluation_window_end, weighting_version=weighting_version,
    )
    if existing is not None and existing["sample_size"] == sample_size and existing["roi"] == roi and existing["status"] == status:
        return "unchanged", existing["id"]

    is_correction = existing is not None
    payload = {
        "agent_id": agent_id,
        "previous_weight": previous_weight,
        "raw_proposed_weight": raw_proposed_weight,
        "guardrail_adjusted_proposed_weight": guardrail_adjusted_proposed_weight,
        "applied_weight": None,
        "evaluation_window_start": evaluation_window_start,
        "evaluation_window_end": evaluation_window_end,
        "sample_size": sample_size,
        "roi": roi,
        "committee_average_roi": committee_average_roi,
        "performance_delta": performance_delta,
        "learning_rate": learning_rate,
        "weighting_version": weighting_version,
        "status": status,
        "rejection_reason": rejection_reason,
        "is_correction": is_correction,
        "corrects_proposal_id": existing["id"] if is_correction else None,
    }
    response = await client.post(
        "/rest/v1/adaptive_weight_proposals",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code == 409 and not is_correction:
        winner = await read_latest_proposal(
            client, headers, agent_id=agent_id, evaluation_window_start=evaluation_window_start,
            evaluation_window_end=evaluation_window_end, weighting_version=weighting_version,
        )
        if winner is not None:
            return "unchanged", winner["id"]
    if response.status_code not in (200, 201):
        raise AdaptiveWeightingPersistenceError(
            f"failed to persist proposal for agent_id={agent_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise AdaptiveWeightingPersistenceError(f"proposal insert for agent_id={agent_id!r} returned no row")
    return ("corrected" if is_correction else "created"), rows[0]["id"]


async def persist_proposal_observation(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    proposal_id: str,
    recommendation_leg_grade_event_id: str,
    classification: str,
    directional_lean: str,
    notional_pnl: float,
) -> str:
    payload = {
        "proposal_id": proposal_id,
        "recommendation_leg_grade_event_id": recommendation_leg_grade_event_id,
        "classification": classification,
        "directional_lean": directional_lean,
        "notional_pnl": notional_pnl,
    }
    response = await client.post(
        "/rest/v1/adaptive_weight_proposal_observations",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code == 409:
        # Already recorded for this (proposal, leg_grade_event) pair --
        # a retried worker re-deriving identical evidence for an
        # already-"unchanged" proposal. Not an error.
        existing = await client.get(
            "/rest/v1/adaptive_weight_proposal_observations",
            params={
                "proposal_id": f"eq.{proposal_id}",
                "recommendation_leg_grade_event_id": f"eq.{recommendation_leg_grade_event_id}",
                "select": "id",
                "limit": "1",
            },
            headers=headers,
        )
        rows = existing.json() if existing.status_code == 200 else []
        if rows:
            return rows[0]["id"]
    if response.status_code not in (200, 201):
        raise AdaptiveWeightingPersistenceError(
            f"failed to persist proposal observation for proposal_id={proposal_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise AdaptiveWeightingPersistenceError(f"proposal observation insert for proposal_id={proposal_id!r} returned no row")
    return rows[0]["id"]
