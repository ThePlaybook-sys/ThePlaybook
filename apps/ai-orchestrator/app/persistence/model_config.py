"""Read-only AI-orchestration configuration access (Milestone 4.1;
`resolve_active_prompt` added Milestone 4.8).

Covers the four config/registry tables Phase 4's committee will need to
read once agents/model adapters actually exist (Milestone 4.2+):
`agents`, `model_routing_rules`, `model_registry`, `prompt_registry`.
Nothing in this module writes to any of these tables, and nothing here
interprets or acts on what it reads -- that is later milestones' job.
This milestone only proves the read contract.

Every reader filters to the "currently usable" subset of its table
(`agents.active = true`, `model_routing_rules.active = true`,
`model_registry.status = 'active'`, `prompt_registry.status = 'active'`)
-- a deactivated agent, a retired model, or a draft/deprecated prompt is
never silently returned to a caller that didn't ask for history.

**Dev's current rows behind these readers were Phase-1 `seed.sql` fixture
data for `agents`/`model_routing_rules`/`model_registry`** -- see
`PROGRESS.md`'s Milestone 4.1 entry for the full inspection.
`prompt_registry` additionally carried two unrelated Phase-1 fixture rows
(`nfl_parlay_v1.0`, `nfl_single_v1.0`, a different "recommendation-type
prompt" concept) alongside which Milestone 4.8 seeds the 12 real agents'
canonical prompts, one per `agent_name`, per Mac's approved
`prompt_name = agent_name` convention.

**`resolve_active_prompt` (Milestone 4.8) is the one function in this
module callers outside this file should actually use for prompt
resolution** -- `get_active_prompt` (below) remains as the thin per-row
Milestone 4.1 reader it always was, but has no caller of its own left
once `resolve_active_prompt` exists; kept for backward compatibility
rather than removed mid-milestone. `resolve_active_prompt` is deterministic
and fails loud (`PromptConfigError`) rather than ever silently choosing
between rows or falling back to hardcoded text -- see its own docstring.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx


class ConfigReadError(Exception):
    """Raised when a configuration-table read fails on Supabase's side."""


async def list_active_agents(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    response = await client.get(
        "/rest/v1/agents",
        params={
            "active": "eq.true",
            "select": "id,name,category,active,current_weight",
            "order": "name.asc",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ConfigReadError(f"failed to list active agents: {response.status_code} {response.text}")
    return response.json()


async def get_model_routing_rule(client: httpx.AsyncClient, headers: dict, *, task_type: str) -> dict | None:
    response = await client.get(
        "/rest/v1/model_routing_rules",
        params={
            "task_type": f"eq.{task_type}",
            "active": "eq.true",
            "select": "id,task_type,primary_model,fallback_model,min_tier_for_second_pass,active",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ConfigReadError(
            f"failed to read model_routing_rules for task_type {task_type!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def list_active_model_routing_rules(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    response = await client.get(
        "/rest/v1/model_routing_rules",
        params={
            "active": "eq.true",
            "select": "id,task_type,primary_model,fallback_model,min_tier_for_second_pass,active",
            "order": "task_type.asc",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ConfigReadError(f"failed to list active model_routing_rules: {response.status_code} {response.text}")
    return response.json()


async def get_model(client: httpx.AsyncClient, headers: dict, *, model_name: str) -> dict | None:
    response = await client.get(
        "/rest/v1/model_registry",
        params={"model_name": f"eq.{model_name}", "status": "eq.active", "select": "*"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ConfigReadError(
            f"failed to read model_registry for {model_name!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def get_active_prompt(client: httpx.AsyncClient, headers: dict, *, prompt_name: str) -> dict | None:
    response = await client.get(
        "/rest/v1/prompt_registry",
        params={"prompt_name": f"eq.{prompt_name}", "status": "eq.active", "select": "*"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ConfigReadError(
            f"failed to read prompt_registry for {prompt_name!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


class PromptConfigError(Exception):
    """Raised when an agent requires a canonical production prompt and
    none can be resolved -- no active `prompt_registry` row for its
    `prompt_name` (Milestone 4.8 convention: `prompt_name = agent_name`),
    or (defense in depth) more than one active row, which
    `idx_prompt_registry_one_active_per_name` should already make
    impossible to write. Never silently rescued with hardcoded text --
    mirrors `app.models.router.UnknownProviderError`'s "fail loud rather
    than silently defaulting" precedent."""


@dataclass(frozen=True)
class ResolvedPrompt:
    """The exact, already-versioned prompt actually resolved for one
    agent's execution -- `prompt_name`/`version` are persisted verbatim
    as `recommendation_agent_outputs.prompt_name`/`.prompt_version`
    (Milestone 4.8), so this is the Time Machine provenance record for
    "which prompt produced this specific output", not just an
    implementation detail."""

    prompt_name: str
    version: int
    prompt_text: str


async def resolve_active_prompt(client: httpx.AsyncClient, headers: dict, *, prompt_name: str) -> ResolvedPrompt:
    """The canonical production prompt-resolution call (Milestone 4.8) --
    every agent's system prompt is resolved through this function at the
    orchestration/harness boundary (never inside an agent class itself,
    per Mac's explicit Option C direction). Deterministic: the live
    `idx_prompt_registry_one_active_per_name` partial unique index
    already makes more than one active row per `prompt_name` impossible
    to write, but this function still defensively checks for it rather
    than trusting the constraint alone -- "do not silently choose between
    multiple active prompts if invalid configuration somehow exists" is
    enforced here, not assumed from the schema.

    Raises `PromptConfigError` (never returns `None`, never falls back to
    any hardcoded template) when zero or more than one active row exists
    for `prompt_name` -- a caller with a real, configured agent should
    never see this in production; a caller in a test supplies its own
    prompt text directly to `build_messages` instead of calling this at
    all, so this failure mode is exclusively a production-configuration
    signal, never a test-determinism concern (FakeModelAdapter ignores
    prompt content entirely)."""
    response = await client.get(
        "/rest/v1/prompt_registry",
        params={"prompt_name": f"eq.{prompt_name}", "status": "eq.active", "select": "prompt_name,version,prompt_text"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ConfigReadError(
            f"failed to read prompt_registry for {prompt_name!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise PromptConfigError(
            f"no active prompt_registry row for prompt_name={prompt_name!r} -- cannot execute this agent "
            f"without a configured canonical production prompt"
        )
    if len(rows) > 1:
        raise PromptConfigError(
            f"invalid prompt_registry configuration: {len(rows)} active rows found for "
            f"prompt_name={prompt_name!r}, expected exactly one"
        )
    row = rows[0]
    return ResolvedPrompt(prompt_name=row["prompt_name"], version=row["version"], prompt_text=row["prompt_text"])
