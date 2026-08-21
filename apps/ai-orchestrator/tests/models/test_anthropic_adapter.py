"""Tests for app.models.anthropic_adapter (Milestone 4.3). All HTTP
mocked via respx -- zero real network access, no real API key."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.agents.contract import AgentOutput
from app.models.anthropic_adapter import AnthropicModelAdapter
from app.models.base import ModelAdapter
from app.models.errors import (
    ModelAuthError,
    ModelBadRequestError,
    ModelMalformedOutputError,
    ModelRateLimitError,
    ModelServerError,
    ModelTimeoutError,
)
from app.models.types import ModelMessage, ModelRequest

BASE_URL = "https://api.anthropic.com"

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
        model="claude-sonnet-5",
        messages=[ModelMessage(role="system", content="you are an agent"), ModelMessage(role="user", content="go")],
        task_type="test_task",
        agent_name="weather_agent",
        correlation_id="corr-1",
    )
    base.update(overrides)
    return ModelRequest(**base)


def _success_body(text: str) -> dict:
    return {
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 15, "output_tokens": 6},
    }


def test_satisfies_shared_model_adapter_interface():
    async_client = httpx.AsyncClient(base_url=BASE_URL)
    adapter = AnthropicModelAdapter(client=async_client, api_key="test-key")
    assert isinstance(adapter, ModelAdapter)


@pytest.mark.asyncio
@respx.mock
async def test_success_parses_content_and_usage_and_system_prompt_separated():
    route = respx.post(f"{BASE_URL}/v1/messages").mock(return_value=httpx.Response(200, json=_success_body("hello back")))
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = AnthropicModelAdapter(client=client, api_key="test-key")
        response = await adapter.complete(_request())
    assert response.raw_text == "hello back"
    assert response.finish_reason == "end_turn"
    assert response.usage.provider == "anthropic"
    assert response.usage.input_tokens == 15
    assert response.usage.output_tokens == 6
    assert response.usage.total_tokens == 21
    sent_body = route.calls.last.request.content
    import json

    parsed_body = json.loads(sent_body)
    assert parsed_body["system"] == "you are an agent"
    assert parsed_body["messages"] == [{"role": "user", "content": "go"}]


@pytest.mark.asyncio
@respx.mock
async def test_success_with_response_model_parses_structured_output():
    respx.post(f"{BASE_URL}/v1/messages").mock(return_value=httpx.Response(200, json=_success_body(_VALID_JSON)))
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = AnthropicModelAdapter(client=client, api_key="test-key")
        response = await adapter.complete(_request(response_model=AgentOutput))
    assert isinstance(response.parsed, AgentOutput)


@pytest.mark.asyncio
@respx.mock
async def test_malformed_content_raises_explicitly():
    respx.post(f"{BASE_URL}/v1/messages").mock(return_value=httpx.Response(200, json=_success_body("not json")))
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = AnthropicModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelMalformedOutputError):
            await adapter.complete(_request(response_model=AgentOutput))


@pytest.mark.asyncio
@respx.mock
async def test_429_normalized_with_retry_after():
    respx.post(f"{BASE_URL}/v1/messages").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "4"}, json={"type": "error", "error": {"message": "rate limited"}})
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = AnthropicModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelRateLimitError) as excinfo:
            await adapter.complete(_request())
    assert excinfo.value.retry_after_seconds == 4.0


@pytest.mark.asyncio
@respx.mock
async def test_401_normalized_to_auth_error():
    respx.post(f"{BASE_URL}/v1/messages").mock(
        return_value=httpx.Response(401, json={"type": "error", "error": {"message": "invalid key"}})
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = AnthropicModelAdapter(client=client, api_key="bad-key")
        with pytest.raises(ModelAuthError):
            await adapter.complete(_request())


@pytest.mark.asyncio
@respx.mock
async def test_529_overloaded_normalized_to_server_error():
    """Anthropic's own 529 'overloaded' status -- treated identically to
    any other 5xx, per this adapter's own docstring."""
    respx.post(f"{BASE_URL}/v1/messages").mock(
        return_value=httpx.Response(529, json={"type": "error", "error": {"message": "overloaded"}})
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = AnthropicModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelServerError):
            await adapter.complete(_request())


@pytest.mark.asyncio
@respx.mock
async def test_other_4xx_normalized_to_bad_request():
    respx.post(f"{BASE_URL}/v1/messages").mock(
        return_value=httpx.Response(400, json={"type": "error", "error": {"message": "bad request"}})
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = AnthropicModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelBadRequestError):
            await adapter.complete(_request())


@pytest.mark.asyncio
@respx.mock
async def test_timeout_normalized():
    respx.post(f"{BASE_URL}/v1/messages").mock(side_effect=httpx.TimeoutException("timed out"))
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = AnthropicModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelTimeoutError):
            await adapter.complete(_request())


@pytest.mark.asyncio
@respx.mock
async def test_caller_code_does_not_change_when_provider_changes():
    """Requirement: swapping OpenAI for Anthropic (or either for
    FakeModelAdapter) requires zero change to calling code -- both
    return the identical ModelResponse shape."""
    respx.post(f"{BASE_URL}/v1/messages").mock(return_value=httpx.Response(200, json=_success_body("hi")))
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter: ModelAdapter = AnthropicModelAdapter(client=client, api_key="test-key")
        response = await adapter.complete(_request())
    assert response.raw_text == "hi"
    assert response.usage.provider == "anthropic"
