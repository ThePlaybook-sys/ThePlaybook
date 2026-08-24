"""Recommendation-cycle and agent-output persistence (Milestone 4.5).

**Option C (Mac's approval, 2026-08-21):** `recommendations` is a neutral
recommendation-cycle/run container. Phase 4 creates the row early --
`game_id`, `prompt_version`, `agent_version` -- so
`recommendation_agent_outputs` has a valid `recommendation_id` to attach
to. Phase 5 later completes the SAME row via `UPDATE`
(`recommendation_type`, `bet_details`, `confidence_score`,
`expected_value`, `risk_level`, `consensus_version`, `weight_version`,
`display_id`, `status`) -- this module never creates a second row for the
same analysis cycle, and never touches any Phase-5-owned field.

**Decision B (status/user_facing):** `status` is left `NULL` at creation
-- none of the existing CHECK-constraint values (`active`, `withdrawn`,
`settled_win`, `settled_loss`, `settled_push`) honestly represent "an
analysis cycle exists but no final recommendation decision has been
issued yet," and `status` is nullable with no default, so `NULL` is the
non-fabricated choice rather than misusing `active`. `user_facing` is
explicitly set `False` (overriding the column's `true` default) --
nothing exists yet that should be shown to a user.

**Decision A (idempotency, A1 approved for 4.5):** this module creates
exactly one row per call -- no lookup-before-insert, no dedup. Callers
(`app.orchestration.cycle`) are responsible for calling
`create_recommendation_cycle` exactly once per in-memory orchestration
run and reusing the returned id for every output write in that run. A
crashed-and-retried run may create a second cycle row -- an accepted
limitation for 4.5 (Mac's own words: "acceptable ONLY because the real
Recommendation Worker / scheduled retry path does not exist yet"),
carried forward as a REQUIRED Milestone 4.9 design checkpoint before any
real Recommendation Worker exists.

**Decision C (weight_applied):** `recommendation_agent_outputs.
weight_applied` stores `agents.current_weight` as it existed at the
moment that specific output was persisted -- a frozen historical copy,
read once and written as a plain value, never re-derived through a live
join. A later change to `agents.current_weight` cannot retroactively
alter an already-persisted `weight_applied`.

**Milestone 4.8 (Prompt Provenance decision):** `persist_agent_output`/
`persist_candidate_agent_output` now also accept `prompt_name`/
`prompt_version` -- the exact `prompt_registry` row
(`app.persistence.model_config.resolve_active_prompt`) actually resolved
and used to build that specific agent's system prompt, supplied by the
orchestration layer (`app.orchestration.fanout`/`.sequential`), never
guessed or re-derived here. Frozen exactly like `weight_applied`: a later
change to which prompt version is active cannot retroactively alter an
already-persisted row. `recommendations.prompt_version` remains a
separate, legacy/non-authoritative field (see Volume 3) -- these
per-output columns are the canonical per-agent Time Machine provenance."""
from __future__ import annotations

import httpx

from app.agents.contract import AgentOutput


class RecommendationsError(Exception):
    """Raised when a `recommendations` write/read fails on Supabase's
    side."""


class AgentConfigError(Exception):
    """Raised when an agent's `agent_name` has no matching `agents` row.
    Never silently skipped -- Mac's explicit instruction: 'If an agent
    name cannot resolve to agents.id: FAIL CLEARLY.'"""


