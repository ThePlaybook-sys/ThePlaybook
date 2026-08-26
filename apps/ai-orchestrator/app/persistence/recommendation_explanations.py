"""Recommendation-explanation persistence (Milestone 5.2). Writes the new
`recommendation_product_explanations`/`recommendation_leg_explanations`
tables (Schema Option A, approved 2026-08-25) and reads back the Phase 4
rows Explainability needs that Milestone 5.1 never had to read (this
module is the FIRST reader of a candidate-level `recommendation_agent_outputs`
row and of `consensus_snapshots.participation_metadata` by
`recommendation_id` alone).

**`explainability_payloads` (Phase 1, Volume 3 §5) is never touched by
this module** -- Schema Option A leaves it completely untouched, legacy,
its existing row unmigrated. Nothing here reads or writes it.

Both new tables are append-only (DB-enforced full-block UPDATE triggers)
-- this module only ever INSERTs, never UPDATEs either one.
"""
from __future__ import annotations

import httpx


class RecommendationExplanationsError(Exception):
    """Raised when a recommendation-explanation read/write fails on
    Supabase's side."""


async def read_candidate_level_agent_output(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_id: str,
    candidate_key: str,
    agent_name: str,
) -> dict | None:
    """Reads back ONE candidate-level `recommendation_agent_outputs` row's
    `raw_output` for a specific agent -- Phase 4 only ever wrote this
    shape (Milestone 4.6/4.9), nothing has read it back until now. Returns
    `None` when that agent has no row for this candidate this cycle
    (failed, deferred, or never attempted) -- never fabricated. No
    uniqueness constraint exists upstream (Decision G) so multiple rows
    could theoretically exist; the most recently persisted one is used
    (matches Postgres's natural insertion order with no explicit ORDER BY
    override needed at this table's expected size per candidate)."""
    response = await client.get(
        "/rest/v1/recommendation_agent_outputs",
        params={
            "recommendation_id": f"eq.{recommendation_id}",
            "candidate_key": f"eq.{candidate_key}",
            "select": "raw_output,agents(name)",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise RecommendationExplanationsError(
            f"failed to read candidate-level agent output for recommendation_id={recommendation_id!r} "
            f"candidate_key={candidate_key!r} agent_name={agent_name!r}: {response.status_code} {response.text}"
        )
    rows = [row for row in response.json() if (row.get("agents") or {}).get("name") == agent_name]
    if not rows:
        return None
    return rows[-1]["raw_output"]


async def read_legs_for_product(
    client: httpx.AsyncClient, headers: dict, *, recommendation_product_id: str
) -> list[dict]:
    """Reads back the `id`/`candidate_key` of every `recommendation_legs`
    row already written for one `recommendation_products` row --
    Milestone 5.1's `persist_strategy_decision` creates legs but discards
    their ids immediately after insert, so this is how the Explainability
    orchestration layer (`app.orchestration.explainability`) discovers
    which `recommendation_leg_id` corresponds to which already-computed
    `app.features.strategy.EvaluatedCandidate` (matched by `candidate_key`),
    without requiring any change to the frozen Milestone 5.1 persistence
    module."""
    response = await client.get(
        "/rest/v1/recommendation_legs",
        params={"recommendation_product_id": f"eq.{recommendation_product_id}", "select": "id,candidate_key"},
        headers=headers,
    )
    if response.status_code != 200:
        raise RecommendationExplanationsError(
            f"failed to read legs for recommendation_product_id={recommendation_product_id!r}: "
            f"{response.status_code} {response.text}"
        )
    return response.json()


async def read_participation_metadata(
    client: httpx.AsyncClient, headers: dict, *, recommendation_id: str
) -> dict | None:
    """Reads `participation_metadata` from any one `consensus_snapshots`
    row for this `recommendation_id` -- committee completeness reflects
    the SHARED game-level fan-out (Milestone 4.4), identical across every
    candidate evaluated within one cycle, so any one row's value is
    representative. `None` when no consensus_snapshots row exists at all
    for this recommendation_id (e.g. every candidate's fan-out
    participation was itself totally empty) -- never fabricated."""
    response = await client.get(
        "/rest/v1/consensus_snapshots",
        params={
            "recommendation_id": f"eq.{recommendation_id}",
            "select": "participation_metadata",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise RecommendationExplanationsError(
            f"failed to read participation_metadata for recommendation_id={recommendation_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        return None
    return rows[0]["participation_metadata"]


async def persist_product_explanation(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_product_id: str,
    why_this_shape: str,
    why_not_other_shapes: str | None,
    rejected_alternatives: list[dict],
    data_limitations: str | None,
    explainability_version: str,
) -> str:
    """Inserts the single, permanent explanation row for one
    `recommendation_products` row (UNIQUE constraint enforces exactly one,
    ever). `narrative_summary` is never set here -- Milestone 5.2 is
    deterministic-only; the column stays NULL, reserved for a future
    narrative layer that would populate it only at row-creation time for
    NEW products, never via an UPDATE to this one (the table is
    append-only). `explainability_version` (Milestone 5.3, Decision AX)
    is always supplied explicitly by the caller
    (`app.features.explainability.EXPLAINABILITY_VERSION`) -- never left
    to the column's DB-level default, so a future version bump is never
    silently missed by forgetting to also update this call site."""
    payload = {
        "recommendation_product_id": recommendation_product_id,
        "why_this_shape": why_this_shape,
        "why_not_other_shapes": why_not_other_shapes,
        "rejected_alternatives": rejected_alternatives,
        "data_limitations": data_limitations,
        "explainability_version": explainability_version,
    }
    response = await client.post(
        "/rest/v1/recommendation_product_explanations",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise RecommendationExplanationsError(
            f"failed to persist product explanation for recommendation_product_id={recommendation_product_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise RecommendationExplanationsError(
            f"product explanation insert for recommendation_product_id={recommendation_product_id!r} returned no row"
        )
    return rows[0]["id"]


async def persist_leg_explanation(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_leg_id: str,
    why_selected: str,
    strongest_evidence: str,
    contributing_agents: list[dict],
    biggest_risks: str,
    rejected_alternatives: list[dict],
    would_change_mind_if: str | None,
    explainability_version: str,
) -> str:
    """Inserts the single, permanent explanation row for one
    `recommendation_legs` row (UNIQUE constraint enforces exactly one,
    ever). Same `narrative_summary` reservation as the product-level
    function above. `explainability_version`: see
    `persist_product_explanation`'s identical note."""
    payload = {
        "recommendation_leg_id": recommendation_leg_id,
        "why_selected": why_selected,
        "strongest_evidence": strongest_evidence,
        "contributing_agents": contributing_agents,
        "biggest_risks": biggest_risks,
        "rejected_alternatives": rejected_alternatives,
        "would_change_mind_if": would_change_mind_if,
        "explainability_version": explainability_version,
    }
    response = await client.post(
        "/rest/v1/recommendation_leg_explanations",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise RecommendationExplanationsError(
            f"failed to persist leg explanation for recommendation_leg_id={recommendation_leg_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise RecommendationExplanationsError(
            f"leg explanation insert for recommendation_leg_id={recommendation_leg_id!r} returned no row"
        )
    return rows[0]["id"]
