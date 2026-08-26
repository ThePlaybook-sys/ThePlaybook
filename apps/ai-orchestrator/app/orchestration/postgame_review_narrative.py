"""Milestone 5.4's Postgame Review narrative orchestration (Decision BU).
Strictly downstream of an already-persisted, already-final
`recommendation_product_grade_events` row -- this module never computes,
receives, or has any write path to a grade, EV, confidence, or historical
Explainability field. Its only two writes are `outcome_summary`/
`why_it_won_or_lost`/`learning_notes` (LLM narrative, via
`PostgameReviewNarrativeOutput`) and `correct_agents`/
`underperforming_agents`/`factual_deltas` (deterministic, computed by
`app.features.postgame_review` and merely relayed here).

**Execution order is enforced by data dependency, not convention**: this
module's only entry point, `generate_and_persist_postgame_review`,
REQUIRES an already-graded `product_grade_event_id` as an argument --
there is no code path here that could run before grading, because there
is nothing to narrate without one.

**Routing-rule-gated, not hardcoded** (mirrors every other agent call in
this codebase): the caller supplies `routing_rules` (from
`app.persistence.model_config.list_active_model_routing_rules`), and this
module looks up `task_type="postgame_review_narrative"`. No such row
exists in `model_routing_rules` yet as of Milestone 5.4 (flagged in the
completion report as a required pre-live-narrative seed, exactly the
same class of gap Milestone 4.8-6 closed for the 12 committee agents'
`prompt_registry` rows) -- when absent, narrative generation is skipped
outright (`status="skipped_no_routing_rule"`), never silently defaulted
to some guessed model. **Zero live OpenAI/Anthropic calls are possible
without that row existing AND a real `ANTHROPIC_API_KEY`/
`OPENAI_API_KEY` being configured** -- both conditions are outside this
milestone's own control and explicitly not created by it."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.features.consensus import resolve_candidate_direction
from app.features.postgame_review import (
    POSTGAME_REVIEW_VERSION,
    PostgameReviewNarrativeOutput,
    build_factual_deltas,
    classify_agent_correctness,
    realized_direction,
)
from app.models.retry_policy import RetryEngine
from app.models.router import AdapterRegistry, ModelRouter
from app.models.types import ModelMessage, ModelRequest
from app.persistence.consensus_snapshots import read_game_level_agent_outputs
from app.persistence.games import get_game_for_grading
from app.persistence.postgame_grading import (
    read_latest_leg_grade_event,
    read_recommendation_legs_by_product,
    persist_postgame_review,
)

_TASK_TYPE = "postgame_review_narrative"


@dataclass
class PostgameReviewResult:
    recommendation_product_id: str
    status: str  # "generated" | "skipped_no_routing_rule" | "skipped_not_applicable" | "failed"
    postgame_review_id: str | None = None
    error: str | None = None


def _build_narrative_request(*, outcome: str, correct_agents: list[str] | None, underperforming_agents: list[str] | None, decision) -> ModelRequest:
    facts = (
        f"Deterministic grading outcome: {outcome}. "
        f"Agents whose directional call matched the actual result: {correct_agents or 'none identified'}. "
        f"Agents whose directional call opposed the actual result: {underperforming_agents or 'none identified'}."
    )
    return ModelRequest(
        model=decision.primary_model,
        messages=[
            ModelMessage(
                role="system",
                content=(
                    "You write a short, factual postgame review narrative for a sports betting "
                    "recommendation. You are given the ALREADY-DECIDED deterministic outcome and "
                    "already-computed factual evidence. You must never contradict, restate as "
                    "uncertain, or imply a different outcome than the one given. You must never "
                    "assert that any single factor CAUSED the result -- describe context, not causation."
                ),
            ),
            ModelMessage(role="user", content=facts),
        ],
        task_type=_TASK_TYPE,
        agent_name="postgame_review_narrative",
        correlation_id=outcome,
        response_model=PostgameReviewNarrativeOutput,
    )


async def _classify_agents_for_product(
    client: httpx.AsyncClient, headers: dict, *, recommendation_product_id: str, grading_version: str
) -> tuple[list[str] | None, list[str] | None]:
    """Union across every leg's own objective classification (Milestone
    5.4 MVP aggregation choice, flagged in the completion report): an
    agent lands in `correct_agents` if it was objectively right on AT
    LEAST ONE leg, `underperforming_agents` if objectively wrong on at
    least one -- it can appear in both for a `multiple_singles` product
    whose legs disagreed. Never majority- or confidence-based (Decision
    BT); every entry traces to a real per-leg directional comparison."""
    legs = await read_recommendation_legs_by_product(client, headers, recommendation_product_id=recommendation_product_id)
    all_correct: set[str] = set()
    all_underperforming: set[str] = set()
    any_classified = False
    for leg in legs:
        grade_event = await read_latest_leg_grade_event(
            client, headers, recommendation_leg_id=leg["id"], grading_version=grading_version
        )
        if grade_event is None:
            continue
        game = await get_game_for_grading(client, headers, game_id=leg["game_id"])
        if game is None:
            continue
        try:
            candidate_direction = resolve_candidate_direction(
                market_type=leg["market_type"], selection=leg["selection"], home_team=game["home_team"], away_team=game["away_team"]
            )
        except Exception:  # noqa: BLE001 -- an unresolvable leg simply isn't classified
            continue
        realized = realized_direction(candidate_direction=candidate_direction, outcome=grade_event["outcome"])
        if realized is None:
            continue
        agent_rows = await read_game_level_agent_outputs(client, headers, recommendation_id=leg["recommendation_id"])
        correct, underperforming = classify_agent_correctness(agent_rows, realized_direction_value=realized)
        if correct is None:
            continue
        any_classified = True
        all_correct.update(correct)
        all_underperforming.update(underperforming or [])

    if not any_classified:
        return None, None
    return sorted(all_correct), sorted(all_underperforming)


async def generate_and_persist_postgame_review(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_product_id: str,
    product_grade_event_id: str,
    grading_version: str,
    outcome: str,
    routing_rules: dict[str, dict],
    adapter_registry: AdapterRegistry,
    model_providers: dict[str, str] | None = None,
    retry_engine: RetryEngine | None = None,
) -> PostgameReviewResult:
    """Generates and persists one Postgame Review narrative row for an
    ALREADY-graded product. `outcome` is the grade this function narrates
    -- never recomputed here. NOT_APPLICABLE/PENDING_MISSING_DATA
    products are skipped outright (nothing meaningful to narrate about
    an abstention or an incomplete grade)."""
    if outcome in ("NOT_APPLICABLE", "PENDING_MISSING_DATA"):
        return PostgameReviewResult(recommendation_product_id=recommendation_product_id, status="skipped_not_applicable")

    routing_rule = routing_rules.get(_TASK_TYPE)
    if routing_rule is None:
        return PostgameReviewResult(recommendation_product_id=recommendation_product_id, status="skipped_no_routing_rule")

    try:
        correct_agents, underperforming_agents = await _classify_agents_for_product(
            client, headers, recommendation_product_id=recommendation_product_id, grading_version=grading_version
        )
        factual_deltas = build_factual_deltas()

        decision = ModelRouter.route(routing_rule, model_providers=model_providers)
        primary = adapter_registry.get(decision.primary_provider)
        fallback = adapter_registry.get(decision.fallback_provider) if decision.fallback_provider else None
        engine = retry_engine or RetryEngine()
        request = _build_narrative_request(
            outcome=outcome, correct_agents=correct_agents, underperforming_agents=underperforming_agents, decision=decision
        )
        response = await engine.execute(
            primary=primary,
            primary_provider=decision.primary_provider,
            request=request,
            fallback=fallback,
            fallback_provider=decision.fallback_provider,
            fallback_model=decision.fallback_model,
        )
        narrative: PostgameReviewNarrativeOutput = response.parsed

        review_id = await persist_postgame_review(
            client,
            headers,
            recommendation_product_id=recommendation_product_id,
            product_grade_event_id=product_grade_event_id,
            grading_version=grading_version,
            postgame_review_version=POSTGAME_REVIEW_VERSION,
            outcome_summary=narrative.outcome_summary,
            why_it_won_or_lost=narrative.why_it_won_or_lost,
            factual_deltas=factual_deltas,
            correct_agents=correct_agents,
            underperforming_agents=underperforming_agents,
            learning_notes=narrative.learning_notes,
        )
        return PostgameReviewResult(recommendation_product_id=recommendation_product_id, status="generated", postgame_review_id=review_id)
    except Exception as exc:  # noqa: BLE001 -- deliberate: one product's narrative failing never blocks another's
        return PostgameReviewResult(recommendation_product_id=recommendation_product_id, status="failed", error=str(exc))
