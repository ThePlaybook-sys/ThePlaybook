"""Read-only AI-orchestration configuration access (Milestone 4.1).

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

**Dev's current rows behind these readers are Phase-1 `seed.sql` fixture
data, not a real Phase 4 configuration** (6 agents whose names only
partially match the real 22-agent committee, 2 routing rules, 2 models, 2
prompts) -- see `PROGRESS.md`'s Milestone 4.1 entry for the full
inspection and the proposed cleanup this module deliberately does not
perform. These readers return whatever rows actually exist; they do not
know or care whether those rows are real or fixture data.
"""
from __future__ import annotations

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
