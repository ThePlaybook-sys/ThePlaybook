"""HTTP client for `ai-orchestrator`'s internal Recommendation Worker
endpoint (Milestone 4.9). Service-to-service call, authenticated via
`INTERNAL_SERVICE_TOKEN` (Volume 2 Section 6/10) -- never the user's
JWT. This is the ONLY way this service talks to `ai-orchestrator`; it
never imports or duplicates any of `ai-orchestrator`'s AI/business
logic, per Mac's explicit "no duplicated AI logic in workers"
instruction."""
from __future__ import annotations

import httpx


class AiOrchestratorCallError(Exception):
    """Raised when the internal call to `ai-orchestrator` fails -- a
    non-2xx response, or a transport-level error. Callers (`app.
    recommendation_worker`) isolate this per game, never letting one
    game's failure abort the rest of the slate."""


async def run_game_recommendation(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    internal_token: str,
    game_id: str,
    correlation_id: str,
    prompt_version: str,
    agent_version: str,
) -> dict:
    """Calls `POST {base_url}/v1/internal/recommendation-worker/run-game`
    for exactly one game. Returns the endpoint's parsed JSON response on
    success. Raises `AiOrchestratorCallError` on any non-2xx response or
    transport failure -- never silently swallowed here, isolation is the
    caller's responsibility (mirrors every other per-unit isolation
    boundary already established in this codebase)."""
    try:
        response = await client.post(
            f"{base_url}/v1/internal/recommendation-worker/run-game",
            json={
                "game_id": game_id,
                "correlation_id": correlation_id,
                "prompt_version": prompt_version,
                "agent_version": agent_version,
            },
            headers={"X-Internal-Token": internal_token, "Content-Type": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise AiOrchestratorCallError(f"transport failure calling ai-orchestrator for game_id={game_id!r}: {exc}") from exc
    if response.status_code != 200:
        raise AiOrchestratorCallError(
            f"ai-orchestrator returned {response.status_code} for game_id={game_id!r}: {response.text}"
        )
    return response.json()


async def finalize_slate_strategy(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    internal_token: str,
    master_refresh_run_id: str,
    games: list[dict],
) -> dict:
    """Calls `POST {base_url}/v1/internal/recommendation-worker/
    finalize-strategy` exactly once per Recommendation Worker cycle, after
    every eligible game's `run_game_recommendation` call has completed
    (Milestone 5.1). `games` is `[{"game_id", "recommendation_id",
    "candidates": [...]}]` -- each game's `candidates` list is the
    `strategy_input` field already returned by that game's own `run-game`
    response, relayed unmodified; this function/module never inspects or
    recomputes any of it. Raises `AiOrchestratorCallError` on any non-2xx
    response or transport failure, exactly like `run_game_recommendation` --
    unlike per-game dispatch, a failure here is NOT isolated by this
    module; the caller decides how to record it (there is no smaller unit
    than "the whole slate" for this call)."""
    try:
        response = await client.post(
            f"{base_url}/v1/internal/recommendation-worker/finalize-strategy",
            json={"master_refresh_run_id": master_refresh_run_id, "games": games},
            headers={"X-Internal-Token": internal_token, "Content-Type": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise AiOrchestratorCallError(f"transport failure calling ai-orchestrator finalize-strategy: {exc}") from exc
    if response.status_code != 200:
        raise AiOrchestratorCallError(
            f"ai-orchestrator finalize-strategy returned {response.status_code}: {response.text}"
        )
    return response.json()


async def run_postgame_grading(
    client: httpx.AsyncClient, *, base_url: str, internal_token: str, game_ids: list[str]
) -> dict:
    """Calls `POST {base_url}/v1/internal/postgame-grading/run` once per
    Postgame Grading Worker cycle (Milestone 5.4) with every candidate
    `game_ids` this service discovered (`app.persistence.games.
    read_grading_candidate_game_ids`) -- `ai-orchestrator`'s own endpoint
    decides per-game reconciliation-eligibility; this call is a single
    batch dispatch, not one call per game (unlike `run_game_recommendation`,
    which has a real per-game persistence/idempotency reason to be
    separate calls -- grading has no such requirement, and one call keeps
    this cheap for however many stale candidates the lookback window
    finds). Raises `AiOrchestratorCallError` on any non-2xx response or
    transport failure, exactly like every other call in this module."""
    try:
        response = await client.post(
            f"{base_url}/v1/internal/postgame-grading/run",
            json={"game_ids": game_ids},
            headers={"X-Internal-Token": internal_token, "Content-Type": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise AiOrchestratorCallError(f"transport failure calling ai-orchestrator postgame-grading: {exc}") from exc
    if response.status_code != 200:
        raise AiOrchestratorCallError(
            f"ai-orchestrator postgame-grading returned {response.status_code}: {response.text}"
        )
    return response.json()
