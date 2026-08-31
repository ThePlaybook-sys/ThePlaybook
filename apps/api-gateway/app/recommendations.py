"""Phase 6 Milestone 2 -- thin read-only exposure of already-persisted
Phase 1-5 recommendation data (Volume 5 v5.0). Every route here selects,
joins, and serializes existing rows; none computes a probability, an EV,
a stake, a ranking, or new explainability. See `app.entitlement` for the
tier-gating this module applies uniformly, and
`app.internal_client.call_ai_orchestrator` for the one route
(`/reconstruction`) that reuses Milestone 5.3's `reconstruct_
recommendation_product` instead of re-deriving history itself.

**Milestone 2.1 (additive contract correction, HQ-authorized): product
grade summary.** `recommendation_products.status` stays exactly
`'active'|'withdrawn'` -- lifecycle status -- and is never overloaded
with a `'graded'` value; grade state is a separate dimension, carried in
the new `grade` field below, sourced from `recommendation_product_
grade_events` (Milestone 5.4). `grade` is `null` for an ungraded product
and otherwise `{outcome, gradedAt, isCorrection, correctedAt}`. The
current-outcome resolution (`_current_grade` below) mirrors the exact
rule `app.track_record.get_track_record` already established in this
codebase: the correction chain is append-only and a correction always
lands with a strictly later `computed_at` than the row it supersedes, so
the latest row by `computed_at` is the authoritative current outcome --
no new merge/reconciliation algorithm is invented here. `PENDING_
MISSING_DATA` never appears at product scope (`app.orchestration.
postgame_grading._maybe_rollup_product`, ai-orchestrator, skips
persisting a product-level row entirely while any leg is still
non-terminal), so a present `grade.outcome` is always one of
`WIN|LOSS|PUSH|VOID_NO_ACTION|NOT_APPLICABLE|MIXED_SETTLED`. Per-leg
grade exposure was inspected and is not added: no field in the approved
Volume 5 §5 component contracts (card or four-layer detail) reads a
per-leg outcome -- `MIXED_SETTLED` is already the authoritative
product-level rollup value, so the frontend never needs to derive it
from legs.

**Ordering (HQ Final Decision 1):** no cross-product rank/priority field
exists anywhere in the schema. A game-scoped product orders by its own
game's `scheduled_start` (the real kickoff time, confirmed populated and
not-null); a slate-scoped product (`multiple_singles`/
`bankroll_preservation`, no single `game_id`) falls back to its
`recommendation_activation_snapshots.activated_at`. Neither is EV or
confidence -- both are neutral, already-persisted timestamps. No field
in any response here is named or implies "primary"/"top"/"best".

**Freshness (HQ Final Decision 10):** `decidedAt` on every card is
`recommendation_activation_snapshots.activated_at` -- recommendation
decision time, never called "updated"/"refreshed". Source/intelligence
freshness (`master_refresh_runs.completed_at`) is a page-level concept
the frontend reads from a separate concern (Master Refresh run status),
not attached to individual recommendation rows here.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, get_current_user
from app.entitlement import read_active_subscription_tier, tier_permits
from app.internal_client import InternalServiceError, call_ai_orchestrator
from app.supabase_client import new_client, postgrest_headers

router = APIRouter(prefix="/v1/recommendations", tags=["recommendations"])

#: Every recommendation_type currently issuable (Volume 3 §5A). Not
#: including same_game_parlay/multi_game_parlay in read paths beyond
#: passthrough -- schema-supported but no code ever writes them
#: (Volume 5 v5.0 §5); this module makes no special case for them, it
#: simply serializes whatever recommendation_type a row actually has.


async def _read_game(client: httpx.AsyncClient, *, game_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/games",
        params={"id": f"eq.{game_id}", "select": "id,home_team,away_team,scheduled_start,status"},
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


async def _read_games_by_ids(client: httpx.AsyncClient, game_ids: list[str]) -> dict[str, dict]:
    if not game_ids:
        return {}
    response = await client.get(
        "/rest/v1/games",
        params={
            "id": f"in.({','.join(game_ids)})",
            "select": "id,home_team,away_team,scheduled_start,status",
        },
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    return {row["id"]: row for row in response.json()}


async def _read_activation_snapshots_by_product_ids(
    client: httpx.AsyncClient, product_ids: list[str]
) -> dict[str, dict]:
    if not product_ids:
        return {}
    response = await client.get(
        "/rest/v1/recommendation_activation_snapshots",
        params={
            "recommendation_product_id": f"in.({','.join(product_ids)})",
            "select": "recommendation_product_id,activated_at",
        },
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    return {row["recommendation_product_id"]: row for row in response.json()}


async def _read_legs_by_product_ids(client: httpx.AsyncClient, product_ids: list[str]) -> dict[str, list[dict]]:
    if not product_ids:
        return {}
    response = await client.get(
        "/rest/v1/recommendation_legs",
        params={
            "recommendation_product_id": f"in.({','.join(product_ids)})",
            "select": "*",
            "order": "leg_order.asc",
        },
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    legs_by_product: dict[str, list[dict]] = {}
    for leg in response.json():
        legs_by_product.setdefault(leg["recommendation_product_id"], []).append(leg)
    return legs_by_product


async def _read_grade_events_by_product_ids(client: httpx.AsyncClient, product_ids: list[str]) -> dict[str, list[dict]]:
    if not product_ids:
        return {}
    response = await client.get(
        "/rest/v1/recommendation_product_grade_events",
        params={
            "recommendation_product_id": f"in.({','.join(product_ids)})",
            "select": "recommendation_product_id,outcome,is_correction,computed_at",
            "order": "computed_at.asc",
        },
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    events_by_product: dict[str, list[dict]] = {}
    for row in response.json():
        events_by_product.setdefault(row["recommendation_product_id"], []).append(row)
    return events_by_product


def _current_grade(events: list[dict]) -> dict | None:
    """Resolves the authoritative CURRENT grade for one product from its
    append-only recommendation_product_grade_events rows (chronological,
    oldest first -- see caller). See module docstring: the latest row by
    computed_at is always the current outcome, mirroring app.track_
    record.get_track_record's own resolution rule rather than inventing
    a second one. `gradedAt` is the ORIGINAL grade's timestamp (when the
    product was first graded); `correctedAt` is only set when the
    current row is itself a correction, giving the frontend a real date
    for the "result corrected [date]" sub-label (Volume 5 §5) without it
    ever reconstructing the chain itself."""
    if not events:
        return None
    original, current = events[0], events[-1]
    return {
        "outcome": current["outcome"],
        "gradedAt": original["computed_at"],
        "isCorrection": current["is_correction"],
        "correctedAt": current["computed_at"] if current["is_correction"] else None,
    }


def _order_key(product: dict, games_by_id: dict[str, dict], snapshots_by_product: dict[str, dict]) -> str:
    """Neutral chronological order key -- see module docstring. Falls
    back to `created_at` only in the (should-never-happen) case a
    product has neither a game nor an activation snapshot yet, so
    ordering never raises on a row that's mid-write."""
    if product.get("game_id") and product["game_id"] in games_by_id:
        return games_by_id[product["game_id"]]["scheduled_start"]
    snapshot = snapshots_by_product.get(product["id"])
    if snapshot:
        return snapshot["activated_at"]
    return product["created_at"]


