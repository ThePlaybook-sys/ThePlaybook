"""Time Machine reconstruction orchestration (Milestone 5.3, Decision
BC; extended by the Pre-Phase-6 Operational Readiness Gate, 2026-08-27,
Sections 9/10). The one function the roadmap's own acceptance criterion
requires: "reconstruct recommendation product X as it existed when
activated" -- now extended to also compose the later historical evidence
Milestones 5.4/5.5 went on to build (grading, Postgame Review, Adaptive
Weighting), not just the Milestone 5.1-5.3 activation slice. Internal
only -- no public API route is added here (Decision BC defers that to
Phase 6, which owns the public-facing API design).

**Read-only, composition-only, unchanged as a principle.** Every value
returned here is read back from an already-frozen/append-only row --
`recommendation_products`, `recommendation_activation_snapshots` and its
two join tables, `recommendation_legs`, `recommendation_product_explanations`/
`recommendation_leg_explanations`, `user_recommendation_selections`, and
now also `recommendation_product_lifecycle_events`,
`recommendation_leg_grade_events`, `recommendation_product_grade_events`,
`recommendation_product_postgame_reviews`, and
`adaptive_weight_proposals`/`adaptive_weight_proposal_observations`.
Nothing here re-runs `app.features.strategy`/`app.features.explainability`/
`app.features.grading`/`app.features.adaptive_weighting`, re-ranks legs,
re-grades anything, or re-derives a value current live state could have
moved -- that is exactly the property the reproducibility test
(`tests/orchestration/test_reconstruction.py`) proves. Downstream
evidence that does not yet exist (not graded yet, no review generated,
never evaluated for weighting) is represented as `[]`/`None`, exactly
the same "absent, never fabricated" discipline already established for
`product_explanation`/`user_selection`."""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.persistence.reconstruction_reads import (
    read_activation_snapshot,
    read_activation_snapshot_legs,
    read_activation_snapshot_source_products,
    read_latest_user_selection,
    read_leg_explanation_by_leg_id,
    read_leg_grade_event_history,
    read_lifecycle_events,
    read_postgame_reviews_for_product,
    read_product_explanation_by_id,
    read_product_grade_event_history,
    read_recommendation_leg,
    read_recommendation_product,
    read_weight_proposal_observations_for_grade_events,
    read_weight_proposals_by_ids,
)


class ReconstructionError(Exception):
    """Raised when the requested product (or its activation snapshot)
    cannot be found at all -- distinct from a downstream field simply
    being unavailable (e.g. no explanation, no user selection, no grade
    yet), which is represented as `None`/`[]`, never as an error."""


@dataclass
class ReconstructedWeightingEvidence:
    """One Adaptive Weighting observation this leg's own grade
    contributed to a committee evaluation, plus the evaluation (proposal)
    it belongs to -- Section 9's "Adaptive Weighting evidence/proposal,
    when one exists." A leg can appear in zero, one, or (across
    corrections/re-evaluations) more than one of these."""

    observation: dict
    proposal: dict | None


@dataclass
class ReconstructedLeg:
    leg_order: int
    leg: dict
    explanation: dict | None
    #: Every grade event this leg has ever received, oldest-first --
    #: both the original and any correction, never collapsed. `[]` when
    #: this leg has never been graded.
    grade_history: list[dict] = field(default_factory=list)
    #: `grade_history[-1]` (the most recent row, correction or not) --
    #: the "current authoritative grade," per the same latest-row-wins
    #: convention `app.orchestration.adaptive_weighting` already applies
    #: to this exact table (Decision 17). `None` when `grade_history` is
    #: empty.
    current_grade: dict | None = None
    weighting_evidence: list[ReconstructedWeightingEvidence] = field(default_factory=list)


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
    #: Every lifecycle transition this product has ever recorded
    #: (ACTIVATED/WITHDRAWN/SOFT_DELETED), oldest-first. Never empty for
    #: a product that reached activation (ACTIVATED is always the first
    #: row), but read exactly as persisted, never assumed.
    lifecycle_events: list[dict] = field(default_factory=list)
    #: Product-level grade history, oldest-first -- mirrors a leg's own
    #: `grade_history` at the product-rollup level (Volume 3 §5D). `[]`
    #: until every leg is terminal (or immediately, for `no_bet`/
    #: `bankroll_preservation`, once graded `NOT_APPLICABLE`).
    product_grade_history: list[dict] = field(default_factory=list)
    #: `product_grade_history[-1]`. `None` when `product_grade_history`
    #: is empty.
    current_product_grade: dict | None = None
    #: Every Postgame Review ever generated for this product,
    #: oldest-first. `[]` when none has been generated yet.
    postgame_reviews: list[dict] = field(default_factory=list)


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

    # Downstream historical evidence (Pre-Phase-6 Operational Readiness
    # Gate, Section 9) -- applies to every recommendation_type, including
    # no_bet/bankroll_preservation (which still get a lifecycle history
    # and a NOT_APPLICABLE product grade once graded), so this runs
    # before the per-type branch below, not inside it.
    result.lifecycle_events = await read_lifecycle_events(client, headers, recommendation_product_id=recommendation_product_id)
    result.product_grade_history = await read_product_grade_event_history(
        client, headers, recommendation_product_id=recommendation_product_id
    )
    result.current_product_grade = result.product_grade_history[-1] if result.product_grade_history else None
    result.postgame_reviews = await read_postgame_reviews_for_product(
        client, headers, recommendation_product_id=recommendation_product_id
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
        leg_id = row["recommendation_leg_id"]
        leg = await read_recommendation_leg(client, headers, recommendation_leg_id=leg_id)
        leg_explanation = await read_leg_explanation_by_leg_id(client, headers, recommendation_leg_id=leg_id)

        grade_history = await read_leg_grade_event_history(client, headers, recommendation_leg_id=leg_id)
        current_grade = grade_history[-1] if grade_history else None

        # Adaptive Weighting evidence (Section 9/10) -- every grade event
        # this leg has ever had (original + corrections) may independently
        # have been evaluated into a committee weighting proposal; all are
        # surfaced, not just the one tied to `current_grade`, since a
        # superseded grade's own historical evidence trail is never erased
        # (Decision 17).
        grade_event_ids = [event["id"] for event in grade_history]
        observations = await read_weight_proposal_observations_for_grade_events(
            client, headers, recommendation_leg_grade_event_ids=grade_event_ids
        )
        proposals_by_id = {
            p["id"]: p
            for p in await read_weight_proposals_by_ids(
                client, headers, proposal_ids=list({obs["proposal_id"] for obs in observations})
            )
        }
        weighting_evidence = [
            ReconstructedWeightingEvidence(observation=obs, proposal=proposals_by_id.get(obs["proposal_id"]))
            for obs in observations
        ]

        result.legs.append(
            ReconstructedLeg(
                leg_order=row["leg_order"],
                leg=leg,
                explanation=leg_explanation,
                grade_history=grade_history,
                current_grade=current_grade,
                weighting_evidence=weighting_evidence,
            )
        )

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
