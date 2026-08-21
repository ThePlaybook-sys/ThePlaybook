"""Tests for app.models.fake_adapter (Milestone 4.3, requirement 7)."""
from __future__ import annotations

import pytest

from app.agents.contract import AgentOutput
from app.models.base import ModelAdapter
from app.models.errors import ModelError, ModelRateLimitError, ModelTimeoutError
from app.models.fake_adapter import FakeAdapterExhausted, FakeModelAdapter, ScriptedFailure, ScriptedSuccess
from app.models.types import ModelMessage, ModelRequest

_VALID_JSON = """{
  "agent_name": "weather_agent",
  "finding": "Clear conditions.",
  "supporting_evidence": ["weather: clear"],
  "evidence_classification": "data_backed",
  "directional_lean": "none",
  "confidence": 0.5,
  "would_change_mind_if": "forecast changes"
}"""


def _request(**overrides) -> ModelRequest:
    base = dict(
        model="fake-model-1",
        messages=[ModelMessage(role="user", content="hello")],
        task_type="test_task",
        agent_name="weather_agent",
        correlation_id="corr-1",
    )
    base.update(overrides)
    return ModelRequest(**base)


def test_satisfies_shared_model_adapter_interface():
    adapter = FakeModelAdapter(provider="fake", script=[])
    assert isinstance(adapter, ModelAdapter)


@pytest.mark.asyncio
async def test_scripted_success_returns_response_with_usage():
    adapter = FakeModelAdapter(
        provider="fake", script=[ScriptedSuccess(raw_text="hello back", input_tokens=10, output_tokens=5)]
    )
    response = await adapter.complete(_request())
    assert response.raw_text == "hello back"
    assert response.usage.provider == "fake"
    assert response.usage.model == "fake-model-1"
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 5
    assert response.usage.total_tokens == 15
    assert response.usage.correlation_id == "corr-1"
    assert response.usage.task_type == "test_task"
    assert response.usage.agent_name == "weather_agent"


@pytest.mark.asyncio
async def test_scripted_success_without_token_counts_leaves_them_none_never_zero():
    """Requirement 12: fake mode must not fabricate token/cost metadata
    unless a test explicitly scripts it."""
    adapter = FakeModelAdapter(provider="fake", script=[ScriptedSuccess(raw_text="hi")])
    response = await adapter.complete(_request())
    assert response.usage.input_tokens is None
    assert response.usage.output_tokens is None
    assert response.usage.total_tokens is None
    assert response.usage.estimated_cost_usd is None


@pytest.mark.asyncio
async def test_scripted_success_with_response_model_parses_and_validates():
    adapter = FakeModelAdapter(provider="fake", script=[ScriptedSuccess(raw_text=_VALID_JSON)])
    response = await adapter.complete(_request(response_model=AgentOutput))
    assert isinstance(response.parsed, AgentOutput)
    assert response.parsed.agent_name == "weather_agent"


@pytest.mark.asyncio
async def test_scripted_malformed_success_raises_via_shared_validation():
    """Malformed output is just a ScriptedSuccess whose raw_text doesn't
    validate -- no separate "malformed" scripted type exists."""
    adapter = FakeModelAdapter(provider="fake", script=[ScriptedSuccess(raw_text="not json at all")])
    with pytest.raises(ModelError):
        await adapter.complete(_request(response_model=AgentOutput))


@pytest.mark.asyncio
async def test_scripted_failure_raises_the_exact_scripted_error():
    err = ModelRateLimitError("rate limited", retry_after_seconds=2.5)
    adapter = FakeModelAdapter(provider="fake", script=[ScriptedFailure(error=err)])
    with pytest.raises(ModelRateLimitError) as excinfo:
        await adapter.complete(_request())
    assert excinfo.value is err
    assert excinfo.value.retry_after_seconds == 2.5


@pytest.mark.asyncio
async def test_scripted_timeout_raises_immediately_no_real_wait():
    import time

    adapter = FakeModelAdapter(provider="fake", script=[ScriptedFailure(error=ModelTimeoutError("timed out"))])
    started = time.monotonic()
    with pytest.raises(ModelTimeoutError):
        await adapter.complete(_request(timeout_seconds=30.0))
    assert time.monotonic() - started < 1.0  # never actually waits for timeout_seconds


@pytest.mark.asyncio
async def test_script_exhausted_raises_clearly_not_a_default_response():
    adapter = FakeModelAdapter(provider="fake", script=[ScriptedSuccess(raw_text="only one")])
    await adapter.complete(_request())
    with pytest.raises(FakeAdapterExhausted):
        await adapter.complete(_request())


@pytest.mark.asyncio
async def test_call_count_tracks_every_attempt():
    adapter = FakeModelAdapter(
        provider="fake",
        script=[ScriptedFailure(error=ModelTimeoutError("t1")), ScriptedSuccess(raw_text="ok")],
    )
    with pytest.raises(ModelTimeoutError):
        await adapter.complete(_request())
    await adapter.complete(_request())
    assert adapter.call_count == 2
