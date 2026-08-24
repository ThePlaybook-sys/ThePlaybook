"""Tests for app.orchestration.fanout (Milestone 4.4, Decision 8; client/
headers + prompt resolution added Milestone 4.8)."""
from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
import respx

from app.agents.base_agent import ContextDataAgent
from app.agents.context import AgentContext
from app.features.travel import TravelFeatures
from app.models.base import ModelAdapter
from app.models.errors import ModelTimeoutError
from app.models.fake_adapter import FakeModelAdapter, ScriptedFailure, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.models.types import ModelResponse, UsageMetadata
from app.orchestration.fanout import run_agent, run_fan_out
from tests.conftest import mock_prompt_registry_route

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
        game_id="g1",
        correlation_id="corr-1",
        injuries=None,
        weather=None,
        rest=None,
        stadium=None,
        travel=_empty_travel(),
        odds_history=None,
        line_movement=None,
    )


def _valid_output_json(agent_name: str) -> str:
    return json.dumps(
        {
            "agent_name": agent_name,
            "finding": "finding",
            "supporting_evidence": [],
            "evidence_classification": "data_backed",
            "directional_lean": "none",
            "confidence": 0.5,
            "would_change_mind_if": "x",
        }
    )


def _routing_rule(task_type: str, model: str = "claude-sonnet-5") -> dict:
    return {"task_type": task_type, "primary_model": model, "fallback_model": None}


# --- run_agent: single-agent isolation ---


@pytest.mark.asyncio
@respx.mock
async def test_run_agent_success():
    mock_prompt_registry_route(SUPABASE_URL)
    agent = _StubAgent("agent_a", "task_a")
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_valid_output_json("agent_a"))])
    registry = AdapterRegistry(adapters={"anthropic": adapter})
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_agent(
            agent,
            _context(),
            client=client,
            headers=_headers(),
            routing_rule=_routing_rule("task_a"),
            model_providers={"claude-sonnet-5": "anthropic"},
            adapter_registry=registry,
            retry_engine=__import__("app.models.retry_policy", fromlist=["RetryEngine"]).RetryEngine(),
        )
    assert result.status == "success"
    assert result.output.agent_name == "agent_a"
    assert result.error is None
    assert result.prompt_name == "agent_a"
    assert result.prompt_version == 1


@pytest.mark.asyncio
@respx.mock
async def test_run_agent_never_raises_on_total_failure_reports_failed_instead():
    from app.models.retry_policy import RetryEngine

    mock_prompt_registry_route(SUPABASE_URL)
    agent = _StubAgent("agent_a", "task_a")
    adapter = FakeModelAdapter(
        provider="anthropic", script=[ScriptedFailure(error=ModelTimeoutError("t1")), ScriptedFailure(error=ModelTimeoutError("t2"))]
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_agent(
            agent,
            _context(),
            client=client,
            headers=_headers(),
            routing_rule=_routing_rule("task_a"),
            model_providers={"claude-sonnet-5": "anthropic"},
            adapter_registry=registry,
            retry_engine=RetryEngine(),
        )
    assert result.status == "failed"
    assert result.output is None
    assert result.error is not None


@pytest.mark.asyncio
@respx.mock
async def test_run_agent_missing_adapter_registration_reported_as_failed_not_raised():
    from app.models.retry_policy import RetryEngine

    mock_prompt_registry_route(SUPABASE_URL)
    agent = _StubAgent("agent_a", "task_a")
    registry = AdapterRegistry(adapters={})  # nothing registered
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_agent(
            agent,
            _context(),
            client=client,
            headers=_headers(),
            routing_rule=_routing_rule("task_a"),
            model_providers={"claude-sonnet-5": "anthropic"},
            adapter_registry=registry,
            retry_engine=RetryEngine(),
        )
    assert result.status == "failed"


@pytest.mark.asyncio
@respx.mock
async def test_run_agent_missing_prompt_configuration_reported_as_failed_not_raised():
    """Milestone 4.8: no active prompt_registry row for this agent_name
    -- resolve_active_prompt raises PromptConfigError, caught by the same
    blanket isolation every other per-agent failure uses. Never a silent
    hardcoded-text fallback."""
    from app.models.retry_policy import RetryEngine

    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(return_value=httpx.Response(200, json=[]))
    agent = _StubAgent("agent_with_no_prompt", "task_a")
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_valid_output_json("agent_with_no_prompt"))])
    registry = AdapterRegistry(adapters={"anthropic": adapter})
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_agent(
            agent,
            _context(),
            client=client,
            headers=_headers(),
            routing_rule=_routing_rule("task_a"),
            model_providers={"claude-sonnet-5": "anthropic"},
            adapter_registry=registry,
            retry_engine=RetryEngine(),
        )
    assert result.status == "failed"
    assert "no active prompt_registry row" in result.error
    assert adapter.call_count == 0  # never reached the model call at all


# --- run_fan_out: FULL/PARTIAL/FAILED ---


