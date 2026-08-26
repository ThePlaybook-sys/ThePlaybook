"""Time Machine reconstruction read functions (Milestone 5.3, Decision
BC). Every function here is a plain, single-purpose read of an
already-frozen/append-only row -- nothing here re-derives, re-ranks, or
re-computes anything `app.features.strategy`/`app.features.explainability`
already decided. `app.orchestration.reconstruction.reconstruct_recommendation_product`
composes these into one coherent historical view.

Every read returns `None`/`[]` for "not found," never a synthesized
shape -- matching `app.persistence.games.get_game`'s own established
convention exactly."""
from __future__ import annotations

import httpx


class ReconstructionReadError(Exception):
    """Raised when a reconstruction read fails on Supabase's side."""


async def read_recommendation_product(client: httpx.AsyncClient, headers: dict, *, recommendation_product_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/recommendation_products",
        params={
            "id": f"eq.{recommendation_product_id}",
            "select": (
                "id,display_id,recommendation_type,scope,game_id,recommendation_id,master_refresh_run_id,"
                "min_required_tier,status,withdrawn_at,withdrawal_reason,deleted_at,created_at"
            ),
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ReconstructionReadError(
            f"failed to read recommendation_product id={recommendation_product_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def read_activation_snapshot(client: httpx.AsyncClient, headers: dict, *, recommendation_product_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/recommendation_activation_snapshots",
        params={"recommendation_product_id": f"eq.{recommendation_product_id}", "select": "*"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ReconstructionReadError(
            f"failed to read activation snapshot for recommendation_product_id={recommendation_product_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def read_activation_snapshot_legs(client: httpx.AsyncClient, headers: dict, *, activation_snapshot_id: str) -> list[dict]:
    """Ordered by `leg_order` -- the activation-time presentation order
    frozen at snapshot-creation time (Decision AQ), never re-derived by
    re-ranking current candidate data."""
    response = await client.get(
        "/rest/v1/recommendation_activation_snapshot_legs",
        params={
            "activation_snapshot_id": f"eq.{activation_snapshot_id}",
            "select": "recommendation_leg_id,leg_order",
            "order": "leg_order.asc",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ReconstructionReadError(
            f"failed to read activation snapshot legs for activation_snapshot_id={activation_snapshot_id!r}: "
            f"{response.status_code} {response.text}"
        )
    return response.json()


async def read_activation_snapshot_source_products(
    client: httpx.AsyncClient, headers: dict, *, activation_snapshot_id: str
) -> list[dict]:
    response = await client.get(
        "/rest/v1/recommendation_activation_snapshot_source_products",
        params={"activation_snapshot_id": f"eq.{activation_snapshot_id}", "select": "source_recommendation_product_id"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ReconstructionReadError(
            f"failed to read activation snapshot source products for activation_snapshot_id={activation_snapshot_id!r}: "
            f"{response.status_code} {response.text}"
        )
    return response.json()


async def read_recommendation_leg(client: httpx.AsyncClient, headers: dict, *, recommendation_leg_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/recommendation_legs",
        params={
            "id": f"eq.{recommendation_leg_id}",
            "select": (
                "id,candidate_key,market_type,selection,sportsbook,american_odds,point,decimal_odds,"
                "ev_per_dollar,final_aggregate_confidence,leg_order,consensus_snapshot_id,game_id,recommendation_id"
            ),
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ReconstructionReadError(
            f"failed to read recommendation_leg id={recommendation_leg_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def read_product_explanation_by_id(client: httpx.AsyncClient, headers: dict, *, explanation_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/recommendation_product_explanations",
        params={"id": f"eq.{explanation_id}", "select": "*"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ReconstructionReadError(
            f"failed to read recommendation_product_explanations id={explanation_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def read_leg_explanation_by_leg_id(client: httpx.AsyncClient, headers: dict, *, recommendation_leg_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/recommendation_leg_explanations",
        params={"recommendation_leg_id": f"eq.{recommendation_leg_id}", "select": "*"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ReconstructionReadError(
            f"failed to read recommendation_leg_explanations for recommendation_leg_id={recommendation_leg_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def read_latest_user_selection(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_product_id: str,
    recommendation_leg_id: str | None,
    user_id: str,
) -> dict | None:
    """Reads the user's own historical `user_recommendation_selections`
    row for this product/leg -- append-only (Milestone 5.1), so the
    LATEST row for this `(user, product, leg)` key is the one that was
    actually true at the most recent observation. `None` when the user
    never had a selection recorded for this product/leg (no row ever
    written) -- never joins `user_profiles`/reads current preferences as
    a substitute (Decision BB)."""
    params = {
        "recommendation_product_id": f"eq.{recommendation_product_id}",
        "user_id": f"eq.{user_id}",
        "select": (
            "id,risk_tolerance,bankroll_at_computation,excluded_by_session_preferences,"
            "full_kelly_fraction,quarter_kelly_fraction,risk_tolerance_multiplier,stake,created_at"
        ),
        "order": "created_at.desc",
        "limit": "1",
    }
    params["recommendation_leg_id"] = f"eq.{recommendation_leg_id}" if recommendation_leg_id is not None else "is.null"
    response = await client.get("/rest/v1/user_recommendation_selections", params=params, headers=headers)
    if response.status_code != 200:
        raise ReconstructionReadError(
            f"failed to read user_recommendation_selections for recommendation_product_id={recommendation_product_id!r} "
            f"user_id={user_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None
