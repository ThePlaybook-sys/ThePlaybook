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
