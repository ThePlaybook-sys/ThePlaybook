import dataclasses
import os
from datetime import datetime, timedelta, timezone

import httpx
import sentry_sdk
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app import supabase_client
from app.features.candidate import candidate_key
from app.internal_auth import require_internal_token
from app.models.anthropic_adapter import AnthropicModelAdapter
from app.models.openai_adapter import OpenAIModelAdapter
from app.models.router import AdapterRegistry
from app.features.strategy import EvaluatedCandidate, GameCandidates
from app.features.adaptive_weighting import ADAPTIVE_WEIGHT_MIN_WINDOW_DAYS, EvaluationWindowTooShortError
from app.features.grading import GRADING_VERSION
from app.orchestration.adaptive_weighting import evaluate_committee
from app.orchestration.postgame_grading import grade_game, grade_pending_bankroll_preservation_products
from app.orchestration.postgame_review_narrative import generate_and_persist_postgame_review
from app.orchestration.recommendation_worker import RecommendationWorkerError, run_game_recommendation
from app.orchestration.strategy_finalize import finalize_slate_strategy
from app.persistence.model_config import list_active_model_routing_rules, list_active_models

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    # No privacy policy live yet (Volume 1 §10) to disclose PII collection —
    # revisit once one is in place.
    send_default_pii=False,
    # Without this, the SDK defaults every event to "production" regardless
    # of which Railway environment it actually came from.
    environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev"),
)

app = FastAPI(title="The Playbook — AI Orchestrator")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-orchestrator"}


@app.get("/v1/internal/ping", dependencies=[Depends(require_internal_token)])
def internal_ping() -> dict:
    return {"status": "ok", "service": "ai-orchestrator", "scope": "internal"}


class RunGameRecommendationRequest(BaseModel):
    """Milestone 4.9 -- the Recommendation Worker's (`apps/workers`) own
    request shape. `correlation_id` must already be the stable
    `(master_refresh_run_id, game_id)`-derived value the Worker computed
    -- this endpoint trusts it, never derives its own."""

    game_id: str
    correlation_id: str
    prompt_version: str
    agent_version: str


class StrategyInputItem(BaseModel):
    """Milestone 5.1 -- the frozen candidate fields `apps/workers` relays,
    unmodified, into `/v1/internal/recommendation-worker/finalize-strategy`
    once every game in a slate has been dispatched. `apps/workers` never
    inspects or recomputes any of these fields -- see that endpoint's own
    docstring for why this relay-not-recompute shape is required."""

    game_id: str
    recommendation_id: str
    consensus_snapshot_id: str
    candidate_key: str
    market_type: str
    selection: str
    sportsbook: str
    american_odds: int
    point: float | None
    decimal_odds: float
    ev_per_dollar: float
    final_aggregate_confidence: float


class CandidateRunResponseItem(BaseModel):
    candidate_key: str
    status: str
    shared_chain_status: str | None
    consensus_status: str | None
    second_pass_triggered: bool
    bankroll_coach_user_count: int
    error: str | None
    strategy_input: StrategyInputItem | None = None


class RunGameRecommendationResponse(BaseModel):
    recommendation_id: str
    fan_out_status: str
    sportsbook_used: str | None
    game_skipped_reason: str | None
    candidates: list[CandidateRunResponseItem]


def _build_real_adapter_registry() -> AdapterRegistry:
    """Constructed lazily, per-request -- never at import time (mirrors
    `app.supabase_client`'s own lazy-env-var-read convention) -- so this
    service can start, and every non-live-call code path can run,
    without `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` ever being set. A
    provider whose key isn't configured is simply absent from the
    registry -- `ModelRouter.route`/`AdapterRegistry.get` already fail
    loud (`UnknownProviderError`) for a missing provider, per-agent
    isolated by `run_agent`/`run_sequential_agent`/`_run_review_agent`,
    rather than this function inventing a fallback adapter."""
    adapters: dict[str, object] = {}
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        adapters["anthropic"] = AnthropicModelAdapter(
            client=httpx.AsyncClient(base_url="https://api.anthropic.com"), api_key=anthropic_key
        )
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        adapters["openai"] = OpenAIModelAdapter(
            client=httpx.AsyncClient(base_url="https://api.openai.com"), api_key=openai_key
        )
    return AdapterRegistry(adapters=adapters)