def _serialize_leg(leg: dict) -> dict:
    return {
        "marketType": leg["market_type"],
        "selection": leg["selection"],
        "sportsbook": leg["sportsbook"],
        "americanOdds": leg["american_odds"],
        "point": leg["point"],
        "decimalOdds": leg["decimal_odds"],
        "evPerDollar": leg["ev_per_dollar"],
        "finalAggregateConfidence": leg["final_aggregate_confidence"],
        "legOrder": leg["leg_order"],
    }


def _serialize_product(
    product: dict,
    *,
    legs: list[dict],
    game: dict | None,
    decided_at: str | None,
    explanation: dict | None,
    grade: dict | None = None,
) -> dict:
    return {
        "displayId": product["display_id"],
        "recommendationType": product["recommendation_type"],
        "scope": product["scope"],
        "status": product["status"],
        "minRequiredTier": product["min_required_tier"],
        "withdrawnAt": product.get("withdrawn_at"),
        "withdrawalReason": product.get("withdrawal_reason"),
        "decidedAt": decided_at,
        "grade": grade,
        "game": (
            {
                "homeTeam": game["home_team"],
                "awayTeam": game["away_team"],
                "scheduledStart": game["scheduled_start"],
                "status": game["status"],
            }
            if game
            else None
        ),
        "oneLineSummary": explanation["why_this_shape"] if explanation else None,
        "legs": [_serialize_leg(leg) for leg in legs],
    }


