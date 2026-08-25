import os

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
from app.orchestration.recommendation_worker import RecommendationWorkerError, run_game_recommendation
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


class CandidateRunResponseItem(BaseModel):
    candidate_key: str
    status: str
    shared_chain_status: str | None
    consensus_status: str | None
    second_pass_triggered: bool
    bankroll_coach_user_count: int
    error: str | None


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
            )
            for c in result.candidates
        ],
    )


if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":

    @app.get("/sentry-debug")
    async def trigger_error():
        division_by_zero = 1 / 0
