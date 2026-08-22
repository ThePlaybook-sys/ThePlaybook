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
the not-yet-built Consensus Engine milestone."""
from __future__ import annotations

import httpx

from app.agents.base_agent import ContextDataAgent
from app.agents.context import build_agent_context
from app.models.retry_policy import RetryEngine
from app.models.router import AdapterRegistry
from app.orchestration.fanout import FanOutResult, run_fan_out
from app.persistence.recommendations import create_recommendation_cycle, persist_agent_output


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
        client, headers, game_id=game_id, prompt_version=prompt_version, agent_version=agent_version
    )

    fan_out_result = await run_fan_out(
        agents,
        context,
        routing_rules=routing_rules,
        model_providers=model_providers,
        adapter_registry=adapter_registry,
        retry_engine=retry_engine,
    )

    for result in fan_out_result.successes:
        await persist_agent_output(
            client, headers, recommendation_id=recommendation_id, agent_name=result.agent_name, output=result.output
        )

    return recommendation_id, fan_out_result