async def _visible_products_with_context(
    client: httpx.AsyncClient, *, products: list[dict], user_tier: str | None
) -> list[dict]:
    """Applies tier-gating (app.entitlement), then fetches and attaches
    every product's game, activation timestamp, legs, and top-level
    explanation, returning fully serialized cards ordered per the
    module docstring's neutral ordering rule."""
    visible = [p for p in products if tier_permits(p["min_required_tier"], user_tier)]
    if not visible:
        return []

    product_ids = [p["id"] for p in visible]
    game_ids = [p["game_id"] for p in visible if p.get("game_id")]

    games_by_id, snapshots_by_product, legs_by_product, explanations_by_product, grade_events_by_product = (
        await _read_games_by_ids(client, game_ids),
        await _read_activation_snapshots_by_product_ids(client, product_ids),
        await _read_legs_by_product_ids(client, product_ids),
        await _read_explanations_by_product_ids(client, product_ids),
        await _read_grade_events_by_product_ids(client, product_ids),
    )

    serialized = []
    for product in visible:
        order_key = _order_key(product, games_by_id, snapshots_by_product)
        snapshot = snapshots_by_product.get(product["id"])
        serialized.append(
            (
                order_key,
                _serialize_product(
                    product,
                    legs=legs_by_product.get(product["id"], []),
                    game=games_by_id.get(product.get("game_id")),
                    decided_at=snapshot["activated_at"] if snapshot else None,
                    explanation=explanations_by_product.get(product["id"]),
                    grade=_current_grade(grade_events_by_product.get(product["id"], [])),
                ),
            )
        )
    serialized.sort(key=lambda pair: pair[0])
    return [card for _order_key, card in serialized]


