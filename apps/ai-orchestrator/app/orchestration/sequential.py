"""The sequential Decision & Advisory chain executor (Milestone 4.6):
Probability Modeling -> Expected Value -> Risk Manager -> Bankroll Coach,
run one after another (Volume 4 Section 3.1: "steps 4-6 are necessarily
sequential"), distinct from `app.orchestration.fanout`'s concurrent
model. Deterministic math (EV/Kelly/variance) is computed here, in
application code, between agent calls -- never inside an agent's own
`build_evidence` -- exactly mirroring how `app.agents.context.
build_agent_context` computes `TravelFeatures` before any fan-out agent
runs.

**Decision 8 (Milestone 4.4), carried forward:** if Probability Modeling
itself fails, the whole chain is FAILED -- nothing downstream can produce
a meaningful number without a modeled probability to build on. EV/Risk/
Bankroll Coach failing individually does NOT block each other or stop
deterministic computation for the remaining steps -- their own
LLM-narration failure is isolated exactly like `run_agent` isolates a
fan-out agent's failure, since the deterministic numbers themselves don't
depend on any LLM call succeeding.

**Milestone 4.8:** `run_sequential_agent` resolves each agent's canonical
system prompt via `resolve_active_prompt` at this orchestration boundary,
exactly mirroring `app.orchestration.fanout.run_agent` -- see that
module's docstring for the full rationale (Option C, fail-loud isolation,
never a hardcoded fallback).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import httpx

from app.agents.bankroll_coach import BankrollCoachAgent
from app.agents.committee_context import SequentialDecisionContext
from app.agents.expected_value_agent import ExpectedValueAgent
from app.agents.probability_modeling import ProbabilityModelingAgent
from app.agents.risk_manager import RiskManagerAgent
from app.agents.sequential_base import SequentialDecisionAgent
from app.features.expected_value import EVResult, compute_ev
from app.features.kelly import KellyResult, compute_stake
from app.features.risk import RiskAssessment, build_risk_assessment
from app.models.retry_policy import RetryEngine
from app.models.router import AdapterRegistry, ModelRouter
from app.models.types import ModelRequest
from app.persistence.model_config import resolve_active_prompt


@dataclass
class SequentialAgentRunResult:
    agent_name: str
    status: str  # "success" | "failed"
    output: object | None = None  # AgentOutput or ProbabilityModelOutput
    error: str | None = None
    prompt_name: str | None = None
    prompt_version: int | None = None


@dataclass
class SequentialChainResult:
    status: str  # "full" | "partial" | "failed"
    results: list[SequentialAgentRunResult]
    probability: object | None  # ProbabilityModelOutput | None
    ev: EVResult | None
    risk: RiskAssessment | None
    kelly: KellyResult | None

    @property
    def successes(self) -> list[SequentialAgentRunResult]:
        return [r for r in self.results if r.status == "success"]

    @property
    def failures(self) -> list[SequentialAgentRunResult]:
        return [r for r in self.results if r.status == "failed"]


async def run_sequential_agent(
    agent: SequentialDecisionAgent,
    context: SequentialDecisionContext,
    *,
    client: httpx.AsyncClient,
    headers: dict,
    routing_rule: dict,
    model_providers: dict[str, str] | None,
    adapter_registry: AdapterRegistry,
    retry_engine: RetryEngine,
) -> SequentialAgentRunResult:
    """Runs exactly one sequential-chain agent to completion or failure.
    Never raises -- mirrors `app.orchestration.fanout.run_agent`'s
    isolation guarantee exactly, generalized to whichever `response_model`
    the agent declares (`AgentOutput` for three of the four,
    `ProbabilityModelOutput` for Probability Modeling)."""
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
            primary=primary,
            primary_provider=decision.primary_provider,
            request=request,
            fallback=fallback,
            fallback_provider=decision.fallback_provider,
        )
    except Exception as exc:  # noqa: BLE001 -- deliberate: isolate this one agent, never abort the chain
        return SequentialAgentRunResult(agent_name=agent.agent_name, status="failed", error=str(exc))
    return SequentialAgentRunResult(
        agent_name=agent.agent_name,
        status="success",
        output=response.parsed,
        prompt_name=resolved_prompt.prompt_name,
        prompt_version=resolved_prompt.version,
    )


async def run_sequential_chain(
    context: SequentialDecisionContext,
    *,
    client: httpx.AsyncClient,
    headers: dict,
    routing_rules: dict[str, dict],
    model_providers: dict[str, str] | None = None,
    adapter_registry: AdapterRegistry,
    retry_engine: RetryEngine | None = None,
) -> SequentialChainResult:
    """Runs the full 4-step chain against one already-built
    `SequentialDecisionContext` (one game, one `MarketCandidate`,
    upstream fan-out outputs + participation metadata already attached).
    `routing_rules` is keyed by each agent's `task_type`. `client`/
    `headers` are used only for `resolve_active_prompt` (Milestone 4.8)."""
    retry_engine = retry_engine or RetryEngine()
    results: list[SequentialAgentRunResult] = []

    probability_agent = ProbabilityModelingAgent()
    probability_result = await run_sequential_agent(
        probability_agent,
        context,
        client=client,
        headers=headers,
        routing_rule=routing_rules[probability_agent.task_type],
        model_providers=model_providers,
        adapter_registry=adapter_registry,
        retry_engine=retry_engine,
    )
    results.append(probability_result)
    if probability_result.status != "success":
        return SequentialChainResult(status="failed", results=results, probability=None, ev=None, risk=None, kelly=None)

    probability = probability_result.output
    context = dataclasses.replace(context, probability=probability)

    ev = compute_ev(probability.modeled_probability, context.candidate.american_odds)
    context = dataclasses.replace(context, ev=ev)
    ev_agent = ExpectedValueAgent()
    results.append(
        await run_sequential_agent(
            ev_agent,
            context,
            client=client,
            headers=headers,
            routing_rule=routing_rules[ev_agent.task_type],
            model_providers=model_providers,
            adapter_registry=adapter_registry,
            retry_engine=retry_engine,
        )
    )

    risk = build_risk_assessment(probability.modeled_probability)
    context = dataclasses.replace(context, risk=risk)
    risk_agent = RiskManagerAgent()
    results.append(
        await run_sequential_agent(
            risk_agent,
            context,
            client=client,
            headers=headers,
            routing_rule=routing_rules[risk_agent.task_type],
            model_providers=model_providers,
            adapter_registry=adapter_registry,
            retry_engine=retry_engine,
        )
    )

    bankroll_profile = context.bankroll_profile or {}
    kelly = compute_stake(
        probability.modeled_probability,
        ev.decimal_odds,
        bankroll=bankroll_profile.get("optional_bankroll"),
        risk_tolerance=bankroll_profile.get("risk_tolerance"),
    )
    context = dataclasses.replace(context, kelly=kelly)
    bankroll_agent = BankrollCoachAgent()
    results.append(
        await run_sequential_agent(
            bankroll_agent,
            context,
            client=client,
            headers=headers,
            routing_rule=routing_rules[bankroll_agent.task_type],
            model_providers=model_providers,
            adapter_registry=adapter_registry,
            retry_engine=retry_engine,
        )
    )

    successes = [r for r in results if r.status == "success"]
    if not successes:
        status = "failed"
    elif len(successes) == len(results):
        status = "full"
    else:
        status = "partial"

    return SequentialChainResult(status=status, results=results, probability=probability, ev=ev, risk=risk, kelly=kelly)
