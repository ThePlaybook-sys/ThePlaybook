"""Ties one full recommendation-analysis cycle together (Milestone 4.5):
build the shared `AgentContext`, create the `recommendations` cycle row
(Option C), run the fan-out, and persist exactly one
`recommendation_agent_outputs` row per successful agent -- no row for a
failed one.

**Idempotency (Decision A, A1 approved for 4.5):** `create_recommendation_cycle`
is called exactly once per call to `run_recommendation_cycle`, and the
single `recommendation_id` it returns is reused for every output write in
this run -- proven by construction (one local variable, threaded through),
not by any DB-level dedup. A crashed-and-retried call to
`run_recommendation_cycle` may produce a second cycle row; this is an
accepted 4.5 limitation (see `app.persistence.recommendations` module
docstring), carried forward as a required Milestone 4.9 checkpoint.

**consensus_snapshots is explicitly out of scope here** -- this module
stops at persisting individual agent outputs; consensus math belongs to
the not-yet-built Consensus Engine milestone.

**Milestone 4.6 addition, decoupled Milestone 4.9 (Decision 2):**
`run_candidate_evaluation` runs the SHARED half of the Decision &
Advisory chain (Probability Modeling -> Expected Value -> Risk Manager)
for one `MarketCandidate` against an already-existing `recommendation_id`
-- it never creates a `recommendations` row itself, and it has no user
concept at all. One cycle (`run_recommendation_cycle`) may have
`run_candidate_evaluation` called multiple times, once per candidate
evaluated within it (Decision G: `candidate_key` identifies the wager
being evaluated; `recommendation_id` identifies the overall analysis
cycle -- not interchangeable).

`run_bankroll_coach_evaluation` is the separate, per-user half -- callable
zero or more times against the SAME already-evaluated candidate (one call
per user who actually needs a stake number), reusing `run_candidate_
evaluation`'s already-computed probability/EV rather than re-running
those model calls. This split is the direct fix for the pre-4.9 coupling
that re-ran Probability/EV/Risk once per user for no reason."""
from __future__ import annotations

import dataclasses

import httpx

from app.agents.base_agent import ContextDataAgent
from app.agents.committee_context import ParticipationMetadata, SequentialDecisionContext
from app.agents.context import build_agent_context
from app.agents.probability_output import ProbabilityModelOutput
from app.features.candidate import MarketCandidate, candidate_key as _candidate_key
from app.models.retry_policy import RetryEngine
from app.models.router import AdapterRegistry
from app.orchestration.fanout import FanOutResult, run_fan_out
from app.orchestration.sequential import (
    BankrollCoachResult,
    SharedCandidateChainResult,
    run_bankroll_coach_step,
    run_shared_candidate_chain,
)
from app.persistence.recommendations import create_recommendation_cycle, persist_agent_output, persist_candidate_agent_output
from app.persistence.user_profiles import read_user_profile


async def run_recommendation_cycle(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    correlation_id: str,
    prompt_version: str,
    agent_version: str,
    agents: list[ContextDataAgent],
    routing_rules: dict[str, dict],
    adapter_registry: AdapterRegistry,
    model_providers: dict[str, str] | None = None,
    retry_engine: RetryEngine | None = None,
) -> tuple[str, FanOutResult]:
    """Runs one full cycle for `game_id` and returns
    `(recommendation_id, fan_out_result)`. Every successful agent's
    output is persisted against `recommendation_id`; every failed agent
    is represented only in `fan_out_result.failures`, never as a
    persisted row."""
    context = await build_agent_context(client, headers, game_id=game_id, correlation_id=correlation_id)

    recommendation_id = await create_recommendation_cycle(
        client,
        headers,
        game_id=game_id,
        prompt_version=prompt_version,
        agent_version=agent_version,
        correlation_id=correlation_id,
    )

    fan_out_result = await run_fan_out(
        agents,
        context,
        client=client,
        headers=headers,
        routing_rules=routing_rules,
        model_providers=model_providers,
        adapter_registry=adapter_registry,
        retry_engine=retry_engine,
    )

    for result in fan_out_result.successes:
        await persist_agent_output(
            client,
            headers,
            recommendation_id=recommendation_id,
            agent_name=result.agent_name,
            output=result.output,
            prompt_name=result.prompt_name,
            prompt_version=result.prompt_version,
        )

    return recommendation_id, fan_out_result


def _shared_deterministic_payload_for(agent_name: str, chain_result: SharedCandidateChainResult) -> dict:
    """Maps a shared-chain agent's own deterministic companion data --
    computed by `app.orchestration.sequential.run_shared_candidate_chain`,
    never by the agent's own LLM call -- into the plain dict persisted
    alongside its `AgentOutput` (Milestone 4.6: "compose, don't extend
    the contract")."""
    if agent_name == "expected_value_agent":
        return dataclasses.asdict(chain_result.ev)
    if agent_name == "risk_manager_agent":
        return dataclasses.asdict(chain_result.risk)
    raise ValueError(f"no deterministic payload mapping for agent_name={agent_name!r}")


