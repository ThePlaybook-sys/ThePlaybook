"""Time Machine activation-snapshot/lifecycle-event persistence (Milestone
5.3, Decisions AO-AZ). Writes the new manifest tables --
`recommendation_activation_snapshots`, `recommendation_activation_snapshot_legs`,
`recommendation_activation_snapshot_source_products`, and
`recommendation_product_lifecycle_events` -- all additive, all append-only
(DB-enforced full-block UPDATE triggers), matching every other Milestone
5.x persistence module's convention exactly.

**The manifest composes, never duplicates.** No function here writes an
odds/EV/confidence/explanation-text value -- those already live, frozen,
on `recommendation_legs`/`recommendation_product_explanations`/
`recommendation_leg_explanations` (Milestones 5.1/5.2). This module only
ever writes correlation ids, order, and event metadata."""
from __future__ import annotations

import httpx


class ActivationSnapshotError(Exception):
    """Raised when an activation-snapshot/lifecycle-event write fails on
    Supabase's side."""


async def persist_activation_snapshot(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_product_id: str,
    strategy_version: str,
    recommendation_product_explanation_id: str | None,
) -> str:
    """Inserts the single, permanent activation-snapshot row for one
    `recommendation_products` row (UNIQUE constraint enforces exactly
    one, ever). `recommendation_product_explanation_id` is nullable --
    Milestone 5.2's own per-unit failure isolation means a product's
    explanation can fail to generate even though the product itself was
    persisted successfully; the activation snapshot must not be blocked
    by that (already-isolated) failure."""
    payload = {
        "recommendation_product_id": recommendation_product_id,
        "strategy_version": strategy_version,
        "recommendation_product_explanation_id": recommendation_product_explanation_id,
    }
    response = await client.post(
        "/rest/v1/recommendation_activation_snapshots",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise ActivationSnapshotError(
            f"failed to persist activation snapshot for recommendation_product_id={recommendation_product_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise ActivationSnapshotError(
            f"activation snapshot insert for recommendation_product_id={recommendation_product_id!r} returned no row"
        )
    return rows[0]["id"]


async def persist_activation_snapshot_leg(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    activation_snapshot_id: str,
    recommendation_leg_id: str,
    leg_order: int,
) -> str:
    """Inserts one leg-membership row -- `leg_order` freezes the
    activation-time presentation order exactly as
    `recommendation_legs.leg_order` already recorded it (Milestone 5.1);
    this is a normalized join, never an array/JSON column, per Decision
    AO."""
    payload = {
        "activation_snapshot_id": activation_snapshot_id,
        "recommendation_leg_id": recommendation_leg_id,
        "leg_order": leg_order,
    }
    response = await client.post(
        "/rest/v1/recommendation_activation_snapshot_legs",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise ActivationSnapshotError(
            f"failed to persist activation snapshot leg for activation_snapshot_id={activation_snapshot_id!r} "
            f"recommendation_leg_id={recommendation_leg_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise ActivationSnapshotError(
            f"activation snapshot leg insert for activation_snapshot_id={activation_snapshot_id!r} returned no row"
        )
    return rows[0]["id"]


async def persist_activation_snapshot_source_product(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    activation_snapshot_id: str,
    source_recommendation_product_id: str,
) -> str:
    """Inserts one source-product membership row -- for a
    `bankroll_preservation` activation, freezes the exact per-game
    `no_bet` products that constituted that slate-level decision
    (Decision AR), never leaving a future reader to rediscover them via
    `master_refresh_run_id` alone."""
    payload = {
        "activation_snapshot_id": activation_snapshot_id,
        "source_recommendation_product_id": source_recommendation_product_id,
    }
    response = await client.post(
        "/rest/v1/recommendation_activation_snapshot_source_products",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise ActivationSnapshotError(
            f"failed to persist activation snapshot source product for activation_snapshot_id={activation_snapshot_id!r} "
            f"source_recommendation_product_id={source_recommendation_product_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise ActivationSnapshotError(
            f"activation snapshot source product insert for activation_snapshot_id={activation_snapshot_id!r} returned no row"
        )
    return rows[0]["id"]


async def persist_lifecycle_event(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_product_id: str,
    event_type: str,
    reason: str | None = None,
) -> str:
    """Inserts one append-only lifecycle event -- `event_type` is one of
    `ACTIVATED`/`WITHDRAWN`/`SOFT_DELETED` (Decision AZ; the future
    execution-state events for Bet Timing & Execution Intelligence are
    explicitly NOT added here, per Decision BE). Never overwrites a
    prior event -- a product's full lifecycle history is the append-only
    sequence of these rows, not a single current-state row."""
    payload = {
        "recommendation_product_id": recommendation_product_id,
        "event_type": event_type,
        "reason": reason,
    }
    response = await client.post(
        "/rest/v1/recommendation_product_lifecycle_events",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise ActivationSnapshotError(
            f"failed to persist lifecycle event {event_type!r} for recommendation_product_id={recommendation_product_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise ActivationSnapshotError(
            f"lifecycle event insert for recommendation_product_id={recommendation_product_id!r} returned no row"
        )
    return rows[0]["id"]
