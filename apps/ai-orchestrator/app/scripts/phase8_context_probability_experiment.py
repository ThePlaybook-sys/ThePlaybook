"""Phase 8, MANSA directive "PHASE 8 TEMPORARY DIAGNOSTIC SERVICE EXPERIMENT"
(2026-09-15). One-shot diagnostic entry point -- NOT imported by the FastAPI
app, NOT a production code path. Runs to completion once, prints a single
JSON report to stdout, and exits.

**Why it lives under `app/scripts/` rather than the repo-level `scripts/`
directory** (2026-09-15 path fix, after a real 0-call failure): this
service's Dockerfile copies ONLY `COPY app ./app` into the built image, so
anything under the sibling `scripts/` directory is absent at runtime -- the
first deployment crashed with `python: can't open file
'/app/scripts/phase8_context_probability_experiment.py'` before executing a
single line. Placing it inside `app/` makes it image-visible with no change
to the shared Dockerfile (which `ai-orchestrator` itself also builds from).

Intended to run only as the `startCommand`
of a temporary, isolated Railway service (`phase8-context-experiment`) whose
variables are set as Railway REFERENCES to the real `ai-orchestrator` (dev)
service's own variables -- this script reads `ANTHROPIC_API_KEY`/
`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` from its own process environment
exactly like `app.main._build_real_adapter_registry` already does elsewhere;
none of the three ever leaves this process, is printed, or is logged --
`_redact` scrubs the final report of their exact values as a last-resort
safety net before anything is written to stdout.

**Exercises the REAL MANSA probability path, not a reimplementation:**
`app.persistence.model_config.list_active_model_routing_rules`/
`list_active_models` (real active-routing-rule + real active-model-registry
reads), `app.orchestration.sequential.run_sequential_agent` (real
`resolve_active_prompt` call -> real active `prompt_registry` row ->
`app.agents.probability_modeling.ProbabilityModelingAgent.build_evidence`/
`build_messages` -> the real `app.models.retry_policy.RetryEngine` ->
`app.models.anthropic_adapter.AnthropicModelAdapter` making a real HTTPS
call to `https://api.anthropic.com`). Nothing here is a parallel/duplicate
implementation of that path.

**Hard 6-call budget**: `_BudgetGuardedAdapter` wraps the ONE real
`AnthropicModelAdapter` instance at the lowest practical boundary --
`primary_provider`/`fallback_provider` both resolve to `"anthropic"` for
`probability_modeling_analysis` (claude-opus-5 primary, claude-sonnet-5
fallback, per `model_registry.provider`), so both `RetryEngine` candidates
share this one wrapped instance; every attempt (primary, retry, or
fallback) increments one shared counter, and a call that would exceed 6 is
structurally refused -- the real HTTP request is never made.

**Stop-on-first-failure, applied to every call, not just the first**:
each of the 6 logical evaluations (3 pairs x CONTROL/CONTEXT) is run one at
a time, in order; the script aborts and reports immediately the moment any
one does not succeed -- never attempting a later evaluation once an earlier
one has failed.

**Never persists anything**: calls `run_sequential_agent` directly (the
same function `run_shared_candidate_chain`/`run_context_probability_
comparison` call internally), never `app.orchestration.cycle.
run_candidate_evaluation` (the persistence-writing path) or
`app.orchestration.recommendation_worker`. No sports-data provider call is
made anywhere in this script -- `upstream_outputs=()` for every context,
disclosed explicitly in the report rather than fabricated.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import sys
from datetime import datetime, timezone

import httpx

#: Three levels up from `app/scripts/this_file.py` is the package root that
#: holds `app/` itself -- `/app` inside the built image (Dockerfile:
#: `WORKDIR /app` + `COPY app ./app`), `apps/ai-orchestrator` in a checkout.
#: Required because Python puts the SCRIPT's own directory on `sys.path`,
#: not the working directory, when invoked as `python app/scripts/<file>.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agents.committee_context import ParticipationMetadata, SequentialDecisionContext  # noqa: E402
from app.agents.probability_modeling import ADMITTED_CONTEXT_DIMENSIONS, ProbabilityModelingAgent  # noqa: E402
from app.context_intelligence.context_package import ContextPackage, DimensionCompleteness  # noqa: E402
from app.context_intelligence.models import ContextualDimensionResult, ContextualIntelligenceResult  # noqa: E402
from app.features.candidate import MarketCandidate  # noqa: E402
from app.features.probability import InvalidOddsError, implied_probability  # noqa: E402
from app.models.anthropic_adapter import AnthropicModelAdapter  # noqa: E402
from app.models.retry_policy import RetryEngine  # noqa: E402
from app.models.router import AdapterRegistry  # noqa: E402
from app.orchestration.context_probability_comparison import DIMENSION_OVERLAPPING_AGENTS  # noqa: E402
from app.orchestration.sequential import run_sequential_agent  # noqa: E402
from app.persistence.model_config import list_active_model_routing_rules, list_active_models  # noqa: E402

MAX_CALLS = 6
TREND_KEYWORDS = ("trend", "trending", "tendency", "pattern", "consistently", "typically", "usually", "historically")
SPORTSBOOK_COPY_EPSILON = 0.005


class _BudgetExceeded(Exception):
    pass


class _BudgetGuardedAdapter:
    """Wraps the ONE real AnthropicModelAdapter instance. Refuses (raises,
    without making the HTTP request) the moment a 7th real Anthropic
    request would be attempted -- primary attempts, in-model retries, and
    fallback attempts all increment the same shared counter."""

    def __init__(self, real_adapter: AnthropicModelAdapter, counter: list[int]):
        self._real = real_adapter
        self._counter = counter

    async def complete(self, request):
        if self._counter[0] >= MAX_CALLS:
            raise _BudgetExceeded(f"refused: {self._counter[0]} real Anthropic request(s) already made; {MAX_CALLS}-call budget exhausted")
        self._counter[0] += 1
        return await self._real.complete(request)


def _redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _participation() -> ParticipationMetadata:
    return ParticipationMetadata(
        configured_agents=frozenset({"injury_intelligence_agent"}),
        built_agents=frozenset({"injury_intelligence_agent"}),
        deferred_agents=frozenset(),
        attempted_agents=frozenset(),
        successful_agents=frozenset(),
        failed_agents=frozenset(),
        fan_out_status="full",
        committee_completeness=1.0,
    )


def _dim_result(dimension: str, *, completeness: str, sample_size: int, facts: dict) -> ContextualDimensionResult:
    return ContextualDimensionResult(
        dimension=dimension, context_dimensions_used=(), sample_size=sample_size,
        similarity_score=None, recency_weighting=None, confidence=None,
        confounders=(), insufficient_evidence=(completeness != "joined" or sample_size <= 1),
        insufficient_evidence_reason=None, provenance=(), facts=facts, data_completeness=completeness,
    )


def _package(game_id: str, dim_results: dict[str, ContextualDimensionResult], target_ts: str) -> ContextPackage:
    intelligence = ContextualIntelligenceResult(game_id=game_id, generated_at=target_ts, dimensions=dim_results)
    joined = tuple(sorted(n for n, r in dim_results.items() if r.data_completeness == "joined"))
    partial = tuple(sorted(n for n, r in dim_results.items() if r.data_completeness == "partial"))
    unavailable = tuple(sorted(n for n, r in dim_results.items() if r.data_completeness == "unavailable"))
    dimension_completeness = {
        n: DimensionCompleteness(dimension=n, completeness=r.data_completeness, reason=None, sample_size=r.sample_size, provenance=r.provenance)
        for n, r in dim_results.items()
    }
    return ContextPackage(
        game_id=game_id, player_id=None, generated_at=target_ts, target_event_timestamp=target_ts,
        joined_dimensions=joined, partial_dimensions=partial, unavailable_dimensions=unavailable,
        dimension_completeness=dimension_completeness, known_limitations=(), intelligence=intelligence,
    )


def _build_pairs() -> list[tuple[str, SequentialDecisionContext, SequentialDecisionContext]]:
    now = datetime.now(timezone.utc)
    ts = now.isoformat()

    # --- Pair 1: MARKET context -- SYNTHETIC candidate/game, clearly labeled ---
    market_candidate = MarketCandidate(
        game_id="phase8-realexp-market-synthetic", sportsbook="DraftKings", market_type="moneyline",
        selection="Kansas City Chiefs", american_odds=-125, point=None, observed_at=now,
    )
    market_control = SequentialDecisionContext(
        game_id=market_candidate.game_id, correlation_id="phase8-realexp-market-control",
        candidate=market_candidate, upstream_outputs=(), participation=_participation(), context_package=None,
    )
    market_package = _package(
        market_candidate.game_id,
        {"market": _dim_result("market", completeness="joined", sample_size=6, facts={"movement_groups": {"toward_favorite": 4, "toward_underdog": 2}, "comparable_pool_size": 6})},
        ts,
    )
    market_context = dataclasses.replace(market_control, correlation_id="phase8-realexp-market-context", context_package=market_package)

    # --- Pair 2: WEATHER PARTIAL context -- SYNTHETIC candidate/game, clearly labeled ---
    weather_candidate = MarketCandidate(
        game_id="phase8-realexp-weather-synthetic", sportsbook="DraftKings", market_type="total",
        selection="Over", american_odds=-110, point=44.5, observed_at=now,
    )
    weather_control = SequentialDecisionContext(
        game_id=weather_candidate.game_id, correlation_id="phase8-realexp-weather-control",
        candidate=weather_candidate, upstream_outputs=(), participation=_participation(), context_package=None,
    )
    weather_package = _package(
        weather_candidate.game_id,
        {"weather": _dim_result("weather", completeness="partial", sample_size=1, facts={"conditions": "Overcast", "temperature_f": 63.1, "wind_mph": 0.9, "precipitation_pct": 15.0})},
        ts,
    )
    weather_context = dataclasses.replace(weather_control, correlation_id="phase8-realexp-weather-context", context_package=weather_package)

    # --- Pair 3: PLAYER PERFORMANCE -- REAL JSN/SEA@NE evaluation fixture ---
    # Real persisted values (this session's own repeatedly live-verified proof):
    # 11 targets, 8 receptions, 122 receiving yards, 1 TD, sample_size=1.
    # An evaluation fixture, not a production player-prop candidate --
    # player_receiving_yards is not a real V1 market type (candidate_generation.py).
    SEA_NE_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"
    player_candidate = MarketCandidate(
        game_id=SEA_NE_GAME_ID, sportsbook="DraftKings", market_type="player_receiving_yards",
        selection="Jaxon Smith-Njigba Over 65.5", american_odds=-115, point=65.5, observed_at=now,
    )
    player_control = SequentialDecisionContext(
        game_id=SEA_NE_GAME_ID, correlation_id="phase8-realexp-player-control",
        candidate=player_candidate, upstream_outputs=(), participation=_participation(), context_package=None,
    )
    player_package = _package(
        SEA_NE_GAME_ID,
        {
            "player_performance": _dim_result(
                "player_performance", completeness="joined", sample_size=1,
                facts={"observations": [{"role_usage_signals": {"receiving": {"targets": 11, "receptions": 8, "recYards": 122, "recTD": 1}}}]},
            )
        },
        ts,
    )
    player_context = dataclasses.replace(player_control, correlation_id="phase8-realexp-player-context", context_package=player_package)

    return [
        ("market", market_control, market_context),
        ("weather_partial", weather_control, weather_context),
        ("player_performance_jsn_sea_ne", player_control, player_context),
    ]


def _dimension_mentioned(dimension: str, text_blob: str) -> bool:
    return dimension in text_blob or dimension.replace("_", " ") in text_blob


def _sample_size(evidence: dict, dimension: str) -> int | None:
    entry = evidence.get("contextual_evidence", {}).get("dimensions", {}).get(dimension)
    return entry["sample_size"] if entry is not None else None


def _safety_flags(*, control_output, context_output, context_evidence, upstream_outputs) -> dict:
    admitted_present = tuple(sorted(context_evidence.get("contextual_evidence", {}).get("dimensions", {})))
    admitted_unavailable = tuple(sorted(set(ADMITTED_CONTEXT_DIMENSIONS) - set(admitted_present)))
    upstream_agent_names = {o.agent_name for o in upstream_outputs}
    duplicated = tuple(sorted(d for d in admitted_present if DIMENSION_OVERLAPPING_AGENTS.get(d, frozenset()) & upstream_agent_names))

    delta = context_output.modeled_probability - control_output.modeled_probability
    text_blob = " ".join([context_output.reasoning, *context_output.supporting_evidence]).lower()
    claimed = tuple(sorted(d for d in admitted_present if _dimension_mentioned(d, text_blob)))
    moved = abs(delta) > 1e-9

    sportsbook_copied = False
    american_odds = None  # filled by caller
    return {
        "admitted_dimensions_present": admitted_present,
        "admitted_dimensions_unavailable": admitted_unavailable,
        "duplicated_dimensions": duplicated,
        "claimed_dimensions": claimed,
        "probability_delta": delta,
        "flags": {
            "probability_moved_without_unique_contextual_reason": moved and not claimed,
            "duplicated_evidence_appears_additionally_influential": moved and any(d in claimed for d in duplicated),
            "unavailable_evidence_affects_probability": moved and any(_dimension_mentioned(d, text_blob) for d in admitted_unavailable),
            "venue_alone_causes_unsupported_movement": moved and admitted_present == ("venue",) and "venue" in claimed,
            "player_history_described_as_trend": (
                _sample_size(context_evidence, "player_performance") == 1
                and "player_performance" in claimed
                and any(kw in text_blob for kw in TREND_KEYWORDS)
            ),
        },
    }


def _result_summary(label: str, side: str, result) -> dict:
    summary = {
        "pair": label, "side": side, "status": result.status,
        "model": result.model_name, "provider": result.provider, "used_fallback": result.used_fallback,
        "prompt_name": result.prompt_name, "prompt_version": result.prompt_version,
    }
    if result.status == "success":
        out = result.output
        summary.update({
            "candidate_key": out.candidate_key, "selection": out.selection,
            "modeled_probability": out.modeled_probability, "confidence_in_probability": out.confidence_in_probability,
            "reasoning": out.reasoning, "supporting_evidence": list(out.supporting_evidence),
        })
    else:
        summary["error"] = result.error
    return summary


async def main() -> None:
    anthropic_key = os.environ["ANTHROPIC_API_KEY"]
    supabase_url = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    secrets = [anthropic_key, service_role_key]
    headers = {"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"}

    counter = [0]
    real_anthropic = AnthropicModelAdapter(client=httpx.AsyncClient(base_url="https://api.anthropic.com"), api_key=anthropic_key)
    guarded = _BudgetGuardedAdapter(real_anthropic, counter)
    adapter_registry = AdapterRegistry(adapters={"anthropic": guarded})
    agent = ProbabilityModelingAgent()

    report: dict = {"max_calls": MAX_CALLS, "calls": [], "pairs": [], "stopped_reason": None}

    async with httpx.AsyncClient(base_url=supabase_url) as client:
        try:
            routing_rule_rows = await list_active_model_routing_rules(client, headers)
            routing_rules = {row["task_type"]: row for row in routing_rule_rows}
            model_rows = await list_active_models(client, headers)
            model_providers = {row["model_name"]: row["provider"] for row in model_rows}
            routing_rule = routing_rules["probability_modeling_analysis"]
        except Exception as exc:  # noqa: BLE001 -- config-read failure before any Anthropic call; report and stop
            report["stopped_reason"] = f"failed to read real routing config before any Anthropic call: {exc}"
            print(_redact(json.dumps(report, default=str), secrets))
            return

        report["routing_rule"] = {"task_type": routing_rule["task_type"], "primary_model": routing_rule["primary_model"], "fallback_model": routing_rule.get("fallback_model")}

        for label, control_ctx, context_ctx in _build_pairs():
            control_result = await run_sequential_agent(
                agent, control_ctx, client=client, headers=headers, routing_rule=routing_rule,
                model_providers=model_providers, adapter_registry=adapter_registry, retry_engine=RetryEngine(),
            )
            report["calls"].append(_result_summary(label, "CONTROL", control_result))
            if control_result.status != "success":
                report["stopped_reason"] = f"{label} CONTROL failed after {counter[0]} real Anthropic request(s): {control_result.error}"
                break

            context_result = await run_sequential_agent(
                agent, context_ctx, client=client, headers=headers, routing_rule=routing_rule,
                model_providers=model_providers, adapter_registry=adapter_registry, retry_engine=RetryEngine(),
            )
            report["calls"].append(_result_summary(label, "CONTEXT", context_result))
            if context_result.status != "success":
                report["stopped_reason"] = f"{label} CONTEXT failed after {counter[0]} real Anthropic request(s): {context_result.error}"
                break

            context_evidence = agent.build_evidence(context_ctx)
            analysis = _safety_flags(
                control_output=control_result.output, context_output=context_result.output,
                context_evidence=context_evidence, upstream_outputs=context_ctx.upstream_outputs,
            )
            try:
                book_implied = implied_probability(context_ctx.candidate.american_odds) if context_ctx.candidate.american_odds else None
            except InvalidOddsError:
                book_implied = None
            analysis["flags"]["sportsbook_probability_appears_copied"] = (
                book_implied is not None and abs(context_result.output.modeled_probability - book_implied) < SPORTSBOOK_COPY_EPSILON
            )
            analysis["pair"] = label
            report["pairs"].append(analysis)

    report["actual_anthropic_request_count"] = counter[0]
    report["upstream_outputs_used"] = "none -- no sports-data provider or committee-agent calls made this run (out of scope); duplicated_dimensions can only reflect the candidate's own always-present priced line, not a real upstream agent finding"
    print(_redact(json.dumps(report, default=str, indent=2), secrets))


if __name__ == "__main__":
    asyncio.run(main())
