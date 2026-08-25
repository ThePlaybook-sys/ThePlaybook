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

**Milestone 4.9, Decision 2 -- Elite reconciliation decoupled from
entitlement lookup, split into three steps.** Pre-4.9, this module took
a single `user_id`, looked up ITS OWN subscription tier via
`read_subscription_tier`, and persisted exactly once per call -- meaning
two different Elite users viewing the SAME candidate this cycle would
each trigger their own Elite Reconciliation Agent call, redundantly
re-analyzing IDENTICAL evidence (Elite reconciliation reasoning depends
only on the candidate's own agent findings + Meta Agent's own reasoning,
never on which specific user is asking -- unlike Bankroll Coach, whose
output genuinely differs per user's bankroll). Mac's explicit shared-vs-
personalized breakdown: "Elite reconciliation is candidate-level
(computed at most once per candidate/cycle, reused across Elite users);
entitlement/tier controls triggering, not the underlying football
evidence."

The fix here is orchestration-level sequencing discipline, not a schema
change -- deliberately NOT adding a uniqueness constraint to
`consensus_snapshots` to enable an upsert/update-in-place, since the
existing schema migration
(`20260822153000_consensus_snapshots_candidate_and_final_confidence.sql`)
already documents "No uniqueness constraint... retry/versioning
semantics for a candidate-level consensus snapshot aren't designed yet
either" -- reversing that documented decision without Mac's explicit
sign-off would be exactly the "silently improvise past a real
Blueprint/reality conflict" CLAUDE.md rules out. Instead:

1. `run_shared_consensus` -- no user/tier concept at all. Computes
   consensus + always runs Meta Agent. Does NOT persist.
2. `run_elite_reconciliation` -- takes the ALREADY-RESOLVED `tier` for
   whichever Elite-tier user(s), if any, are requesting this candidate
   this cycle (resolved by the caller, e.g. the Milestone 4.9 top-level
   Recommendation Worker entry point, via `read_subscription_tier` --
   this module no longer calls it). The caller is responsible for
   invoking this AT MOST ONCE per candidate/cycle regardless of how many
   Elite users are viewing it -- exactly like `run_shared_candidate_chain`
   runs once per candidate regardless of how many users later call
   `run_bankroll_coach_step`. Does NOT persist.
3. `finalize_consensus` -- the single persistence call, made exactly
   once per candidate by the caller after both steps above have run
   (`elite=None` in the common case where no Elite user requested this
   candidate this cycle, or Elite reconciliation didn't trigger)."""
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
class SharedConsensusResult:
    """The candidate-level, user-independent half (Milestone 4.9,
    Decision 2) -- computed once per candidate, shared across every user
    who views it. `review_context` carries `meta_reasoning`-ready state
    forward for `run_elite_reconciliation` without re-fetching
    `recommendation_agent_outputs`."""

    status: str  # "no_consensus" | "computed"
    consensus: ConsensusResult | None
    meta_result: ReviewAgentRunResult | None
    review_context: ConsensusReviewContext | None
    after_meta_confidence: float | None
    model_routing_used: dict


@dataclass
class EliteReconciliationResult:
    """`triggered=False` covers both "not requested" (caller never even
    tried, `elite_result=None`) and "requested but the structural
    threshold/tier check didn't fire" -- distinguished only by whether
    the caller invoked this function at all, never by inspecting this
    result alone."""

    triggered: bool
    elite_result: ReviewAgentRunResult | None
    final_aggregate_confidence: float | None
    model_routing_used: dict


@dataclass
class ConsensusFinalizeResult:
    final_aggregate_confidence: float
    below_confidence_floor: bool
    second_pass_triggered: bool


async def run_shared_consensus(
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
) -> SharedConsensusResult:
    """Computes one candidate's consensus and always runs Meta Agent
    when a consensus number exists to review (Milestone 4.9, Decision 2:
    no user/tier concept at all -- entitlement is entirely
    `run_elite_reconciliation`'s concern). `home_team`/`away_team`
    resolve the candidate's own direction (Decision I) -- never inferred
    from array position or text ordering. Does NOT persist -- see this
    module's docstring for why."""
    retry_engine = retry_engine or RetryEngine()

    candidate_direction = resolve_candidate_direction(
        market_type=candidate.market_type, selection=candidate.selection, home_team=home_team, away_team=away_team
    )
    agent_rows = await read_game_level_agent_outputs(client, headers, recommendation_id=recommendation_id)
    consensus = compute_consensus(agent_rows, candidate_direction=candidate_direction)

    if consensus.aggregate_confidence is None:
        return SharedConsensusResult(
            status="no_consensus", consensus=consensus, meta_result=None, review_context=None, after_meta_confidence=None, model_routing_used={}
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
    meta_adjustment = meta_result.output.confidence_adjustment if meta_result.status == "success" else 0.0
    after_meta = apply_confidence_adjustment(consensus.aggregate_confidence, meta_adjustment)

    return SharedConsensusResult(
        status="computed",
        consensus=consensus,
        meta_result=meta_result,
        review_context=review_context,
        after_meta_confidence=after_meta,
        model_routing_used={meta_agent.agent_name: routing_rules[meta_agent.task_type]["primary_model"]},
    )


async def run_elite_reconciliation(
    shared: SharedConsensusResult,
    client,
    headers: dict,
    *,
    tier: str | None,
    routing_rules: dict[str, dict],
    adapter_registry: AdapterRegistry,
    model_providers: dict[str, str] | None = None,
    retry_engine: RetryEngine | None = None,
) -> EliteReconciliationResult:
    """Runs Elite second-pass reconciliation for one candidate, AT MOST
    ONCE per candidate/cycle -- the caller (e.g. the top-level
    Recommendation Worker entry point) resolves `tier` itself, once,
    representing whichever Elite-tier user(s) are requesting this
    candidate this cycle, and is responsible for calling this function
    at most once regardless of how many such users there are (Milestone
    4.9, Decision 2). `tier` is never looked up here -- this module has
    no user concept.

    A no-op (`triggered=False`, `final_aggregate_confidence` carried
    through unchanged from `shared`) when `shared.status != "computed"`
    (nothing to reconcile) or `should_trigger_elite_second_pass` doesn't
    fire for `shared.consensus.agreement_variance`/`tier`."""
    if shared.status != "computed":
        return EliteReconciliationResult(triggered=False, elite_result=None, final_aggregate_confidence=None, model_routing_used={})

    if not should_trigger_elite_second_pass(shared.consensus.agreement_variance, tier):
        return EliteReconciliationResult(
            triggered=False, elite_result=None, final_aggregate_confidence=shared.after_meta_confidence, model_routing_used={}
        )

    retry_engine = retry_engine or RetryEngine()
    meta_reasoning = shared.meta_result.output.reasoning if shared.meta_result.status == "success" else None
    elite_context = dataclasses.replace(shared.review_context, meta_reasoning=meta_reasoning)
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
    elite_adjustment = elite_result.output.confidence_adjustment if elite_result.status == "success" else 0.0
    final_aggregate_confidence = apply_confidence_adjustment(shared.after_meta_confidence, elite_adjustment)

    return EliteReconciliationResult(
        triggered=True,
        elite_result=elite_result,
        final_aggregate_confidence=final_aggregate_confidence,
        model_routing_used={elite_agent.agent_name: routing_rules[elite_agent.task_type]["primary_model"]},
    )


async def finalize_consensus(
    client,
    headers: dict,
    *,
    recommendation_id: str,
    candidate: MarketCandidate,
    participation: ParticipationMetadata,
    shared: SharedConsensusResult,
    elite: EliteReconciliationResult | None = None,
) -> ConsensusFinalizeResult:
    """The single persistence call for one candidate's consensus --
    callers make this call EXACTLY ONCE per candidate/cycle, after
    `run_shared_consensus` and (if it ran at all) `run_elite_
    reconciliation` have both already completed. `shared.status` must be
    `"computed"` -- callers never finalize a `"no_consensus"` result (no
    row to write, per this module's original `consensus_snapshots`
    persistence contract)."""
    final_aggregate_confidence = elite.final_aggregate_confidence if elite is not None else shared.after_meta_confidence
    below_confidence_floor = is_below_confidence_floor(final_aggregate_confidence)
    second_pass_triggered = elite.triggered if elite is not None else False
    model_routing_used = {**shared.model_routing_used, **(elite.model_routing_used if elite is not None else {})}

    await persist_consensus_snapshot(
        client,
        headers,
        recommendation_id=recommendation_id,
        candidate_key=compute_candidate_key(candidate),
        aggregate_confidence=shared.consensus.aggregate_confidence,
        final_aggregate_confidence=final_aggregate_confidence,
        agreement_variance=shared.consensus.agreement_variance,
        below_confidence_floor=below_confidence_floor,
        participation_metadata=participation_metadata_to_json(participation),
        model_routing_used=model_routing_used,
        second_pass_triggered=second_pass_triggered,
    )

    return ConsensusFinalizeResult(
        final_aggregate_confidence=final_aggregate_confidence,
        below_confidence_floor=below_confidence_floor,
        second_pass_triggered=second_pass_triggered,
    )