@app.post(
    "/v1/internal/recommendation-worker/run-game",
    dependencies=[Depends(require_internal_token)],
    response_model=RunGameRecommendationResponse,
)
async def internal_run_game_recommendation(payload: RunGameRecommendationRequest) -> RunGameRecommendationResponse:
    """Milestone 4.9's Recommendation Worker entry point -- reachable
    only via `INTERNAL_SERVICE_TOKEN`, called only by `apps/workers`
    (Milestone 4.9-7), never by `sports-intel-layer` directly (Mac's
    approved service-to-service boundary). See
    `app.orchestration.recommendation_worker`'s module docstring for the
    full pipeline this ties together."""
    headers = supabase_client.auth_headers()
    async with supabase_client.new_client(timeout=60.0) as client:
        routing_rule_rows = await list_active_model_routing_rules(client, headers)
        routing_rules = {row["task_type"]: row for row in routing_rule_rows}
        model_rows = await list_active_models(client, headers)
        model_providers = {row["model_name"]: row["provider"] for row in model_rows}

        try:
            result = await run_game_recommendation(
                client,
                headers,
                game_id=payload.game_id,
                correlation_id=payload.correlation_id,
                prompt_version=payload.prompt_version,
                agent_version=payload.agent_version,
                routing_rules=routing_rules,
                adapter_registry=_build_real_adapter_registry(),
                model_providers=model_providers,
            )
        except RecommendationWorkerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RunGameRecommendationResponse(
        recommendation_id=result.recommendation_id,
        fan_out_status=result.fan_out_status,
        sportsbook_used=result.sportsbook_used,
        game_skipped_reason=result.game_skipped_reason,
        candidates=[
            CandidateRunResponseItem(
                candidate_key=candidate_key(c.candidate),
                status=c.status,
                shared_chain_status=c.shared_chain_status,
                consensus_status=c.consensus_status,
                second_pass_triggered=c.second_pass_triggered,
                bankroll_coach_user_count=c.bankroll_coach_user_count,
                error=c.error,
                strategy_input=(StrategyInputItem(**dataclasses.asdict(c.strategy_input)) if c.strategy_input else None),
            )
            for c in result.candidates
        ],
    )


class FinalizeStrategyGameItem(BaseModel):
    """One game's worth of `run-game` output, as `apps/workers` collected
    it -- `candidates` is every candidate whose `strategy_input` came back
    non-null from that game's own `run-game` response, relayed unmodified.
    A game with zero qualifying/computable candidates still needs an
    entry with `candidates=[]` -- omitting it entirely (vs. sending it
    with an empty list) is reserved for a game that failed to dispatch at
    all (see module docstring)."""

    game_id: str
    recommendation_id: str
    candidates: list[StrategyInputItem]


class FinalizeStrategyRequest(BaseModel):
    master_refresh_run_id: str
    games: list[FinalizeStrategyGameItem]


class FinalizeStrategyResponse(BaseModel):
    outcome: str
    recommendation_product_ids: list[str]
    leg_count: int
    no_bet_game_count: int
    explanations_generated: int
    explanations_failed: int
    activation_snapshots_generated: int
    activation_snapshots_failed: int


@app.post(
    "/v1/internal/recommendation-worker/finalize-strategy",
    dependencies=[Depends(require_internal_token)],
    response_model=FinalizeStrategyResponse,
)
async def internal_finalize_strategy(payload: FinalizeStrategyRequest) -> FinalizeStrategyResponse:
    """Milestone 5.1's Strategy Engine finalization entry point --
    reachable only via `INTERNAL_SERVICE_TOKEN`, called by `apps/workers`
    exactly once per Recommendation Worker cycle, after every eligible
    game's `run-game` call has completed. See
    `app.orchestration.strategy_finalize`'s module docstring for the full
    slate-level rationale."""
    games = [
        GameCandidates(
            game_id=g.game_id,
            recommendation_id=g.recommendation_id,
            candidates=tuple(EvaluatedCandidate(**c.model_dump()) for c in g.candidates),
        )
        for g in payload.games
    ]
    headers = supabase_client.auth_headers()
    async with supabase_client.new_client(timeout=60.0) as client:
        decision, created_ids, explainability_result, time_machine_result = await finalize_slate_strategy(
            client, headers, master_refresh_run_id=payload.master_refresh_run_id, games=games
        )
    all_explanation_statuses = [p.status for p in explainability_result.products] + [l.status for l in explainability_result.legs]
    all_snapshot_statuses = [p.status for p in time_machine_result.snapshots] + [l.status for l in time_machine_result.legs]
    return FinalizeStrategyResponse(
        outcome=decision.outcome,
        recommendation_product_ids=created_ids,
        leg_count=len(decision.legs),
        no_bet_game_count=sum(1 for d in decision.game_decisions if d.outcome == "no_bet"),
        explanations_generated=sum(1 for s in all_explanation_statuses if s == "generated"),
        explanations_failed=sum(1 for s in all_explanation_statuses if s == "failed"),
        activation_snapshots_generated=sum(1 for s in all_snapshot_statuses if s == "generated"),
        activation_snapshots_failed=sum(1 for s in all_snapshot_statuses if s == "failed"),
    )