async def run_candidate_evaluation(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_id: str,
    game_id: str,
    correlation_id: str,
    candidate: MarketCandidate,
    upstream_outputs: tuple,
    participation: ParticipationMetadata,
    routing_rules: dict[str, dict],
    adapter_registry: AdapterRegistry,
    model_providers: dict[str, str] | None = None,
    retry_engine: RetryEngine | None = None,
) -> SharedCandidateChainResult:
    """Runs the SHARED half of the Decision & Advisory chain (Probability
    Modeling -> EV -> Risk Manager, Milestone 4.9 Decision 2) for exactly
    one `MarketCandidate` against an ALREADY-EXISTING `recommendation_id`
    -- one recommendation cycle may have this called multiple times, once
    per candidate evaluated within it (Decision G). Never creates a
    second `recommendations` row. No user/bankroll concept at all -- see
    `run_bankroll_coach_evaluation` for the per-user step.

    Persists one `recommendation_agent_outputs` row per successful
    chain step, each tagged with this candidate's `candidate_key`. A
    failed step (including Probability Modeling itself, which blocks the
    rest of the chain per `run_shared_candidate_chain`) is never
    persisted. Returns the full `SharedCandidateChainResult` -- including
    its `context` -- so callers can pass it straight into
    `run_bankroll_coach_evaluation` without re-fetching or re-running
    anything."""
    context = SequentialDecisionContext(
        game_id=game_id,
        correlation_id=correlation_id,
        candidate=candidate,
        upstream_outputs=tuple(upstream_outputs),
        participation=participation,
    )

    chain_result = await run_shared_candidate_chain(
        context,
        client=client,
        headers=headers,
        routing_rules=routing_rules,
        model_providers=model_providers,
        adapter_registry=adapter_registry,
        retry_engine=retry_engine,
    )

    key = _candidate_key(candidate)
    for result in chain_result.successes:
        if isinstance(result.output, ProbabilityModelOutput):
            raw_output = {"probability_output": result.output.model_dump(mode="json")}
            agent_confidence = result.output.confidence_in_probability
        else:
            raw_output = {
                "agent_output": result.output.model_dump(mode="json"),
                "deterministic": _shared_deterministic_payload_for(result.agent_name, chain_result),
            }
            agent_confidence = result.output.confidence
        await persist_candidate_agent_output(
            client,
            headers,
            recommendation_id=recommendation_id,
            agent_name=result.agent_name,
            candidate_key=key,
            raw_output=raw_output,
            agent_confidence=agent_confidence,
            prompt_name=result.prompt_name,
            prompt_version=result.prompt_version,
        )

    return chain_result


async def run_bankroll_coach_evaluation(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_id: str,
    candidate: MarketCandidate,
    shared_chain_context: SequentialDecisionContext,
    routing_rule: dict,
    adapter_registry: AdapterRegistry,
    user_id: str | None = None,
    model_providers: dict[str, str] | None = None,
    retry_engine: RetryEngine | None = None,
) -> BankrollCoachResult:
    """Runs Bankroll Coach for exactly one user against an already-
    evaluated candidate (Milestone 4.9, Decision 2) -- `shared_chain_context`
    must be `run_candidate_evaluation`'s own returned
    `SharedCandidateChainResult.context` (carrying `probability`/`ev`
    forward, so this step never re-runs those model calls). Callable zero
    or more times per candidate, once per user who actually needs a
    stake number -- calling it for a second user does not touch
    Probability/EV/Risk again.

    `user_id`, when given, reads that user's real `user_profiles` row
    (Decision F) -- `None` (no row, or every real row's `optional_bankroll`
    being `NULL`, as confirmed live in dev) flows straight through to
    `context.bankroll_profile`, never fabricated. Omitting `user_id`
    entirely (the default) also yields `bankroll_profile=None`, exactly
    the same degraded path a real incomplete profile produces -- bankroll
    stays optional/user-reported/non-authoritative: candidate analysis
    already happened regardless, only the dollar stake goes `None`.

    Persists one `recommendation_agent_outputs` row for Bankroll Coach on
    success, tagged with the same `candidate_key` the shared chain's rows
    used."""
    bankroll_profile = await read_user_profile(client, headers, user_id=user_id) if user_id is not None else None
    context = dataclasses.replace(shared_chain_context, bankroll_profile=bankroll_profile)

    result = await run_bankroll_coach_step(
        context,
        client=client,
        headers=headers,
        routing_rule=routing_rule,
        model_providers=model_providers,
        adapter_registry=adapter_registry,
        retry_engine=retry_engine,
    )

    if result.status == "success":
        await persist_candidate_agent_output(
            client,
            headers,
            recommendation_id=recommendation_id,
            agent_name=result.result.agent_name,
            candidate_key=_candidate_key(candidate),
            raw_output={
                "agent_output": result.result.output.model_dump(mode="json"),
                "deterministic": dataclasses.asdict(result.kelly),
            },
            agent_confidence=result.result.output.confidence,
            prompt_name=result.result.prompt_name,
            prompt_version=result.result.prompt_version,
        )

    return result
