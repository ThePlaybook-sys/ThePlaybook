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

**Decision A (idempotency, A1 approved for 4.5) -- superseded by Milestone
4.9's durable `correlation_id` design.** `create_recommendation_cycle` now
accepts an optional `correlation_id`. When supplied, the write becomes a
PostgREST upsert keyed on `correlation_id` (`Prefer:
resolution=merge-duplicates` + `on_conflict=correlation_id`) -- a retry
that reuses the same `correlation_id` recovers the SAME row's `id`
instead of creating a second cycle, closing the gap Milestone 4.5
explicitly carried forward. `correlation_id` is stable-derived by the
caller (Milestone 4.9: `stable(master_refresh_run_id, game_id)`, never a
random UUID a crash couldn't reproduce) -- this module has no opinion on
how it's built, only that reusing the same value reuses the same row.
Omitting `correlation_id` (the default, `None`) preserves the exact
pre-4.9 blind-insert behavior unchanged, for any caller that doesn't yet
have a stable identity to key on (e.g. existing tests, on-demand NL
Engine requests in a future phase that may use a different idempotency
strategy).

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
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    prompt_version: str,
    agent_version: str,
    correlation_id: str | None = None,
) -> str:
    """Creates (or, when `correlation_id` is supplied and already exists,
    RECOVERS) one `recommendations` row representing a recommendation-
    analysis cycle (Option C). Populates ONLY the fields Phase 4 owns at
    this point -- see module docstring. Returns the row's `id`.

    Milestone 4.9: with `correlation_id` supplied, this is a PostgREST
    upsert keyed on that column's `unique` constraint -- a retry that
    passes the SAME `correlation_id` gets back the SAME `id`, never a
    second row. Without it (the default), behaves exactly as it always
    has: a blind insert, one new row per call."""
    payload = {
        "game_id": game_id,
        "prompt_version": prompt_version,
        "agent_version": agent_version,
        "user_facing": False,
        "status": None,
    }
    params = {}
    prefer = "return=representation"
    if correlation_id is not None:
        payload["correlation_id"] = correlation_id
        params["on_conflict"] = "correlation_id"
        prefer = "resolution=merge-duplicates," + prefer
    response = await client.post(
        "/rest/v1/recommendations",
        json=payload,
        params=params,
        headers={**headers, "Content-Type": "application/json", "Prefer": prefer},
    )
    if response.status_code not in (200, 201):
        raise RecommendationsError(
            f"failed to create recommendation cycle for game_id={game_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise RecommendationsError(f"recommendation cycle insert for game_id={game_id!r} returned no row")
    return rows[0]["id"]


async def read_recommendation_by_correlation_id(client: httpx.AsyncClient, headers: dict, *, correlation_id: str) -> dict | None:
    """Pre-Phase-6 Operational Readiness Gate, Decision 5. Reads back the
    `recommendations` row for this correlation, if one exists yet --
    `None` when this is genuinely the first attempt at this
    `(master_refresh_run_id, game_id)` pair. Returns `id`/
    `cycle_completed_at` only: this is a cheap pre-flight check, not a
    full row read."""
    response = await client.get(
        "/rest/v1/recommendations",
        params={"correlation_id": f"eq.{correlation_id}", "select": "id,cycle_completed_at"},
        headers=headers,
    )
    if response.status_code != 200:
        raise RecommendationsError(
            f"failed to read recommendation by correlation_id={correlation_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def mark_recommendation_cycle_completed(
    client: httpx.AsyncClient, headers: dict, *, recommendation_id: str, completed_at_iso: str
) -> None:
    """Pre-Phase-6 Operational Readiness Gate, Decision 5. Stamps
    `cycle_completed_at` -- called exactly once, as the LAST step of a
    successful `run_game_recommendation` call, regardless of whether
    individual candidates within it succeeded or were isolated failures
    (per-candidate failure isolation is unchanged and orthogonal to this
    marker: the CYCLE, as a process, reached its normal end). Never
    called on any other path -- a cycle that raises before reaching here
    leaves this row's marker `NULL`, which is exactly what makes a
    crashed/incomplete attempt safely retryable. `completed_at_iso` is
    caller-supplied (mirrors `app.persistence.master_refresh_runs.
    complete_master_refresh_run`'s own `completed_at_iso` parameter) so
    the timestamp is injectable/deterministic in tests, never a bare
    `now()` string PostgREST would store literally rather than evaluate."""
    response = await client.patch(
        "/rest/v1/recommendations",
        json={"cycle_completed_at": completed_at_iso},
        params={"id": f"eq.{recommendation_id}"},
        headers={**headers, "Content-Type": "application/json"},
    )
    if response.status_code not in (200, 204):
        raise RecommendationsError(
            f"failed to mark recommendation cycle completed for recommendation_id={recommendation_id!r}: "
            f"{response.status_code} {response.text}"
        )


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
    model_name: str | None = None,
    provider: str | None = None,
    used_fallback: bool | None = None,
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
    agent run). `model_name`/`provider`/`used_fallback` (Milestone 5.3,
    Decision AV) are the ACTUAL model/provider that produced this output
    (`AgentRunResult.model_name`/`.provider`/`.used_fallback`, sourced
    from `ModelResponse.usage`) -- never the routing rule's requested
    `primary_model`. `None` for a caller with no such data (e.g. a test
    fixture predating this milestone) -- never inferred or guessed."""
    agent = await resolve_agent(client, headers, agent_name=agent_name)
    payload = {
        "recommendation_id": recommendation_id,
        "agent_id": agent["id"],
        "raw_output": output.model_dump(mode="json"),
        "agent_confidence": output.confidence,
        "weight_applied": agent["current_weight"],
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "model_name": model_name,
        "provider": provider,
        "used_fallback": used_fallback,
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
    model_name: str | None = None,
    provider: str | None = None,
    used_fallback: bool | None = None,
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
    (Milestone 4.8): see `persist_agent_output`'s identical note.
    `model_name`/`provider`/`used_fallback` (Milestone 5.3, Decision AV):
    same note."""
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
        "model_name": model_name,
        "provider": provider,
        "used_fallback": used_fallback,
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
