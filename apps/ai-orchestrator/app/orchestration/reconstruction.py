"""Time Machine reconstruction orchestration (Milestone 5.3, Decision
BC). The one function the roadmap's own acceptance criterion requires:
"reconstruct recommendation product X as it existed when activated."
Internal only -- no public API route is added here (Decision BC defers
that to Phase 6, which owns the public-facing API design).

**Read-only, composition-only.** Every value returned here is read back
from an already-frozen/append-only row (`recommendation_products`,
`recommendation_activation_snapshots` and its two join tables,
`recommendation_legs`, `recommendation_product_explanations`/
`recommendation_leg_explanations`, `user_recommendation_selections`).
Nothing here re-runs `app.features.strategy`/`app.features.explainability`,
re-ranks legs, or re-derives a value current live state could have moved
-- that is exactly the property the reproducibility test
(`tests/orchestration/test_reconstruction.py`) proves."""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.persistence.reconstruction_reads import (
    read_activation_snapshot,
    read_activation_snapshot_legs,
    read_activation_snapshot_source_products,
    read_latest_user_selection,
    read_leg_explanation_by_leg_id,
    read_product_explanation_by_id,
    read_recommendation_leg,
    read_recommendation_product,
)


class ReconstructionError(Exception):
    """Raised when the requested product (or its activation snapshot)
    cannot be found at all -- distinct from a downstream field simply
    being unavailable (e.g. no explanation, no user selection), which is
    represented as `None`, never as an error."""


@dataclass
class ReconstructedLeg:
    leg_order: int
    leg: dict
    explanation: dict | None


@dataclass
class ReconstructedSourceProduct:
    recommendation_product_id: str
    explanation: dict | None


@dataclass
class ReconstructedProduct:
    product: dict
    activation_snapshot: dict
    strategy_version: str
    product_explanation: dict | None
    legs: list[ReconstructedLeg] = field(default_factory=list)
    source_products: list[ReconstructedSourceProduct] = field(default_factory=list)
    user_selection: dict | None = None


async def reconstruct_recommendation_product(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_product_id: str,
    user_id: str | None = None,
) -> ReconstructedProduct:
    """Reconstructs `recommendation_product_id` exactly as it existed at
    activation time. Raises `ReconstructionError` if the product or its
    activation snapshot doesn't exist at all (nothing to reconstruct) --
    every other field degrades to `None`/`[]` when genuinely unavailable,
    never fabricated.

    `user_id`, when given, additionally attaches that user's own latest
    `user_recommendation_selections` row for this product (and, for a
    leg-bearing product, resolved per-leg below) -- `None` when that user
    never had one recorded (Decision BB: never substituted with a join to
    current `user_profiles`)."""
    product = await read_recommendation_product(client, headers, recommendation_product_id=recommendation_product_id)
    if product is None:
        raise ReconstructionError(f"no recommendation_products row found for id={recommendation_product_id!r}")

    snapshot = await read_activation_snapshot(client, headers, recommendation_product_id=recommendation_product_id)
    if snapshot is None:
        raise ReconstructionError(
            f"no recommendation_activation_snapshots row found for recommendation_product_id={recommendation_product_id!r}"
        )

    product_explanation = None
    if snapshot["recommendation_product_explanation_id"] is not None:
        product_explanation = await read_product_explanation_by_id(
            client, headers, explanation_id=snapshot["recommendation_product_explanation_id"]
        )

    result = ReconstructedProduct(
        product=product,
        activation_snapshot=snapshot,
        strategy_version=snapshot["strategy_version"],
        product_explanation=product_explanation,
    )

    if product["recommendation_type"] == "bankroll_preservation":
        source_rows = await read_activation_snapshot_source_products(client, headers, activation_snapshot_id=snapshot["id"])
        for row in source_rows:
            source_product_id = row["source_recommendation_product_id"]
            source_snapshot = await read_activation_snapshot(client, headers, recommendation_product_id=source_product_id)
            source_explanation = None
            if source_snapshot is not None and source_snapshot["recommendation_product_explanation_id"] is not None:
                source_explanation = await read_product_explanation_by_id(
                    client, headers, explanation_id=source_snapshot["recommendation_product_explanation_id"]
                )
            result.source_products.append(
                ReconstructedSourceProduct(recommendation_product_id=source_product_id, explanation=source_explanation)
            )
        return result

    if product["recommendation_type"] == "no_bet":
        return result

    # single / multiple_singles -- leg-bearing.
    leg_rows = await read_activation_snapshot_legs(client, headers, activation_snapshot_id=snapshot["id"])
    for row in leg_rows:
        leg = await read_recommendation_leg(client, headers, recommendation_leg_id=row["recommendation_leg_id"])
        leg_explanation = await read_leg_explanation_by_leg_id(client, headers, recommendation_leg_id=row["recommendation_leg_id"])
        result.legs.append(ReconstructedLeg(leg_order=row["leg_order"], leg=leg, explanation=leg_explanation))

    if user_id is not None:
        # `single` has exactly one leg -- attach that leg's own selection.
        # `multiple_singles` has no single product-level selection concept
        # (each leg is its own independent wager); callers reconstructing
        # a specific leg's personalization pass `recommendation_leg_id`
        # via a future per-leg lookup if ever needed -- not built here,
        # since no code currently writes multi-leg-product selections
        # differently per leg (out of scope, not silently assumed).
        recommendation_leg_id = result.legs[0].leg["id"] if len(result.legs) == 1 else None
        result.user_selection = await read_latest_user_selection(
            client,
            headers,
            recommendation_product_id=recommendation_product_id,
            recommendation_leg_id=recommendation_leg_id,
            user_id=user_id,
        )

    return result
