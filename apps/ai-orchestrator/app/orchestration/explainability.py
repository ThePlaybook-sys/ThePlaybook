"""Milestone 5.2 -- ties the deterministic Explainability domain logic
(`app.features.explainability`) to persistence
(`app.persistence.recommendation_explanations`) for one already-persisted
`SlateStrategyResult`. Reachable only from `app.orchestration.
strategy_finalize.finalize_slate_strategy`, called immediately after
`persist_strategy_decision` (Milestone 5.1) succeeds -- preserving the
corrected pipeline order: Phase 4 Analysis -> Strategy Engine -> product
activation -> Explainability.

**Read-only with respect to every decision.** This module reads back
already-persisted Phase 4/Milestone 5.1 rows and an already-computed
`SlateStrategyResult`; it writes only to the two new Milestone 5.2
tables. It never calls `app.features.strategy` again, never issues a
second `persist_strategy_decision` call, and has no code path that could
write to `recommendation_products`/`recommendation_legs`/
`recommendation_type`/any EV/confidence/stake column. Explaining a
decision and making one are structurally different operations in this
module -- there is no shared function between them.

**Per-product and per-leg failure isolation**, matching every other
per-unit isolation boundary already established in this codebase
(Milestone 4.9's per-candidate/per-user pattern): one product's or one
leg's explanation failing to generate never blocks the others, and never
raises out of `generate_and_persist_explanations` itself -- every
attempt, success or failure, is recorded in the returned result.

**Correlating already-created rows without touching frozen Milestone 5.1
code.** `persist_strategy_decision`'s own documented return contract --
"one `no_bet` product per no_bet game_decision, in `game_decisions`
order, followed by exactly one further product for the slate's overall
outcome" -- is relied on here to map `created_product_ids` back to the
`GameDecision`/`SlateStrategyResult` objects that produced them, and
`read_legs_for_product` (new, Milestone 5.2) discovers each leg's id by
reading back `recommendation_legs` and matching on `candidate_key` --
neither requires changing `persist_strategy_decision`'s signature or
behavior at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.features.consensus import resolve_candidate_direction
from app.features.explainability import (
    EXPLAINABILITY_VERSION,
    build_biggest_risks,
    build_contributing_agents,
    build_data_limitations,
    build_strongest_evidence,
    build_why_not_other_shapes,
    build_why_selected,
    build_why_this_shape,
    contributing_agents_to_json,
    rejected_alternatives_to_json,
    select_would_change_mind_if,
)
from app.features.strategy import EvaluatedCandidate, GameDecision, RejectionReason, SlateStrategyResult
from app.persistence.consensus_snapshots import read_game_level_agent_outputs
from app.persistence.games import get_game
from app.persistence.recommendation_explanations import (
    persist_leg_explanation,
    persist_product_explanation,
    read_candidate_level_agent_output,
    read_legs_for_product,
    read_participation_metadata,
)


@dataclass
class ProductExplanationResult:
    product_id: str
    recommendation_type: str
    status: str  # "generated" | "failed"
    explanation_id: str | None = None
    error: str | None = None


@dataclass
class LegExplanationResult:
    leg_id: str
    candidate_key: str
    status: str  # "generated" | "failed"
    explanation_id: str | None = None
    error: str | None = None


@dataclass
class ExplainabilityResult:
    products: list[ProductExplanationResult] = field(default_factory=list)
    legs: list[LegExplanationResult] = field(default_factory=list)


def _no_bet_game_decisions(decision: SlateStrategyResult) -> list[GameDecision]:
    return [gd for gd in decision.game_decisions if gd.outcome == "no_bet"]


async def _explain_no_bet_product(
    client: httpx.AsyncClient, headers: dict, *, product_id: str, game_decision: GameDecision
) -> ProductExplanationResult:
    participation = await read_participation_metadata(client, headers, recommendation_id=game_decision.recommendation_id)
    explanation_id = await persist_product_explanation(
        client,
        headers,
        recommendation_product_id=product_id,
        why_this_shape=build_why_this_shape("no_bet"),
        why_not_other_shapes=build_why_not_other_shapes("no_bet"),
        rejected_alternatives=rejected_alternatives_to_json(list(game_decision.rejected)),
        data_limitations=build_data_limitations(participation),
        explainability_version=EXPLAINABILITY_VERSION,
    )
    return ProductExplanationResult(product_id=product_id, recommendation_type="no_bet", status="generated", explanation_id=explanation_id)


async def _explain_bankroll_preservation_product(
    client: httpx.AsyncClient, headers: dict, *, product_id: str, decision: SlateStrategyResult
) -> ProductExplanationResult:
    explanation_id = await persist_product_explanation(
        client,
        headers,
        recommendation_product_id=product_id,
        why_this_shape=build_why_this_shape("bankroll_preservation", game_count=len(decision.game_decisions)),
        why_not_other_shapes=build_why_not_other_shapes("bankroll_preservation"),
        # Per-game detail already lives on each sibling no_bet product
        # (reachable via the same master_refresh_run_id) -- never
        # duplicated here.
        rejected_alternatives=[],
        data_limitations=build_data_limitations(None),
        explainability_version=EXPLAINABILITY_VERSION,
    )
    return ProductExplanationResult(
        product_id=product_id, recommendation_type="bankroll_preservation", status="generated", explanation_id=explanation_id
    )


async def _explain_leg(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    leg_id: str,
    candidate: EvaluatedCandidate,
    game_decision: GameDecision,
    rank_position: int,
    total_qualifying: int,
) -> LegExplanationResult:
    game = await get_game(client, headers, game_id=candidate.game_id)
    direction = resolve_candidate_direction(
        market_type=candidate.market_type,
        selection=candidate.selection,
        home_team=game["home_team"],
        away_team=game["away_team"],
    )
    agent_rows = await read_game_level_agent_outputs(client, headers, recommendation_id=candidate.recommendation_id)
    contributions = build_contributing_agents(agent_rows, candidate_direction=direction)
    strongest_evidence = build_strongest_evidence(contributions)
    would_change_mind_if = select_would_change_mind_if(agent_rows, candidate_direction=direction)

    risk_raw_output = await read_candidate_level_agent_output(
        client,
        headers,
        recommendation_id=candidate.recommendation_id,
        candidate_key=candidate.candidate_key,
        agent_name="risk_manager_agent",
    )
    biggest_risks = build_biggest_risks(risk_raw_output)

    conflict_losers = [
        r
        for r in game_decision.rejected
        if r.reasons == (RejectionReason.LOST_SAME_MARKET_CONFLICT,) and r.candidate.market_type == candidate.market_type
    ]
    why_selected = build_why_selected(
        candidate,
        rank_position=rank_position,
        total_qualifying=total_qualifying,
        beat_same_market_conflict=bool(conflict_losers),
    )

    explanation_id = await persist_leg_explanation(
        client,
        headers,
        recommendation_leg_id=leg_id,
        why_selected=why_selected,
        strongest_evidence=strongest_evidence,
        contributing_agents=contributing_agents_to_json(contributions),
        biggest_risks=biggest_risks,
        rejected_alternatives=rejected_alternatives_to_json(conflict_losers),
        would_change_mind_if=would_change_mind_if,
        explainability_version=EXPLAINABILITY_VERSION,
    )
    return LegExplanationResult(
        leg_id=leg_id, candidate_key=candidate.candidate_key, status="generated", explanation_id=explanation_id
    )


async def generate_and_persist_explanations(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    decision: SlateStrategyResult,
    created_product_ids: list[str],
) -> ExplainabilityResult:
    """`created_product_ids` must be `persist_strategy_decision`'s own
    return value for this exact `decision` -- relied on for its documented
    order (see module docstring) to correlate ids back to game/slate
    outcomes without re-deriving or re-deciding anything."""
    result = ExplainabilityResult()

    no_bet_games = _no_bet_game_decisions(decision)
    for product_id, game_decision in zip(created_product_ids, no_bet_games):
        try:
            result.products.append(await _explain_no_bet_product(client, headers, product_id=product_id, game_decision=game_decision))
        except Exception as exc:  # noqa: BLE001 -- deliberate: one product's failure never blocks the rest
            result.products.append(
                ProductExplanationResult(product_id=product_id, recommendation_type="no_bet", status="failed", error=str(exc))
            )

    if len(created_product_ids) <= len(no_bet_games):
        return result
    final_product_id = created_product_ids[len(no_bet_games)]

    if decision.outcome == "bankroll_preservation":
        try:
            result.products.append(
                await _explain_bankroll_preservation_product(client, headers, product_id=final_product_id, decision=decision)
            )
        except Exception as exc:  # noqa: BLE001
            result.products.append(
                ProductExplanationResult(
                    product_id=final_product_id, recommendation_type="bankroll_preservation", status="failed", error=str(exc)
                )
            )
        return result

    # decision.outcome in ("single", "multiple_singles") -- a leg-bearing product.
    game_decisions_by_game_id = {gd.game_id: gd for gd in decision.game_decisions}
    rank_by_candidate_key = {c.candidate_key: i + 1 for i, c in enumerate(decision.legs)}
    total_qualifying = len(decision.legs)

    try:
        leg_rows = await read_legs_for_product(client, headers, recommendation_product_id=final_product_id)
        legs_by_candidate_key = {row["candidate_key"]: row["id"] for row in leg_rows}
        explanation_id = await persist_product_explanation(
            client,
            headers,
            recommendation_product_id=final_product_id,
            why_this_shape=build_why_this_shape(decision.outcome, leg_count=len(decision.legs)),
            why_not_other_shapes=build_why_not_other_shapes(decision.outcome),
            rejected_alternatives=[],
            data_limitations=build_data_limitations(
                await read_participation_metadata(client, headers, recommendation_id=decision.legs[0].recommendation_id)
                if decision.outcome == "single"
                else None
            ),
            explainability_version=EXPLAINABILITY_VERSION,
        )
        result.products.append(
            ProductExplanationResult(
                product_id=final_product_id, recommendation_type=decision.outcome, status="generated", explanation_id=explanation_id
            )
        )
    except Exception as exc:  # noqa: BLE001
        result.products.append(
            ProductExplanationResult(product_id=final_product_id, recommendation_type=decision.outcome, status="failed", error=str(exc))
        )
        return result

    for candidate in decision.legs:
        leg_id = legs_by_candidate_key.get(candidate.candidate_key)
        if leg_id is None:
            result.legs.append(
                LegExplanationResult(
                    leg_id="", candidate_key=candidate.candidate_key, status="failed",
                    error=f"no recommendation_legs row found for candidate_key={candidate.candidate_key!r}",
                )
            )
            continue
        try:
            result.legs.append(
                await _explain_leg(
                    client,
                    headers,
                    leg_id=leg_id,
                    candidate=candidate,
                    game_decision=game_decisions_by_game_id[candidate.game_id],
                    rank_position=rank_by_candidate_key[candidate.candidate_key],
                    total_qualifying=total_qualifying,
                )
            )
        except Exception as exc:  # noqa: BLE001 -- deliberate: one leg's failure never blocks the rest
            result.legs.append(LegExplanationResult(leg_id=leg_id, candidate_key=candidate.candidate_key, status="failed", error=str(exc)))

    return result