async def create_recommendation_cycle(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, prompt_version: str, agent_version: str
) -> str:
    """Creates one `recommendations` row representing a new
    recommendation-analysis cycle (Option C). Populates ONLY the fields
    Phase 4 owns at this point -- see module docstring. Returns the new
    row's `id`."""
    payload = {
        "game_id": game_id,
        "prompt_version": prompt_version,
        "agent_version": agent_version,
        "user_facing": False,
        "status": None,
    }
    response = await client.post(
        "/rest/v1/recommendations",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise RecommendationsError(
            f"failed to create recommendation cycle for game_id={game_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise RecommendationsError(f"recommendation cycle insert for game_id={game_id!r} returned no row")
    return rows[0]["id"]


async def resolve_agent(client: httpx.AsyncClient, headers: dict, *, agent_name: str) -> dict:
    """Reads `agents.id`/`agents.current_weight` by `name`. Raises
    `AgentConfigError` when no row matches -- never returns a
    placeholder or a default weight."""
    response = await client.get(
        "/rest/v1/agents",
        params={"name": f"eq.{agent_name}", "select": "id,current_weight"},
        headers=headers,
    )
    if response.status_code != 200:
        raise RecommendationsError(
            f"failed to resolve agent {agent_name!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise AgentConfigError(
            f"no agents row found for agent_name={agent_name!r} -- cannot persist its output without a configured agent"
        )
    return rows[0]


async def persist_agent_output(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_id: str,
    agent_name: str,
    output: AgentOutput,
    prompt_name: str | None = None,
    prompt_version: int | None = None,
) -> None:
    """Persists exactly one `recommendation_agent_outputs` row for a
    successful agent output. Never called for a failed agent -- callers
    (`app.orchestration.cycle`) iterate only `FanOutResult.successes`.
    `candidate_key` stays `NULL` -- this is the game-level fan-out path
    (Milestones 4.4/4.5), not a candidate-specific evaluation.
    `prompt_name`/`prompt_version` (Milestone 4.8) are the exact resolved
    prompt identity the caller's orchestration layer used for this
    agent's system prompt -- `None` only for a caller that genuinely has
    none (there is no other legitimate reason to omit them for a real
    agent run)."""
    agent = await resolve_agent(client, headers, agent_name=agent_name)
    payload = {
        "recommendation_id": recommendation_id,
        "agent_id": agent["id"],
        "raw_output": output.model_dump(mode="json"),
        "agent_confidence": output.confidence,
        "weight_applied": agent["current_weight"],
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
    }
    response = await client.post(
        "/rest/v1/recommendation_agent_outputs",
        json=payload,
        headers={**headers, "Content-Type": "application/json"},
    )
    if response.status_code not in (200, 201):
        raise RecommendationsError(
            f"failed to persist agent output for {agent_name!r} on recommendation_id={recommendation_id!r}: "
            f"{response.status_code} {response.text}"
        )


async def persist_candidate_agent_output(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_id: str,
    agent_name: str,
    candidate_key: str,
    raw_output: dict,
    agent_confidence: float | None,
    prompt_name: str | None = None,
    prompt_version: int | None = None,
) -> None:
    """Persists one candidate-level `recommendation_agent_outputs` row
    for the sequential Decision & Advisory chain (Milestone 4.6, Decision
    G) -- `candidate_key` is a first-class, queryable column, not buried
    inside `raw_output`. `raw_output` itself carries the full structured
    result for auditability (`{"probability_output": {...}}` for
    Probability Modeling, or `{"agent_output": {...}, "deterministic":
    {...}}` for Expected Value/Risk Manager/Bankroll Coach -- callers
    build this shape, this function stays agnostic to which Pydantic
    contract produced it).

    No uniqueness check against an existing `(recommendation_id,
    agent_id, candidate_key)` row -- multiple evaluations of the same
    candidate may legitimately exist over time (Decision G, no
    uniqueness constraint approved). `prompt_name`/`prompt_version`
    (Milestone 4.8): see `persist_agent_output`'s identical note."""
    agent = await resolve_agent(client, headers, agent_name=agent_name)
    payload = {
        "recommendation_id": recommendation_id,
        "agent_id": agent["id"],
        "raw_output": raw_output,
        "agent_confidence": agent_confidence,
        "weight_applied": agent["current_weight"],
        "candidate_key": candidate_key,
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
    }
    response = await client.post(
        "/rest/v1/recommendation_agent_outputs",
        json=payload,
        headers={**headers, "Content-Type": "application/json"},
    )
    if response.status_code not in (200, 201):
        raise RecommendationsError(
            f"failed to persist candidate agent output for {agent_name!r} "
            f"on recommendation_id={recommendation_id!r} candidate_key={candidate_key!r}: "
            f"{response.status_code} {response.text}"
        )
