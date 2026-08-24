"""Milestone 4.8: end-to-end prompt-provenance tests. Proves that
`recommendation_agent_outputs.prompt_name`/`.prompt_version` -- not
`recommendations.prompt_version` -- are the canonical per-agent Time
Machine record of which exact prompt_registry row produced each output,
and that this is resolved at the orchestration boundary, never guessed
or re-derived. FakeModelAdapter is the only model adapter used anywhere
in this file -- no live OpenAI/Anthropic calls are possible; every
Supabase call is respx-mocked, not a real network request."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.agents.base_agent import ContextDataAgent
from app.agents.context import AgentContext
from app.features.travel import TravelFeatures
from app.models.fake_adapter import FakeModelAdapter, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.orchestration.cycle import run_recommendation_cycle
from app.persistence.recommendations import persist_agent_output

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


class _StubAgent(ContextDataAgent):
    def __init__(self, name: str, task_type: str):
        self.agent_name = name
        self.task_type = task_type

    def build_evidence(self, context: AgentContext) -> dict:
        return {"stub": True}


def _empty_travel() -> TravelFeatures:
    return TravelFeatures(None, None, None, None)


def _context() -> AgentContext:
    return AgentContext(
        game_id="g1", correlation_id="corr-1", injuries=None, weather=None, rest=None, stadium=None,
        travel=_empty_travel(), odds_history=None, line_movement=None,
    )


def _valid_output_json(agent_name: str) -> str:
    return json.dumps(
        {
            "agent_name": agent_name, "finding": "finding", "supporting_evidence": [],
            "evidence_classification": "data_backed", "directional_lean": "none", "confidence": 0.5,
            "would_change_mind_if": "x",
        }
    )


def _routing_rule(task_type: str) -> dict:
    return {"task_type": task_type, "primary_model": "claude-sonnet-5", "fallback_model": None}


def _mock_two_distinct_prompts():
    """agent_a resolves to prompt_registry v2, agent_b to v5 --
    independently versioned, exactly as Mac's example describes
    (injury_intelligence_agent -> v3, weather_agent -> v2, etc. may
    legitimately coexist in the same cycle)."""

    def _respond(request: httpx.Request) -> httpx.Response:
        raw = request.url.params.get("prompt_name", "")
        name = raw[len("eq.") :] if raw.startswith("eq.") else raw
        version = {"agent_a": 2, "agent_b": 5}[name]
        return httpx.Response(200, json=[{"prompt_name": name, "version": version, "prompt_text": f"prompt for {name} v{version}"}])

    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(side_effect=_respond)


@pytest.mark.asyncio
@respx.mock
async def test_two_agents_in_one_cycle_persist_independently_different_prompt_versions():
    _mock_two_distinct_prompts()
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games", params={"status": "eq.final"}).mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200,
            json=[{
                "id": "g1", "home_team": "BUF", "away_team": "KC", "scheduled_start": "2026-09-21T17:00:00+00:00",
                "venue_lat": None, "venue_long": None, "stadium": None, "venue_type": None,
            }],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))

    agents = [_StubAgent("agent_a", "task_a"), _StubAgent("agent_b", "task_b")]
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedSuccess(raw_text=_valid_output_json("agent_a")), ScriptedSuccess(raw_text=_valid_output_json("agent_b"))],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        recommendation_id, fan_out_result = await run_recommendation_cycle(
            client, _headers(), game_id="g1", correlation_id="corr-1", prompt_version="legacy-v1", agent_version="v1",
            agents=agents, routing_rules={"task_a": _routing_rule("task_a"), "task_b": _routing_rule("task_b")},
            adapter_registry=registry, model_providers={"claude-sonnet-5": "anthropic"},
        )

    assert fan_out_result.status == "full"
    assert output_route.call_count == 2
    sent_by_agent = {}
    for call in output_route.calls:
        body = json.loads(call.request.content)
        agent_id_marker = body["raw_output"]["agent_name"]  # agent_a or agent_b, from the scripted output
        sent_by_agent[agent_id_marker] = body

    # Each output persists its OWN exact prompt_name/version -- not a
    # shared/global value, not recommendations.prompt_version ("legacy-v1"):
    assert sent_by_agent["agent_a"]["prompt_name"] == "agent_a"
    assert sent_by_agent["agent_a"]["prompt_version"] == 2
    assert sent_by_agent["agent_b"]["prompt_name"] == "agent_b"
    assert sent_by_agent["agent_b"]["prompt_version"] == 5
    # Both differ from recommendations.prompt_version -- proves the two
    # concepts are genuinely independent, not silently coupled:
    assert sent_by_agent["agent_a"]["prompt_version"] != "legacy-v1"


@pytest.mark.asyncio
@respx.mock
async def test_prompt_provenance_corresponds_to_the_exact_prompt_text_actually_sent():
    """Not just that SOME version number is persisted -- that the
    persisted prompt_name/version is the exact row whose prompt_text was
    used to build the system message sent to the model."""
    captured_system_prompts: list[str] = []

    class _CapturingAdapter:
        async def complete(self, request):
            from app.models.structured_output import parse_structured_output
            from app.models.types import ModelResponse, UsageMetadata

            captured_system_prompts.append(request.messages[0].content)
            text = _valid_output_json(request.agent_name)
            return ModelResponse(
                raw_text=text, usage=UsageMetadata(provider="anthropic", model=request.model),
                parsed=parse_structured_output(text, request.response_model),
            )

    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(
        return_value=httpx.Response(200, json=[{"prompt_name": "agent_a", "version": 7, "prompt_text": "THE EXACT RESOLVED PROMPT TEXT"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games", params={"status": "eq.final"}).mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200,
            json=[{
                "id": "g1", "home_team": "BUF", "away_team": "KC", "scheduled_start": "2026-09-21T17:00:00+00:00",
                "venue_lat": None, "venue_long": None, "stadium": None, "venue_type": None,
            }],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))

    registry = AdapterRegistry(adapters={"anthropic": _CapturingAdapter()})
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await run_recommendation_cycle(
            client, _headers(), game_id="g1", correlation_id="corr-1", prompt_version="legacy-v1", agent_version="v1",
            agents=[_StubAgent("agent_a", "task_a")], routing_rules={"task_a": _routing_rule("task_a")},
            adapter_registry=registry, model_providers={"claude-sonnet-5": "anthropic"},
        )

    assert captured_system_prompts == ["THE EXACT RESOLVED PROMPT TEXT"]
    sent = json.loads(output_route.calls.last.request.content)
    assert sent["prompt_name"] == "agent_a"
    assert sent["prompt_version"] == 7  # the same row whose text was actually sent to the model


@pytest.mark.asyncio
async def test_persist_agent_output_never_re_reads_prompt_registry_frozen_at_call_time():
    """Changing prompt_registry's active version LATER cannot alter an
    already-persisted row -- persist_agent_output takes prompt_name/
    version as plain frozen values (mirroring weight_applied's Decision
    C precedent) and performs no prompt_registry read of its own."""
    from app.agents.contract import AgentOutput

    with respx.mock:
        respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
        output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
        prompt_registry_route = respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(return_value=httpx.Response(200, json=[]))

        output = AgentOutput.model_validate(json.loads(_valid_output_json("agent_a")))
        async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
            await persist_agent_output(
                client, _headers(), recommendation_id="r1", agent_name="agent_a", output=output,
                prompt_name="agent_a", prompt_version=9,
            )

        assert prompt_registry_route.call_count == 0  # no live re-read at persist time
        sent = json.loads(output_route.calls.last.request.content)
        assert sent["prompt_name"] == "agent_a"
        assert sent["prompt_version"] == 9  # exactly the frozen value the caller supplied


@pytest.mark.asyncio
async def test_persist_agent_output_without_prompt_provenance_persists_null_legacy_shape():
    """A caller that doesn't supply prompt_name/prompt_version (e.g. a
    pre-Milestone-4.8 code path, or a legacy-shaped row being replayed)
    still persists successfully with NULL provenance -- backward
    compatible, nothing errors."""
    from app.agents.contract import AgentOutput

    with respx.mock:
        respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
        output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))

        output = AgentOutput.model_validate(json.loads(_valid_output_json("agent_a")))
        async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
            await persist_agent_output(client, _headers(), recommendation_id="r1", agent_name="agent_a", output=output)

        sent = json.loads(output_route.calls.last.request.content)
        assert sent["prompt_name"] is None
        assert sent["prompt_version"] is None


@pytest.mark.asyncio
@respx.mock
async def test_deterministic_active_version_selection_ignores_inactive_rows():
    """The live GET filters status=eq.active server-side -- simulated
    here by a route that only ever returns the single active row for a
    prompt_name that (in a real database) also has inactive/deprecated
    versions on record. Proves resolve_active_prompt's caller-visible
    contract: exactly the active row, deterministically, never a
    deprecated/draft one."""
    from app.persistence.model_config import resolve_active_prompt

    route = respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(
        return_value=httpx.Response(200, json=[{"prompt_name": "weather_agent", "version": 4, "prompt_text": "current active text"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_active_prompt(client, _headers(), prompt_name="weather_agent")

    assert result.version == 4
    assert result.prompt_text == "current active text"
    assert route.calls.last.request.url.params["status"] == "eq.active"
