"""Time Machine activation-snapshot/lifecycle-event orchestration
(Milestone 5.3, Decisions AO-AZ). Ties the already-persisted Milestone
5.1 `SlateStrategyResult` and Milestone 5.2 `ExplainabilityResult`
together into a durable, explicit manifest -- reachable only from
`app.orchestration.strategy_finalize.finalize_slate_strategy`, called
immediately after `generate_and_persist_explanations` (Milestone 5.2)
succeeds. Preserves the pipeline order: Phase 4 Analysis -> Strategy
Engine -> Explainability -> Time Machine activation snapshot.

**Composes, never duplicates.** No value here is copied a second time --
`recommendation_activation_snapshots`/`_legs`/`_source_products` store
only correlation ids, order, and event metadata, referencing
already-frozen Milestone 5.1/5.2 rows by FK. See
`app.persistence.recommendation_activation_snapshots`'s module docstring
for the full rationale.

**Per-product and per-leg failure isolation**, matching Milestone 5.2's
own established pattern exactly: one product's or one leg's snapshot
failing to generate never blocks the others, and never raises out of
`generate_activation_snapshots` itself -- every attempt, success or
failure, is recorded in the returned result. An activation-snapshot
failure never un-persists or hides the already-committed Strategy
decision or Explainability content -- Time Machine is purely additive,
read-only history on top of what Milestones 5.1/5.2 already wrote.

**Correlating already-created rows without touching frozen Milestone 5.1
code**, exactly the same technique `app.orchestration.explainability`
already established: relies on `persist_strategy_decision`'s own
documented write-order contract to map `created_product_ids` back to
`GameDecision`/`SlateStrategyResult` objects, and reuses
`app.persistence.recommendation_explanations.read_legs_for_product` (no
new read function needed) to discover each leg's id by `candidate_key`
match."""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.features.strategy import STRATEGY_VERSION, GameDecision, SlateStrategyResult
from app.orchestration.explainability import ExplainabilityResult
from app.persistence.recommendation_activation_snapshots import (
    persist_activation_snapshot,
    persist_activation_snapshot_leg,
    persist_activation_snapshot_source_product,
    persist_lifecycle_event,
)
from app.persistence.recommendation_explanations import read_legs_for_product


@dataclass
class ActivationSnapshotResult:
    product_id: str
    status: str  # "generated" | "failed"
    activation_snapshot_id: str | None = None
    error: str | None = None


@dataclass
class ActivationSnapshotLegResult:
    activation_snapshot_id: str
    candidate_key: str
    status: str  # "generated" | "failed"
    error: str | None = None


@dataclass
class TimeMachineResult:
    snapshots: list[ActivationSnapshotResult] = field(default_factory=list)
    legs: list[ActivationSnapshotLegResult] = field(default_factory=list)


def _no_bet_game_decisions(decision: SlateStrategyResult) -> list[GameDecision]:
    return [gd for gd in decision.game_decisions if gd.outcome == "no_bet"]


async def generate_activation_snapshots(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    decision: SlateStrategyResult,
    created_product_ids: list[str],
    explainability_result: ExplainabilityResult,
) -> TimeMachineResult:
    """`created_product_ids`/`decision` must be the exact same values
    already passed to `generate_and_persist_explanations` for this cycle
    -- relied on for the same write-order correlation that function
    already uses (see module docstring)."""
    result = TimeMachineResult()
    explanation_id_by_product = {p.product_id: p.explanation_id for p in explainability_result.products}

    no_bet_games = _no_bet_game_decisions(decision)
    no_bet_product_ids = created_product_ids[: len(no_bet_games)]

    for product_id in no_bet_product_ids:
        try:
            snapshot_id = await persist_activation_snapshot(
                client,
                headers,
                recommendation_product_id=product_id,
                strategy_version=STRATEGY_VERSION,
                recommendation_product_explanation_id=explanation_id_by_product.get(product_id),
            )
            await persist_lifecycle_event(client, headers, recommendation_product_id=product_id, event_type="ACTIVATED")
            result.snapshots.append(
                ActivationSnapshotResult(product_id=product_id, status="generated", activation_snapshot_id=snapshot_id)
            )
        except Exception as exc:  # noqa: BLE001 -- deliberate: one product's failure never blocks the rest
            result.snapshots.append(ActivationSnapshotResult(product_id=product_id, status="failed", error=str(exc)))

    if len(created_product_ids) <= len(no_bet_games):
        return result
    final_product_id = created_product_ids[len(no_bet_games)]

    try:
        snapshot_id = await persist_activation_snapshot(
            client,
            headers,
            recommendation_product_id=final_product_id,
            strategy_version=STRATEGY_VERSION,
            recommendation_product_explanation_id=explanation_id_by_product.get(final_product_id),
        )
        await persist_lifecycle_event(client, headers, recommendation_product_id=final_product_id, event_type="ACTIVATED")

        if decision.outcome == "bankroll_preservation":
            # Freezes the exact per-game no_bet products that
            # constituted this slate-level decision (Decision AR) --
            # membership failures here mean the manifest can't honestly
            # represent what composed this activation, so they fail the
            # whole snapshot rather than being isolated per-source.
            for source_product_id in no_bet_product_ids:
                await persist_activation_snapshot_source_product(
                    client, headers, activation_snapshot_id=snapshot_id, source_recommendation_product_id=source_product_id
                )
        result.snapshots.append(
            ActivationSnapshotResult(product_id=final_product_id, status="generated", activation_snapshot_id=snapshot_id)
        )
    except Exception as exc:  # noqa: BLE001
        result.snapshots.append(ActivationSnapshotResult(product_id=final_product_id, status="failed", error=str(exc)))
        return result

    if decision.outcome == "bankroll_preservation":
        return result

    # decision.outcome in ("single", "multiple_singles") -- freeze leg
    # membership + activation-time order (Decision AQ). Never
    # reconstructed later by rerunning Strategy ranking.
    leg_rows = await read_legs_for_product(client, headers, recommendation_product_id=final_product_id)
    legs_by_candidate_key = {row["candidate_key"]: row["id"] for row in leg_rows}
    for leg_order, candidate in enumerate(decision.legs, start=1):
        leg_id = legs_by_candidate_key.get(candidate.candidate_key)
        if leg_id is None:
            result.legs.append(
                ActivationSnapshotLegResult(
                    activation_snapshot_id=snapshot_id,
                    candidate_key=candidate.candidate_key,
                    status="failed",
                    error=f"no recommendation_legs row found for candidate_key={candidate.candidate_key!r}",
                )
            )
            continue
        try:
            await persist_activation_snapshot_leg(
                client, headers, activation_snapshot_id=snapshot_id, recommendation_leg_id=leg_id, leg_order=leg_order
            )
            result.legs.append(
                ActivationSnapshotLegResult(activation_snapshot_id=snapshot_id, candidate_key=candidate.candidate_key, status="generated")
            )
        except Exception as exc:  # noqa: BLE001 -- deliberate: one leg's failure never blocks the rest
            result.legs.append(
                ActivationSnapshotLegResult(
                    activation_snapshot_id=snapshot_id, candidate_key=candidate.candidate_key, status="failed", error=str(exc)
                )
            )

    return result
