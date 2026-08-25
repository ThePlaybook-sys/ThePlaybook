"""Recommendation-product persistence (Milestone 5.1). Writes the Phase 5
product layer -- `recommendation_products`/`recommendation_legs` -- from
an already-computed `app.features.strategy.SlateStrategyResult`. This
module never decides anything itself; `app.features.strategy` is the only
place Strategy Engine decisions are made.

**`display_id` generation (the atomicity proof lives in the migration --
see `supabase/migrations/20260825120000_recommendation_products_schema.sql`
and `20260825130000_display_id_counter_function.sql`):** PostgREST has no
way to express the required single-statement `INSERT ... ON CONFLICT ...
DO UPDATE SET counter = counter + 1 RETURNING counter` against a table
endpoint directly -- its upsert support only replaces columns with
client-supplied values, never a server-side expression referencing the
existing row. `next_display_id_counter` (a Postgres function) wraps that
exact statement; this module calls it via `/rest/v1/rpc/
next_display_id_counter`, preserving the same no-prior-read atomicity,
just over RPC transport instead of a raw table POST.

**Bucket policy, deliberately simple and separate from the atomicity
mechanism:** `bucket_key` is the 4-digit UTC year at generation time. This
is a product decision, not a correctness requirement -- it can change
later without touching the RPC or its proof.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.features.strategy import EvaluatedCandidate, SlateStrategyResult


class RecommendationProductsError(Exception):
    """Raised when a recommendation_products/recommendation_legs
    read/write fails on Supabase's side."""


async def generate_display_id(client: httpx.AsyncClient, headers: dict, *, now: datetime | None = None) -> str:
    """Calls the atomic `next_display_id_counter` RPC and formats the
    result as `"{year}-{counter:05d}"`. Never reads the counter first --
    the RPC itself is the single atomic statement (see module docstring)."""
    now = now or datetime.now(timezone.utc)
    bucket_key = f"{now.year:04d}"
    response = await client.post(
        "/rest/v1/rpc/next_display_id_counter",
        json={"p_bucket_key": bucket_key},
        headers={**headers, "Content-Type": "application/json"},
    )
    if response.status_code != 200:
        raise RecommendationProductsError(
            f"failed to generate display_id for bucket_key={bucket_key!r}: {response.status_code} {response.text}"
        )
    counter = response.json()
    return f"{bucket_key}-{counter:05d}"


async def _create_recommendation_product(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_type: str,
    scope: str,
    game_id: str | None,
    recommendation_id: str | None,
    master_refresh_run_id: str,
    min_required_tier: str = "free",
    now: datetime | None = None,
) -> str:
    display_id = await generate_display_id(client, headers, now=now)
    payload = {
        "display_id": display_id,
        "recommendation_type": recommendation_type,
        "scope": scope,
        "game_id": game_id,
        "recommendation_id": recommendation_id,
        "master_refresh_run_id": master_refresh_run_id,
        "min_required_tier": min_required_tier,
    }
    response = await client.post(
        "/rest/v1/recommendation_products",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise RecommendationProductsError(
            f"failed to create recommendation_product type={recommendation_type!r} scope={scope!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise RecommendationProductsError(f"recommendation_product insert for type={recommendation_type!r} returned no row")
    return rows[0]["id"]


async def _create_recommendation_leg(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_product_id: str,
    candidate: EvaluatedCandidate,
    leg_order: int,
) -> str:
    payload = {
        "recommendation_product_id": recommendation_product_id,
        "consensus_snapshot_id": candidate.consensus_snapshot_id,
        "game_id": candidate.game_id,
        "recommendation_id": candidate.recommendation_id,
        "candidate_key": candidate.candidate_key,
        "market_type": candidate.market_type,
        "selection": candidate.selection,
        "sportsbook": candidate.sportsbook,
        "american_odds": candidate.american_odds,
        "point": candidate.point,
        "decimal_odds": candidate.decimal_odds,
        "ev_per_dollar": candidate.ev_per_dollar,
        "final_aggregate_confidence": candidate.final_aggregate_confidence,
        "leg_order": leg_order,
    }
    response = await client.post(
        "/rest/v1/recommendation_legs",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise RecommendationProductsError(
            f"failed to create recommendation_leg for candidate_key={candidate.candidate_key!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise RecommendationProductsError(
            f"recommendation_leg insert for candidate_key={candidate.candidate_key!r} returned no row"
        )
    return rows[0]["id"]


async def persist_strategy_decision(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    master_refresh_run_id: str,
    decision: SlateStrategyResult,
    now: datetime | None = None,
) -> list[str]:
    """Writes every `recommendation_products` row (and, where applicable,
    its `recommendation_legs`) implied by one already-computed
    `SlateStrategyResult`. Returns the list of created `recommendation_products.id`
    values, in write order. One `no_bet` product is written per game whose
    `GameDecision.outcome == "no_bet"` -- independent of the slate-level
    outcome, exactly matching Decision AA (`no_bet` is a per-game fact).
    `no_bet` products carry zero legs (Invariant 1 -- see the migration's
    own proof); the correction this schema implements forbids fabricating
    one."""
    created_ids: list[str] = []

    for game_decision in decision.game_decisions:
        if game_decision.outcome != "no_bet":
            continue
        product_id = await _create_recommendation_product(
            client,
            headers,
            recommendation_type="no_bet",
            scope="game",
            game_id=game_decision.game_id,
            recommendation_id=game_decision.recommendation_id,
            master_refresh_run_id=master_refresh_run_id,
            now=now,
        )
        created_ids.append(product_id)

    if decision.outcome == "bankroll_preservation":
        product_id = await _create_recommendation_product(
            client,
            headers,
            recommendation_type="bankroll_preservation",
            scope="slate",
            game_id=None,
            recommendation_id=None,
            master_refresh_run_id=master_refresh_run_id,
            now=now,
        )
        created_ids.append(product_id)
        return created_ids

    if decision.outcome == "single":
        leg = decision.legs[0]
        product_id = await _create_recommendation_product(
            client,
            headers,
            recommendation_type="single",
            scope="game",
            game_id=leg.game_id,
            recommendation_id=leg.recommendation_id,
            master_refresh_run_id=master_refresh_run_id,
            now=now,
        )
        await _create_recommendation_leg(client, headers, recommendation_product_id=product_id, candidate=leg, leg_order=1)
        created_ids.append(product_id)
        return created_ids

    # decision.outcome == "multiple_singles"
    product_id = await _create_recommendation_product(
        client,
        headers,
        recommendation_type="multiple_singles",
        scope="slate",
        game_id=None,
        recommendation_id=None,
        master_refresh_run_id=master_refresh_run_id,
        now=now,
    )
    for leg_order, leg in enumerate(decision.legs, start=1):
        await _create_recommendation_leg(client, headers, recommendation_product_id=product_id, candidate=leg, leg_order=leg_order)
    created_ids.append(product_id)
    return created_ids
