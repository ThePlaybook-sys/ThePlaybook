"""The async fan-out executor (Milestone 4.4, Decision 8). Runs every
configured `ContextDataAgent` concurrently against one shared
`AgentContext`, via `asyncio.gather` -- `run_agent` never raises (it
catches every `ModelError` internally), so one agent's failure can never
cancel or block the others' concurrent execution.

**FULL/PARTIAL/FAILED, exactly as approved (Decision 8):**
- FULL: every configured agent produced a valid `AgentOutput`.
- PARTIAL: at least one succeeded, at least one failed.
- FAILED: zero succeeded.

**Failed agents are never fabricated as zero-confidence participants.**
A failed agent's `AgentRunResult.output` stays `None`; its absence is the
record of non-participation (Volume 4 Section 4.1's own consensus
formula already sums only over agents that actually contributed a term --
see `PROGRESS.md`'s Milestone 4.4 entry for the full reasoning this
mirrors at the orchestration layer).

**No minimum-participation quorum is invented here** -- FULL/PARTIAL/
FAILED are structural conditions (all/some/none succeeded), not a chosen
threshold. Per Mac's explicit instruction, an actual minimum-viable-
participation number (e.g. "at least N of 17") is carried forward to
Milestone 4.7 (Consensus Engine), not decided in this fan-out layer.

**Milestone 4.8:** `run_agent` resolves each agent's canonical system
prompt via `app.persistence.model_config.resolve_active_prompt` at this
orchestration boundary (Mac's approved Option C -- never inside the
agent class itself) before building the `ModelRequest`. A
`PromptConfigError` (no active prompt configured) is caught by the same
blanket `except Exception` this function already uses to isolate any
other per-agent failure -- one agent's missing prompt configuration fails
that agent clearly (`AgentRunResult.error` names exactly what's missing),
never the whole fan-out, and never silently substitutes hardcoded text.
`AgentRunResult.prompt_name`/`.prompt_version` carry the exact resolved
prompt identity forward so `app.orchestration.cycle` can persist it
per-output (`recommendation_agent_outputs.prompt_name`/`.prompt_version`).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from app.agents.base_agent import ContextDataAgent
from app.agents.context import AgentContext
from app.agents.contract import AgentOutput
from app.models.errors import ModelError
from app.models.retry_policy import RetryEngine
from app.models.router import AdapterRegistry, ModelRouter
from app.models.types import ModelRequest
from app.persistence.model_config import resolve_active_prompt


@dataclass
class AgentRunResult:
    agent_name: str
    status: str  # "success" | "failed"
    output: AgentOutput | None = None
    error: str | None = None
    prompt_name: str | None = None
    prompt_version: int | None = None
    # Milestone 5.3 (Decision AV) -- the ACTUAL model/provider that
    # produced this output, from `ModelResponse.usage`, never the
    # requested routing rule's `primary_model`. `None` only for a failed
    # run (no response was ever produced).
    model_name: str | None = None
    provider: str | None = None
    used_fallback: bool | None = None


@dataclass
class FanOutResult:
    status: str  # "full" | "partial" | "failed"
    results: list[AgentRunResult]

    @property
    def successes(self) -> list[AgentRunResult]:
        return [r for r in self.results if r.status == "success"]

    @property
    def failures(self) -> list[AgentRunResult]:
        return [r for r in self.results if r.status == "failed"]


async def run_agent(
    agent: ContextDataAgent,
    context: AgentContext,
    *,
    client: httpx.AsyncClient,
    headers: dict,
    routing_rule: dict,
    model_providers: dict[str, str] | None,
    adapter_registry: AdapterRegistry,
    retry_engine: RetryEngine,
) -> AgentRunResult:
    """Runs exactly one agent to completion or failure. Never raises --
    every `ModelError` (including routing/adapter-lookup errors, and
    Milestone 4.8's `PromptConfigError` for missing prompt configuration,
    all wrapped consistently with the rest of this package's exception
    discipline) is caught and reported as a failed `AgentRunResult`, so
    `asyncio.gather` in `run_fan_out` never has one agent's failure
    cancel the others."""
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
            response_model=AgentOutput,
        )
        response = await retry_engine.execute(
            primary=primary,
            primary_provider=decision.primary_provider,
            request=request,
            fallback=fallback,
            fallback_provider=decision.fallback_provider,
        )
    except Exception as exc:  # noqa: BLE001 -- deliberate: isolate this one agent, never cancel the others
        return AgentRunResult(agent_name=agent.agent_name, status="failed", error=str(exc))
    return AgentRunResult(
        agent_name=agent.agent_name,
        status="success",
        output=response.parsed,
        prompt_name=resolved_prompt.prompt_name,
        prompt_version=resolved_prompt.version,
        model_name=response.usage.model,
        provider=response.usage.provider,
        used_fallback=response.usage.used_fallback,
    )


async def run_fan_out(
    agents: list[ContextDataAgent],
    context: AgentContext,
    *,
    client: httpx.AsyncClient,
    headers: dict,
    routing_rules: dict[str, dict],
    model_providers: dict[str, str] | None = None,
    adapter_registry: AdapterRegistry,
    retry_engine: RetryEngine | None = None,
) -> FanOutResult:
    """Runs all `agents` concurrently. `routing_rules` is keyed by
    `agent.task_type`. `retry_engine` defaults to a fresh `RetryEngine()`
    (default policy) if not supplied. `client`/`headers` are used only
    for `resolve_active_prompt` (Milestone 4.8) -- routing/model config
    is still supplied pre-fetched via `routing_rules`/`model_providers`,
    unchanged."""
    retry_engine = retry_engine or RetryEngine()
    results = await asyncio.gather(
        *(
            run_agent(
                agent,
                context,
                client=client,
                headers=headers,
                routing_rule=routing_rules[agent.task_type],
                model_providers=model_providers,
                adapter_registry=adapter_registry,
                retry_engine=retry_engine,
            )
            for agent in agents
        )
    )
    successes = [r for r in results if r.status == "success"]
    if not successes:
        status = "failed"
    elif len(successes) == len(results):
        status = "full"
    else:
        status = "partial"
    return FanOutResult(status=status, results=list(results))