class RunPostgameGradingRequest(BaseModel):
    """Milestone 5.4's Postgame Grading entry point request. `game_ids`
    is whatever `apps/workers` already determined are grading-candidate
    games (its own `games` read, mirroring the Recommendation Worker's
    own eligibility-discovery-then-dispatch split) -- this endpoint never
    discovers eligibility itself, only grades what it's told to look at.
    A game not yet reconciliation-eligible is a safe, cheap no-op here
    (see `app.orchestration.postgame_grading`), so `apps/workers` can
    pass a generously-bounded candidate list without this endpoint
    misgrading anything."""

    game_ids: list[str]


class LegGradingResponseItem(BaseModel):
    leg_id: str
    recommendation_product_id: str
    status: str
    outcome: str | None
    error: str | None


class ProductGradingResponseItem(BaseModel):
    product_id: str
    status: str
    outcome: str | None


class GameGradingResponseItem(BaseModel):
    game_id: str
    status: str
    legs: list[LegGradingResponseItem]
    no_bet_products: list[ProductGradingResponseItem]
    products: list[ProductGradingResponseItem]


class RunPostgameGradingResponse(BaseModel):
    games: list[GameGradingResponseItem]
    bankroll_preservation_products: list[ProductGradingResponseItem]
    postgame_reviews_generated: int
    postgame_reviews_failed: int
    postgame_reviews_skipped: int


@app.post(
    "/v1/internal/postgame-grading/run",
    dependencies=[Depends(require_internal_token)],
    response_model=RunPostgameGradingResponse,
)
async def internal_run_postgame_grading(payload: RunPostgameGradingRequest) -> RunPostgameGradingResponse:
    """Milestone 5.4's Postgame Review entry point -- reachable only via
    `INTERNAL_SERVICE_TOKEN`, called by `apps/workers` once it has
    discovered which `game_ids` are grading candidates (see
    `app.orchestration.postgame_grading`'s own module docstring for the
    reconciliation-eligibility mechanism this endpoint applies per
    game). Grades every game's legs/no_bet products, rolls up any
    leg-bearing product whose every leg is now terminally graded, sweeps
    every `bankroll_preservation` product (unconditional, no game-data
    dependency), then generates a Postgame Review narrative (Decision BU
    -- `FakeModelAdapter` in dev/testing, real providers only once a real
    `postgame_review_narrative` routing rule AND real API keys both
    exist, neither of which this endpoint creates) for every
    newly-graded, non-NOT_APPLICABLE product rollup."""
    headers = supabase_client.auth_headers()
    async with supabase_client.new_client(timeout=60.0) as client:
        routing_rule_rows = await list_active_model_routing_rules(client, headers)
        routing_rules = {row["task_type"]: row for row in routing_rule_rows}
        model_rows = await list_active_models(client, headers)
        model_providers = {row["model_name"]: row["provider"] for row in model_rows}
        adapter_registry = _build_real_adapter_registry()

        game_results = []
        review_stats = {"generated": 0, "failed": 0, "skipped": 0}
        for game_id in payload.game_ids:
            result = await grade_game(client, headers, game_id=game_id)
            for product in result.products:
                if (
                    product.status in ("created", "corrected")
                    and product.outcome not in ("NOT_APPLICABLE", "PENDING_MISSING_DATA")
                    and product.grade_event_id is not None
                ):
                    review = await generate_and_persist_postgame_review(
                        client,
                        headers,
                        recommendation_product_id=product.product_id,
                        product_grade_event_id=product.grade_event_id,
                        grading_version=GRADING_VERSION,
                        outcome=product.outcome,
                        routing_rules=routing_rules,
                        adapter_registry=adapter_registry,
                        model_providers=model_providers,
                    )
                    if review.status == "generated":
                        review_stats["generated"] += 1
                    elif review.status == "failed":
                        review_stats["failed"] += 1
                    else:
                        review_stats["skipped"] += 1
            game_results.append(result)

        bankroll_results = await grade_pending_bankroll_preservation_products(client, headers)

    return RunPostgameGradingResponse(
        games=[
            GameGradingResponseItem(
                game_id=g.game_id,
                status=g.status,
                legs=[LegGradingResponseItem(leg_id=l.leg_id, recommendation_product_id=l.recommendation_product_id, status=l.status, outcome=l.outcome, error=l.error) for l in g.legs],
                no_bet_products=[ProductGradingResponseItem(product_id=p.product_id, status=p.status, outcome=p.outcome) for p in g.no_bet_products],
                products=[ProductGradingResponseItem(product_id=p.product_id, status=p.status, outcome=p.outcome) for p in g.products],
            )
            for g in game_results
        ],
        bankroll_preservation_products=[ProductGradingResponseItem(product_id=p.product_id, status=p.status, outcome=p.outcome) for p in bankroll_results],
        postgame_reviews_generated=review_stats["generated"],
        postgame_reviews_failed=review_stats["failed"],
        postgame_reviews_skipped=review_stats["skipped"],
    )