async def _read_explanations_by_product_ids(client: httpx.AsyncClient, product_ids: list[str]) -> dict[str, dict]:
    if not product_ids:
        return {}
    response = await client.get(
        "/rest/v1/recommendation_product_explanations",
        params={
            "recommendation_product_id": f"in.({','.join(product_ids)})",
            "select": "recommendation_product_id,why_this_shape,why_not_other_shapes,rejected_alternatives,data_limitations",
        },
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    return {row["recommendation_product_id"]: row for row in response.json()}


@router.get("/today")
async def get_todays_recommendations(current_user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    """Today's recommendation_products -- game-scoped products whose
    game kicks off today (UTC calendar day), plus slate-scoped products
    (multiple_singles/bankroll_preservation) whose Master Refresh run
    started today. Includes withdrawn products (the frontend renders
    the withdrawn treatment, this route never hides history) -- only
    `deleted_at is null` rows are excluded, matching every other
    Phase 5 read path's own convention."""
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    async with new_client() as client:
        user_tier = await read_active_subscription_tier(client, user_id=current_user.id)

        games_today = await client.get(
            "/rest/v1/games",
            params={
                "scheduled_start": [f"gte.{day_start.isoformat()}", f"lt.{day_end.isoformat()}"],
                "select": "id",
            },
            headers=postgrest_headers(),
        )
        games_today.raise_for_status()
        game_ids_today = [row["id"] for row in games_today.json()]

        runs_today = await client.get(
            "/rest/v1/master_refresh_runs",
            params={
                "started_at": [f"gte.{day_start.isoformat()}", f"lt.{day_end.isoformat()}"],
                "select": "id",
            },
            headers=postgrest_headers(),
        )
        runs_today.raise_for_status()
        run_ids_today = [row["id"] for row in runs_today.json()]

        if not game_ids_today and not run_ids_today:
            return []

        or_clauses = []
        if game_ids_today:
            or_clauses.append(f"game_id.in.({','.join(game_ids_today)})")
        if run_ids_today:
            or_clauses.append(f"master_refresh_run_id.in.({','.join(run_ids_today)})")

        products_response = await client.get(
            "/rest/v1/recommendation_products",
            params={"deleted_at": "is.null", "or": f"({','.join(or_clauses)})", "select": "*"},
            headers=postgrest_headers(),
        )
        products_response.raise_for_status()

        return await _visible_products_with_context(
            client, products=products_response.json(), user_tier=user_tier
        )


@router.get("")
async def list_recommendations(
    since: str | None = Query(default=None, description="ISO date, inclusive lower bound on game/run date"),
    until: str | None = Query(default=None, description="ISO date, exclusive upper bound"),
    limit: int = Query(default=50, le=200),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """Broader recommendation feed -- reads existing product/leg state
    only, same tier-gating and ordering as `/today`. Defaults to the
    trailing 30 days when no range is given."""
    now = datetime.now(timezone.utc)
    until_dt = datetime.fromisoformat(until) if until else now + timedelta(days=1)
    since_dt = datetime.fromisoformat(since) if since else now - timedelta(days=30)

    async with new_client() as client:
        user_tier = await read_active_subscription_tier(client, user_id=current_user.id)

        products_response = await client.get(
            "/rest/v1/recommendation_products",
            params={
                "deleted_at": "is.null",
                "created_at": [f"gte.{since_dt.isoformat()}", f"lt.{until_dt.isoformat()}"],
                "select": "*",
                "order": "created_at.desc",
                "limit": str(limit),
            },
            headers=postgrest_headers(),
        )
        products_response.raise_for_status()

        return await _visible_products_with_context(
            client, products=products_response.json(), user_tier=user_tier
        )


async def _read_product_by_display_id(client: httpx.AsyncClient, *, display_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/recommendation_products",
        params={"display_id": f"eq.{display_id}", "deleted_at": "is.null", "select": "*"},
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


async def _authorize_product_for_display_id(client: httpx.AsyncClient, *, display_id: str, user_tier: str | None) -> dict:
    """Shared by the detail and reconstruction routes: resolve
    display_id -> row, 404 if absent, 404 (never 403 -- see module
    docstring on not inferring locked content) if the caller's tier
    doesn't reach it."""
    product = await _read_product_by_display_id(client, display_id=display_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if not tier_permits(product["min_required_tier"], user_tier):
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return product


async def _read_agent_outputs_for_recommendation(client: httpx.AsyncClient, *, recommendation_id: str) -> list[dict]:
    response = await client.get(
        "/rest/v1/recommendation_agent_outputs",
        params={
            "recommendation_id": f"eq.{recommendation_id}",
            "select": "agent_id,candidate_key,agent_confidence,weight_applied,raw_output,model_name,provider,used_fallback,prompt_name,prompt_version",
        },
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    return response.json()


async def _read_agent_names(client: httpx.AsyncClient, agent_ids: list[str]) -> dict[str, str]:
    if not agent_ids:
        return {}
    response = await client.get(
        "/rest/v1/agents",
        params={"id": f"in.({','.join(agent_ids)})", "select": "id,name"},
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    return {row["id"]: row["name"] for row in response.json()}


async def _read_consensus_snapshot(client: httpx.AsyncClient, *, consensus_snapshot_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/consensus_snapshots",
        params={
            "id": f"eq.{consensus_snapshot_id}",
            "select": "aggregate_confidence,agreement_variance,final_aggregate_confidence,below_confidence_floor",
        },
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


async def _read_leg_explanation(client: httpx.AsyncClient, *, recommendation_leg_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/recommendation_leg_explanations",
        params={"recommendation_leg_id": f"eq.{recommendation_leg_id}", "select": "*"},
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


@router.get("/{display_id}")
async def get_recommendation_detail(
    display_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> dict:
    """Full detail across Layers 1-4 (Volume 5 v5.0 §5): product, legs,
    the top-level and per-leg explanations (Layers 1-3), and per-leg
    agent contributions/provenance/consensus (Layer 4). Every field is
    read straight from an already-persisted row -- `directionalLean` is
    read out of `raw_output` verbatim (never re-derived), agent names
    come from a plain `agents` join, nothing here calls a model or
    recomputes consensus math."""
    async with new_client() as client:
        user_tier = await read_active_subscription_tier(client, user_id=current_user.id)
        product = await _authorize_product_for_display_id(client, display_id=display_id, user_tier=user_tier)

        game = await _read_game(client, game_id=product["game_id"]) if product.get("game_id") else None
        snapshots = await _read_activation_snapshots_by_product_ids(client, [product["id"]])
        explanation = (await _read_explanations_by_product_ids(client, [product["id"]])).get(product["id"])
        legs = (await _read_legs_by_product_ids(client, [product["id"]])).get(product["id"], [])
        grade_events = (await _read_grade_events_by_product_ids(client, [product["id"]])).get(product["id"], [])

        leg_details = []
        for leg in legs:
            leg_explanation = await _read_leg_explanation(client, recommendation_leg_id=leg["id"])
            agent_outputs = await _read_agent_outputs_for_recommendation(client, recommendation_id=leg["recommendation_id"])
            matching_outputs = [o for o in agent_outputs if o.get("candidate_key") == leg["candidate_key"]]
            agent_names = await _read_agent_names(client, [o["agent_id"] for o in matching_outputs])
            consensus = await _read_consensus_snapshot(client, consensus_snapshot_id=leg["consensus_snapshot_id"])

            leg_details.append(
                {
                    **_serialize_leg(leg),
                    "whySelected": leg_explanation["why_selected"] if leg_explanation else None,
                    "strongestEvidence": leg_explanation["strongest_evidence"] if leg_explanation else None,
                    "contributingAgents": leg_explanation["contributing_agents"] if leg_explanation else [],
                    "biggestRisks": leg_explanation["biggest_risks"] if leg_explanation else None,
                    "rejectedAlternatives": leg_explanation["rejected_alternatives"] if leg_explanation else [],
                    "wouldChangeMindIf": leg_explanation["would_change_mind_if"] if leg_explanation else None,
                    "agentContributions": [
                        {
                            "agentId": o["agent_id"],
                            "agentName": agent_names.get(o["agent_id"]),
                            "agentConfidence": o["agent_confidence"],
                            "weightApplied": o["weight_applied"],
                            "directionalLean": (o.get("raw_output") or {}).get("directional_lean"),
                            "modelName": o["model_name"],
                            "provider": o["provider"],
                            "usedFallback": o["used_fallback"],
                            "promptName": o["prompt_name"],
                            "promptVersion": o["prompt_version"],
                        }
                        for o in matching_outputs
                    ],
                    "consensus": (
                        {
                            "aggregateConfidence": consensus["aggregate_confidence"],
                            "agreementVariance": consensus["agreement_variance"],
                            "finalAggregateConfidence": consensus["final_aggregate_confidence"],
                            "belowConfidenceFloor": consensus["below_confidence_floor"],
                        }
                        if consensus
                        else None
                    ),
                }
            )

        base = _serialize_product(
            product,
            legs=[],
            game=game,
            decided_at=snapshots.get(product["id"], {}).get("activated_at"),
            explanation=explanation,
            grade=_current_grade(grade_events),
        )
        base["legs"] = leg_details
        base["whyNotOtherShapes"] = explanation["why_not_other_shapes"] if explanation else None
        base["rejectedAlternatives"] = explanation["rejected_alternatives"] if explanation else []
        base["dataLimitations"] = explanation["data_limitations"] if explanation else None
        return base


@router.get("/{display_id}/reconstruction")
async def get_recommendation_reconstruction(
    display_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> dict:
    """Time Machine -- proxies to ai-orchestrator's internal
    `reconstruct_recommendation_product` wrapper (Milestone 5.3, reused
    verbatim per HQ's explicit instruction not to rebuild historical
    reasoning here). This route's only job beyond proxying is resolving
    display_id -> internal id and applying the same tier gate every
    other route in this module applies."""
    async with new_client() as client:
        user_tier = await read_active_subscription_tier(client, user_id=current_user.id)
        product = await _authorize_product_for_display_id(client, display_id=display_id, user_tier=user_tier)

    try:
        response = await call_ai_orchestrator(
            "GET", f"/v1/internal/reconstruction/{product['id']}"
        )
    except InternalServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()
