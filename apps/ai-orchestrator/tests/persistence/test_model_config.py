"""Tests for app.persistence.model_config (Milestone 4.1;
resolve_active_prompt/PromptConfigError/ResolvedPrompt added Milestone 4.8)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.model_config import (
    ConfigReadError,
    PromptConfigError,
    ResolvedPrompt,
    get_active_prompt,
    get_model,
    get_model_routing_rule,
    list_active_agents,
    list_active_model_routing_rules,
    resolve_active_prompt,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_list_active_agents_filters_active_true():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "a1", "name": "injury_intelligence_agent", "active": True}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await list_active_agents(client, _headers())
    assert len(result) == 1
    request = respx.calls.last.request
    assert request.url.params["active"] == "eq.true"


@pytest.mark.asyncio
@respx.mock
async def test_list_active_agents_empty_is_not_an_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await list_active_agents(client, _headers())
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_list_active_agents_raises_on_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ConfigReadError):
            await list_active_agents(client, _headers())


@pytest.mark.asyncio
@respx.mock
async def test_get_model_routing_rule_returns_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/model_routing_rules").mock(
        return_value=httpx.Response(200, json=[{"task_type": "injury_analysis", "primary_model": "claude-sonnet-5"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await get_model_routing_rule(client, _headers(), task_type="injury_analysis")
    assert result["primary_model"] == "claude-sonnet-5"


@pytest.mark.asyncio
@respx.mock
async def test_get_model_routing_rule_returns_none_when_absent():
    respx.get(f"{SUPABASE_URL}/rest/v1/model_routing_rules").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await get_model_routing_rule(client, _headers(), task_type="unknown_task")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_list_active_model_routing_rules():
    respx.get(f"{SUPABASE_URL}/rest/v1/model_routing_rules").mock(
        return_value=httpx.Response(200, json=[{"task_type": "injury_analysis"}, {"task_type": "consensus_reconciliation"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await list_active_model_routing_rules(client, _headers())
    assert len(result) == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_model_returns_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/model_registry").mock(
        return_value=httpx.Response(200, json=[{"model_name": "claude-sonnet-5", "status": "active"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await get_model(client, _headers(), model_name="claude-sonnet-5")
    assert result["model_name"] == "claude-sonnet-5"


@pytest.mark.asyncio
@respx.mock
async def test_get_model_returns_none_when_absent_or_retired():
    respx.get(f"{SUPABASE_URL}/rest/v1/model_registry").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await get_model(client, _headers(), model_name="retired-model")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_get_active_prompt_returns_row():
    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(
        return_value=httpx.Response(200, json=[{"prompt_name": "injury_intelligence_agent", "status": "active", "version": 3}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await get_active_prompt(client, _headers(), prompt_name="injury_intelligence_agent")
    assert result["version"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_get_active_prompt_returns_none_when_only_draft_exists():
    # PostgREST filter itself excludes non-active rows -- simulated here by
    # returning empty, proving the caller correctly treats "filtered out" the
    # same as "doesn't exist" rather than assuming a draft/deprecated row.
    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await get_active_prompt(client, _headers(), prompt_name="draft_only_prompt")
    assert result is None
    request = respx.calls.last.request
    assert request.url.params["status"] == "eq.active"


@pytest.mark.asyncio
@respx.mock
async def test_get_active_prompt_raises_on_malformed_response():
    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(
        return_value=httpx.Response(200, text="not json", headers={"content-type": "application/json"})
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(Exception):
            await get_active_prompt(client, _headers(), prompt_name="whatever")


# --- resolve_active_prompt (Milestone 4.8) ---


@pytest.mark.asyncio
@respx.mock
async def test_resolve_active_prompt_returns_resolved_prompt():
    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(
        return_value=httpx.Response(
            200, json=[{"prompt_name": "weather_agent", "version": 3, "prompt_text": "You are the weather_agent..."}]
        )
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_active_prompt(client, _headers(), prompt_name="weather_agent")
    assert result == ResolvedPrompt(prompt_name="weather_agent", version=3, prompt_text="You are the weather_agent...")
    request = respx.calls.last.request
    assert request.url.params["prompt_name"] == "eq.weather_agent"
    assert request.url.params["status"] == "eq.active"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_active_prompt_raises_prompt_config_error_when_missing():
    """Production must fail clearly, never silently fall back to
    hardcoded text -- an agent with no active prompt_registry row raises
    PromptConfigError, distinct from ConfigReadError (a transport/DB
    failure)."""
    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(PromptConfigError, match="no active prompt_registry row"):
            await resolve_active_prompt(client, _headers(), prompt_name="nonexistent_agent")


@pytest.mark.asyncio
@respx.mock
async def test_resolve_active_prompt_raises_on_multiple_active_rows_defense_in_depth():
    """idx_prompt_registry_one_active_per_name should already make this
    impossible to write live, but resolve_active_prompt does not trust
    the constraint alone -- it never silently picks one row when more
    than one is returned."""
    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"prompt_name": "weather_agent", "version": 1, "prompt_text": "old"},
                {"prompt_name": "weather_agent", "version": 2, "prompt_text": "new"},
            ],
        )
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(PromptConfigError, match="invalid prompt_registry configuration"):
            await resolve_active_prompt(client, _headers(), prompt_name="weather_agent")


@pytest.mark.asyncio
@respx.mock
async def test_resolve_active_prompt_never_returns_a_deprecated_or_draft_row():
    """The live GET filters status=eq.active server-side -- a
    draft/deprecated row for the same prompt_name is never returned to
    this function even if other versions exist. Simulated here exactly
    like get_active_prompt's own precedent: an empty result stands in
    for "filtered out by PostgREST," not "table is empty." """
    route = respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(PromptConfigError):
            await resolve_active_prompt(client, _headers(), prompt_name="weather_agent")
    assert route.calls.last.request.url.params["status"] == "eq.active"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_active_prompt_raises_config_read_error_on_transport_failure():
    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ConfigReadError):
            await resolve_active_prompt(client, _headers(), prompt_name="weather_agent")
