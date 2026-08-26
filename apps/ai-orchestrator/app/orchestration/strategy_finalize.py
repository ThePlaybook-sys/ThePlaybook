"""Milestone 5.1 -- ties the Strategy Engine (`app.features.strategy`) to
persistence (`app.persistence.recommendation_products`) for one whole
slate.

Reachable only via a dedicated internal endpoint (`app.main`), called by
`apps/workers` exactly once per Recommendation Worker cycle, AFTER every
eligible game's `run-game` call has completed -- Decision AB requires
seeing the whole slate before `bankroll_preservation` can honestly be
decided; a per-game call can never make that determination alone.

`apps/workers` relays each game's `strategy_input` fields (already
computed, in-memory, during that game's own `run-game` call) unmodified --
this module never recomputes EV/confidence/candidate market fields
itself, it only re-assembles the already-frozen values `apps/workers`
forwards into `app.features.strategy.GameCandidates`/`EvaluatedCandidate`
objects and calls the pure decision function.

Games that failed to dispatch entirely (game not found, transport
failure) are represented by their absence, never as `no_bet` -- `no_bet`
is a positive claim ("evaluated, nothing qualified"), which isn't true
for a game that was never evaluated at all. `apps/workers` is responsible
for omitting such games from the `games` list it sends here.

**Milestone 5.2 addition:** immediately after the Strategy decision is
persisted, `app.orchestration.explainability.generate_and_persist_explanations`
runs against it -- preserving the corrected pipeline order (Phase 4
Analysis -> Strategy Engine -> product activation -> Explainability).
Explanation generation never raises out of this function (every
product/leg failure is isolated and recorded in its own result, per
`app.orchestration.explainability`'s own docstring) -- an explanation
failure never un-persists or invalidates the Strategy decision that was
already committed.

**Milestone 5.3 addition:** immediately after Explainability runs,
`app.orchestration.time_machine.generate_activation_snapshots` runs
against the same decision/explanation results -- extending the pipeline
order once more (Phase 4 Analysis -> Strategy Engine -> Explainability ->
Time Machine activation snapshot). Same never-raises, per-unit-isolated
discipline as Explainability -- an activation-snapshot failure never
un-persists or hides the already-committed Strategy decision or
Explainability content."""
from __future__ import annotations

import httpx

from app.features.strategy import GameCandidates, SlateStrategyResult, compute_strategy_decision
from app.orchestration.explainability import ExplainabilityResult, generate_and_persist_explanations
from app.orchestration.time_machine import TimeMachineResult, generate_activation_snapshots
from app.persistence.recommendation_products import persist_strategy_decision


async def finalize_slate_strategy(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    master_refresh_run_id: str,
    games: list[GameCandidates],
) -> tuple[SlateStrategyResult, list[str], ExplainabilityResult, TimeMachineResult]:
    """Computes and persists the Strategy Engine's decision for one whole
    slate, generates and persists its Explainability, then its Time
    Machine activation snapshot. Returns the pure decision, the list of
    created `recommendation_products.id` values (in write order), the
    explanation generation result, and the activation-snapshot result."""
    decision = compute_strategy_decision(games)
    created_ids = await persist_strategy_decision(
        client, headers, master_refresh_run_id=master_refresh_run_id, decision=decision
    )
    explainability_result = await generate_and_persist_explanations(
        client, headers, decision=decision, created_product_ids=created_ids
    )
    time_machine_result = await generate_activation_snapshots(
        client, headers, decision=decision, created_product_ids=created_ids, explainability_result=explainability_result
    )
    return decision, created_ids, explainability_result, time_machine_result