@pytest.mark.asyncio
@respx.mock
async def test_fan_out_full_when_all_agents_succeed():
    mock_prompt_registry_route(SUPABASE_URL)
    agents = [_StubAgent("agent_a", "task_a"), _StubAgent("agent_b", "task_b")]
    adapters = {
        "anthropic": FakeModelAdapter(
            provider="anthropic",
            script=[ScriptedSuccess(raw_text=_valid_output_json("agent_a")), ScriptedSuccess(raw_text=_valid_output_json("agent_b"))],
        )
    }
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_fan_out(
            agents,
            _context(),
            client=client,
            headers=_headers(),
            routing_rules={"task_a": _routing_rule("task_a"), "task_b": _routing_rule("task_b")},
            model_providers={"claude-sonnet-5": "anthropic"},
            adapter_registry=AdapterRegistry(adapters=adapters),
        )
    assert result.status == "full"
    assert len(result.successes) == 2
    assert len(result.failures) == 0


@pytest.mark.asyncio
@respx.mock
async def test_fan_out_partial_when_one_agent_fails_and_one_succeeds():
    from app.models.structured_output import parse_structured_output
    from app.agents.contract import AgentOutput

    mock_prompt_registry_route(SUPABASE_URL)

    class _MixedAdapterReal(ModelAdapter):
        """One shared adapter whose behavior depends on which agent's
        request it receives -- proves the failure is isolated to exactly
        the failing agent, not the whole fan-out."""

        async def complete(self, request):
            if request.agent_name == "agent_fails":
                raise ModelTimeoutError("always times out")
            parsed = parse_structured_output(_valid_output_json("agent_succeeds"), AgentOutput)
            return ModelResponse(
                raw_text=_valid_output_json("agent_succeeds"),
                usage=UsageMetadata(provider="anthropic", model=request.model),
                parsed=parsed,
            )

    agents = [_StubAgent("agent_fails", "task_fail"), _StubAgent("agent_succeeds", "task_ok")]
    registry = AdapterRegistry(adapters={"anthropic": _MixedAdapterReal()})
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_fan_out(
            agents,
            _context(),
            client=client,
            headers=_headers(),
            routing_rules={"task_fail": _routing_rule("task_fail"), "task_ok": _routing_rule("task_ok")},
            model_providers={"claude-sonnet-5": "anthropic"},
            adapter_registry=registry,
        )
    assert result.status == "partial"
    assert len(result.successes) == 1
    assert len(result.failures) == 1
    assert result.failures[0].agent_name == "agent_fails"
    assert result.successes[0].agent_name == "agent_succeeds"
    # The failed agent is absent, never a fabricated zero-confidence entry:
    assert result.failures[0].output is None


@pytest.mark.asyncio
@respx.mock
async def test_fan_out_failed_when_every_agent_fails():
    mock_prompt_registry_route(SUPABASE_URL)
    agents = [_StubAgent("agent_a", "task_a"), _StubAgent("agent_b", "task_b")]
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedFailure(error=ModelTimeoutError("t1")),
            ScriptedFailure(error=ModelTimeoutError("t2")),
            ScriptedFailure(error=ModelTimeoutError("t3")),
            ScriptedFailure(error=ModelTimeoutError("t4")),
        ],
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_fan_out(
            agents,
            _context(),
            client=client,
            headers=_headers(),
            routing_rules={"task_a": _routing_rule("task_a"), "task_b": _routing_rule("task_b")},
            model_providers={"claude-sonnet-5": "anthropic"},
            adapter_registry=AdapterRegistry(adapters={"anthropic": adapter}),
        )
    assert result.status == "failed"
    assert len(result.successes) == 0
    assert len(result.failures) == 2


@pytest.mark.asyncio
@respx.mock
async def test_fan_out_is_actually_concurrent_not_sequential():
    """Four agents, each with a real 0.05s delay via a test-only slow
    adapter -- if execution were sequential, total elapsed would be
    ~0.20s; concurrent execution keeps it close to the single slowest
    agent's own delay."""
    mock_prompt_registry_route(SUPABASE_URL)

    class _SlowAdapter(ModelAdapter):
        async def complete(self, request):
            await asyncio.sleep(0.05)
            from app.agents.contract import AgentOutput
            from app.models.structured_output import parse_structured_output

            text = _valid_output_json(request.agent_name)
            return ModelResponse(
                raw_text=text,
                usage=UsageMetadata(provider="anthropic", model=request.model),
                parsed=parse_structured_output(text, AgentOutput),
            )

    agents = [_StubAgent(f"agent_{i}", f"task_{i}") for i in range(4)]
    routing_rules = {f"task_{i}": _routing_rule(f"task_{i}") for i in range(4)}
    registry = AdapterRegistry(adapters={"anthropic": _SlowAdapter()})

    started = time.monotonic()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_fan_out(
            agents,
            _context(),
            client=client,
            headers=_headers(),
            routing_rules=routing_rules,
            model_providers={"claude-sonnet-5": "anthropic"},
            adapter_registry=registry,
        )
    elapsed = time.monotonic() - started

    assert result.status == "full"
    assert elapsed < 0.15  # well under 4 x 0.05s sequential; concurrent stays near ~0.05s
