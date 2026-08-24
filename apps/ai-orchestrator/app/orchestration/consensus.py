"""Ties the deterministic Consensus Engine, Meta Agent, and conditional
Elite second-pass reconciliation together for one candidate (Milestone
4.7).

**Consensus is candidate-specific (Decision I), never collapsed into one
game-level value.** Called once per `(recommendation_id, candidate)`
pair -- the same game-level fan-out outputs (read back from persistence,
Decision J) are re-evaluated against a different `candidate_direction`
each time, producing an independent `consensus_snapshots` row per
candidate.

**Meta Agent always runs when a consensus number exists to review; Elite
reconciliation runs only when triggered.** A failed Meta Agent LLM call
degrades to a `0.0` adjustment (no review occurred, no adjustment
applied) rather than blocking consensus persistence entirely --
unlike Milestone 4.6's Probability Modeling, Meta Agent is a QC layer
on top of already-valid deterministic math, not a prerequisite for it.

**Elite second-pass evidence, per Volume 4 Section 4.3's own literal
text:** the same already-persisted fan-out findings the Meta Agent saw,
plus the Meta Agent's own `reasoning` field -- the fan-out committee is
never re-run.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from app.agents.committee_context import ParticipationMetadata, participation_metadata_to_json
from app.agents.consensus_review_context import ConsensusReviewContext
from app.agents.elite_reconciliation_agent import EliteReconciliationAgent
from app.features.candidate import MarketCandidate, candidate_key as compute_candidate_key
from app.features.consensus import (
    ConsensusResult,
    apply_confidence_adjustment,
    compute_consensus,
    is_below_confidence_floor,
    resolve_candidate_direction,
    should_trigger_elite_second_pass,
)
from app.agents.meta_agent import MetaAgent
from app.models.retry_policy import RetryEngine
from app.models.router import AdapterRegistry, ModelRouter
from app.models.types import ModelRequest
from app.persistence.consensus_snapshots import persist_consensus_snapshot, read_game_level_agent_outputs
from app.persistence.model_config import resolve_active_prompt
from app.persistence.subscriptions import read_subscription_tier

@dataclass
class ReviewAgentRunResult:
    agent_name: str
    status: str  # "success" | "failed"
    output: object | None = None
    error: str | None = None
    prompt_name: str | None = None
    prompt_version: int | None = None


async def _run_review_agent(
    agent, context: ConsensusReviewContext, *, client, headers: dict, routing_rule: dict, model_providers, adapter_registry: AdapterRegistry, retry_engine: RetryEngine
) -> ReviewAgentRunResult:
    """Never raises -- mirrors `app.orchestration.fanout.run_agent`'s
    isolation guarantee exactly, including Milestone 4.8's
    `resolve_active_prompt` call at this orchestration boundary. Neither
    Meta Agent's nor Elite Reconciliation Agent's output is persisted as
    a `recommendation_agent_outputs` row (unchanged, out of Milestone
    4.8's approved scope) -- `prompt_name`/`.prompt_version` are still
    resolved and returned here for consistency/testability, they simply
    have no persisted destination yet."""
    try:
        resolved_prompt = await resolve_active_prompt(client, headers, prompt_name=agent.agent_name)
        decision = ModelRouter.route(routing_rule, model_providers=model_providers)
        primary = adapter_registry.get(decision.primary_provider)
        fallback = adapter_registry.get(decision.fallback_provider) if decision.fallback_provider else None
        request = ModelRequest(
            model=decision.primary_model,
            messages=agent.build_messages(context, system_prompt=resolved_prompt.prompt_text),
            task_type=agent.task_type,
            agent_name=agent.agent_name,
            correlation_id=context.correlation_id,
            response_model=agent.response_model,
        )
        response = await retry_engine.execute(
            primary=primary, primary_provider=decision.primary_provider, request=request, fallback=fallback, fallback_provider=decision.fallback_provider
        )
    except Exception as exc:  # noqa: BLE001 -- deliberate: isolate this one review agent
        return ReviewAgentRunResult(agent_name=agent.agent_name, status="failed", error=str(exc))
    return ReviewAgentRunResult(
        agent_name=agent.agent_name,
        status="success",
        output=response.parsed,
        prompt_name=resolved_prompt.prompt_name,
        prompt_version=resolved_prompt.version,
    )


@dataclass
class ConsensusRunResult:
    status: str  # "no_consensus" | "computed"
    consensus: ConsensusResult | None
    meta_result: ReviewAgentRunResult | None
    elite_result: ReviewAgentRunResult | None
    second_pass_triggered: bool
    final_aggregate_confidence: float | None
    below_confidence_floor: bool | None


async def run_candidate_consensus(
    client,
    headers: dict,
    *,
    recommendation_id: str,
    correlation_id: str,
    game_id: str,
    candidate: MarketCandidate,
    home_team: str,
    away_team: str,
    participation: ParticipationMetadata,
    routing_rules: dict[str, dict],
    adapter_registry: AdapterRegistry,
    model_providers: dict[str, str] | None = None,
    retry_engine: RetryEngine | None = None,
    user_id: str | None = None,
) -> ConsensusRunResult:
    """Computes and persists one candidate's consensus. `home_team`/
    `away_team` resolve the candidate's own direction (Decision I) --
    never inferred from array position or text ordering. `user_id`,
    when given, is the ONLY way Elite second-pass can ever trigger; its
    absence (the default) means the trigger check is skipped entirely,
    never defaulted to elevated treatment."""
    retry_engine = retry_engine or RetryEngine()

    candidate_direction = resolve_candidate_direction(
        market_type=candidate.market_type, selection=candidate.selection, home_team=home_team, away_team=away_team
    )
    agent_rows = await read_game_level_agent_outputs(client, headers, recommendation_id=recommendation_id)
    consensus = compute_consensus(agent_rows, candidate_direction=candidate_direction)

    if consensus.aggregate_confidence is None:
        return ConsensusRunResult(
            status="no_consensus",
            consensus=consensus,
            meta_result=None,
            elite_result=None,
            second_pass_triggered=False,
            final_aggregate_confidence=None,
            below_confidence_floor=None,
        )

    candidate_key_value = compute_candidate_key(candidate)
    review_context = ConsensusReviewContext(
        game_id=game_id,
        correlation_id=correlation_id,
        candidate_key=candidate_key_value,
        agent_findings=tuple(agent_rows),
        aggregate_confidence=consensus.aggregate_confidence,
        agreement_variance=consensus.agreement_variance,
        participation=participation,
    )

    model_routing_used: dict[str, str] = {}

    meta_agent = MetaAgent()
    meta_result = await _run_review_agent(
        meta_agent,
        review_context,
        client=client,
        headers=headers,
        routing_rule=routing_rules[meta_agent.task_type],
        model_providers=model_providers,
        adapter_registry=adapter_registry,
        retry_engine=retry_engine,
    )
    model_routing_used[meta_agent.agent_name] = routing_rules[meta_agent.task_type]["primary_model"]
    meta_adjustment = meta_result.output.confidence_adjustment if meta_result.status == "success" else 0.0
    after_meta = apply_confidence_adjustment(consensus.aggregate_confidence, meta_adjustment)

    second_pass_triggered = False
    elite_result = None
    final_aggregate_confidence = after_meta

    tier = await read_subscription_tier(client, headers, user_id=user_id) if user_id is not None else None
    if should_trigger_elite_second_pass(consensus.agreement_variance, tier):
        second_pass_triggered = True
        meta_reasoning = meta_result.output.reasoning if meta_result.status == "success" else None
        elite_context = dataclasses.replace(review_context, meta_reasoning=meta_reasoning)
        elite_agent = EliteReconciliationAgent()
        elite_result = await _run_review_agent(
            elite_agent,
            elite_context,
            client=client,
            headers=headers,
            routing_rule=routing_rules[elite_agent.task_type],
            model_providers=model_providers,
            adapter_registry=adapter_registry,
            retry_engine=retry_engine,
        )
        model_routing_used[elite_agent.agent_name] = routing_rules[elite_agent.task_type]["primary_model"]
        elite_adjustment = elite_result.output.confidence_adjustment if elite_result.status == "success" else 0.0
        final_aggregate_confidence = apply_confidence_adjustment(after_meta, elite_adjustment)

    below_confidence_floor = is_below_confidence_floor(final_aggregate_confidence)

    await persist_consensus_snapshot(
        client,
        headers,
        recommendation_id=recommendation_id,
        candidate_key=candidate_key_value,
        aggregate_confidence=consensus.aggregate_confidence,
        final_aggregate_confidence=final_aggregate_confidence,
        agreement_variance=consensus.agreement_variance,
        below_confidence_floor=below_confidence_floor,
        participation_metadata=participation_metadata_to_json(participation),
        model_routing_used=model_routing_used,
        second_pass_triggered=second_pass_triggered,
    )

    return ConsensusRunResult(
        status="computed",
        consensus=consensus,
        meta_result=meta_result,
        elite_result=elite_result,
        second_pass_triggered=second_pass_triggered,
        final_aggregate_confidence=final_aggregate_confidence,
        below_confidence_floor=below_confidence_floor,
    )
