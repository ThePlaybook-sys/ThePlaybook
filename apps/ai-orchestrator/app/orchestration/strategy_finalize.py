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
for omitting such games from the `games` list it sends here."""
from __future__ import annotations

import httpx

from app.features.strategy import GameCandidates, SlateStrategyResult, compute_strategy_decision
from app.persistence.recommendation_products import persist_strategy_decision


async def finalize_slate_strategy(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    master_refresh_run_id: str,
    games: list[GameCandidates],
) -> tuple[SlateStrategyResult, list[str]]:
    """Computes and persists the Strategy Engine's decision for one whole
    slate. Returns the pure decision alongside the list of created
    `recommendation_products.id` values, in write order."""
    decision = compute_strategy_decision(games)
    created_ids = await persist_strategy_decision(
        client, headers, master_refresh_run_id=master_refresh_run_id, decision=decision
    )
    return decision, created_ids
