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
that re-ran Probability/EV/Risk once per user for no reason.

**Live Context Package Orchestration (2026-09-15, HQ-authorized "MANSA --
PHASE 8 LIVE CONTEXT PACKAGE ORCHESTRATION").** `run_candidate_evaluation`
now builds one real `ContextPackage` per candidate via the existing,
unmodified Context Intelligence engine (`app.context_intelligence.engine.
build_contextual_intelligence` + `app.context_intelligence.context_
package.assemble_context_package`) and attaches it to `SequentialDecisionContext.
context_package` -- no Context Intelligence logic is reimplemented here,
only composed, exactly as `engine.py`'s own "download once" reads already
work. `build_evidence()` (Milestone 4.6, Context Integration pass,
2026-09-15) remains the sole admission gate -- `ADMITTED_CONTEXT_
DIMENSIONS` is neither read, duplicated, nor bypassed here; this module
attaches the FULL, unfiltered package (all ten dimensions, exactly as the
engine produces), and filtering to the four admitted, non-unavailable
ones happens only inside `build_evidence()`, unchanged.

**Live-only, by construction, not by convention.** `_attach_context_package`
always uses real wall-clock time (`datetime.now(timezone.utc)`) for the
package's `target_event_timestamp` -- there is no parameter anywhere in
this module's own public surface that lets a caller backdate it, which
would be the one thing that could turn the market/weather comparable-pool
evidence (undisclosed point-in-time filter, per the Admission Decision)
unsafe. This codebase has no historical/replay execution path today
(confirmed by direct search across `app/orchestration/`/`app/workers/`
this pass) -- `run_candidate_evaluation`/`_evaluate_one_candidate`
(`recommendation_worker.py`) are exclusively live-call sites.

**Additive and failure-isolated.** `_attach_context_package` never raises
-- any failure while building the real package (a Supabase read error, an
unexpected shape) is caught, logged via `_logger.warning`, and degrades
to `context_package=None`, which `build_evidence()` already treats
exactly like every pre-Context-Integration call (no `contextual_evidence`
key at all). The rest of the sequential chain, and every probability/EV/
risk computation downstream of it, is completely unaffected either way --
nothing about this step can change a probability or fail the
recommendation cycle.

**`player_id` has no real source in this codebase yet.** `MarketCandidate`
(`app.features.candidate`) carries no structured player identity -- a
`"prop"` candidate's player is only ever free text inside `selection`
(e.g. `"Jaxon Smith-Njigba Over 65.5"`). Matching that text against a
real player would be exactly the fuzzy-matching-as-identity-resolution
this whole Context Intelligence effort has deliberately avoided
elsewhere (opponent resolution, Engine Integration pass) -- so this pass
does not attempt it. `run_candidate_evaluation` accepts an optional
`player_id` parameter for a FUTURE caller that has one (e.g. once a real,
structured props pipeline exists); `recommendation_worker.py`'s own real
call site does not pass one today, so `player_performance` legitimately,
honestly resolves to `unavailable` (absent from `contextual_evidence`)
for every real live candidate right now -- not a bug, the correct
reflection of real capability."""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone

import httpx

from app.agents.base_agent import ContextDataAgent
from app.agents.committee_context import ParticipationMetadata, SequentialDecisionContext
from app.agents.context import build_agent_context
from app.agents.probability_output import ProbabilityModelOutput
from app.context_intelligence.context_package import ContextPackage, assemble_context_package
from app.context_intelligence.engine import build_contextual_intelligence
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

_logger = logging.getLogger(__name__)


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
            model_name=result.model_name,
            provider=result.provider,
            used_fallback=result.used_fallback,
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


async def _attach_context_package(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, player_id: str | None
) -> ContextPackage | None:
    """Builds one real `ContextPackage` for `game_id` (and `player_id`,
    when known) via the existing, unmodified Context Intelligence engine
    -- see module docstring for why this is always live (real wall-clock
    `now`, no override parameter) and always additive (never raises).
    Returns `None`, never an exception, on any failure -- the caller
    treats that identically to "no Context Intelligence attempted,"
    exactly `build_evidence()`'s own pre-existing degraded path."""
    try:
        now = datetime.now(timezone.utc)
        intelligence = await build_contextual_intelligence(client, headers, game_id=game_id, player_id=player_id, now=now)
        return assemble_context_package(intelligence, player_id=player_id, target_event_timestamp=now.isoformat())
    except Exception:
        _logger.warning(
            "Context Intelligence package construction failed for game_id=%r player_id=%r -- "
            "continuing the recommendation cycle without contextual evidence (additive-only, "
            "never fails the cycle, never changes any probability).",
            game_id, player_id, exc_info=True,
        )
        return None


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
    player_id: str | None = None,
) -> SharedCandidateChainResult:
    """Runs the SHARED half of the Decision & Advisory chain (Probability
    Modeling -> EV -> Risk Manager, Milestone 4.9 Decision 2) for exactly
    one `MarketCandidate` against an ALREADY-EXISTING `recommendation_id`
    -- one recommendation cycle may have this called multiple times, once
    per candidate evaluated within it (Decision G). Never creates a
    second `recommendations` row. No user/bankroll concept at all -- see
    `run_bankroll_coach_evaluation` for the per-user step.

    `player_id` (2026-09-15, Live Context Package Orchestration pass) is
    optional and has no real source in this codebase yet -- see module
    docstring. When given, the attached `ContextPackage` includes real
    `player_performance` evidence when available; when omitted (every
    real call today), `player_performance` legitimately resolves to
    `unavailable`.

    Persists one `recommendation_agent_outputs` row per successful
    chain step, each tagged with this candidate's `candidate_key`. A
    failed step (including Probability Modeling itself, which blocks the
    rest of the chain per `run_shared_candidate_chain`) is never
    persisted. Returns the full `SharedCandidateChainResult` -- including
    its `context` -- so callers can pass it straight into
    `run_bankroll_coach_evaluation` without re-fetching or re-running
    anything."""
    context_package = await _attach_context_package(client, headers, game_id=game_id, player_id=player_id)

    context = SequentialDecisionContext(
        game_id=game_id,
        correlation_id=correlation_id,
        candidate=candidate,
        upstream_outputs=tuple(upstream_outputs),
        participation=participation,
        context_package=context_package,
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
            model_name=result.model_name,
            provider=result.provider,
            used_fallback=result.used_fallback,
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
            model_name=result.result.model_name,
            provider=result.result.provider,
            used_fallback=result.result.used_fallback,
        )

    return result