class RunAdaptiveWeightingRequest(BaseModel):
    """Milestone 5.5's Adaptive Agent Weighting entry point request.
    `evaluation_window_days` defaults to the Blueprint's own rolling
    90-day minimum (Decision 8) -- a caller may widen it, but
    `app.orchestration.adaptive_weighting.evaluate_committee` rejects
    anything narrower, never silently widening it back up."""

    evaluation_window_days: int = ADAPTIVE_WEIGHT_MIN_WINDOW_DAYS


class AgentEvaluationResponseItem(BaseModel):
    agent_id: str
    agent_name: str
    status: str
    proposal_status: str
    sample_size: int
    roi: float | None
    performance_delta: float | None
    guardrail_adjusted_proposed_weight: float | None


class RunAdaptiveWeightingResponse(BaseModel):
    evaluation_window_start: str
    evaluation_window_end: str
    committee_average_roi: float | None
    agents: list[AgentEvaluationResponseItem]


@app.post(
    "/v1/internal/adaptive-weighting/run",
    dependencies=[Depends(require_internal_token)],
    response_model=RunAdaptiveWeightingResponse,
)
async def internal_run_adaptive_weighting(payload: RunAdaptiveWeightingRequest) -> RunAdaptiveWeightingResponse:
    """Milestone 5.5's Adaptive Agent Weighting entry point -- reachable
    only via `INTERNAL_SERVICE_TOKEN`, called by `apps/workers` on a
    schedule (`worker-scheduled`, Decision 21 -- no new Railway service).

    **PROPOSE-ONLY (Decision 2): this endpoint NEVER writes
    `agents.current_weight`.** It computes and persists, for every agent,
    what weight change the Blueprint's Section 6.1 formula and guardrails
    would produce -- nothing more. Applying a proposal is a separate,
    not-yet-authorized future capability. See
    `app.orchestration.adaptive_weighting`'s own module docstring for the
    full evidence-gathering and guardrail design."""
    now = datetime.now(timezone.utc).date()
    window_end = now
    window_start = window_end - timedelta(days=payload.evaluation_window_days)

    headers = supabase_client.auth_headers()
    async with supabase_client.new_client(timeout=60.0) as client:
        try:
            result = await evaluate_committee(
                client, headers, evaluation_window_start=window_start, evaluation_window_end=window_end
            )
        except EvaluationWindowTooShortError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RunAdaptiveWeightingResponse(
        evaluation_window_start=result.evaluation_window_start,
        evaluation_window_end=result.evaluation_window_end,
        committee_average_roi=result.committee_average_roi,
        agents=[
            AgentEvaluationResponseItem(
                agent_id=a.agent_id, agent_name=a.agent_name, status=a.status, proposal_status=a.proposal_status,
                sample_size=a.sample_size, roi=a.roi, performance_delta=a.performance_delta,
                guardrail_adjusted_proposed_weight=a.guardrail_adjusted_proposed_weight,
            )
            for a in result.agents
        ],
    )


if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":

    @app.get("/sentry-debug")
    async def trigger_error():
        division_by_zero = 1 / 0
