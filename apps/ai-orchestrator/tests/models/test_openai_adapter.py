"""Tests for app.models.openai_adapter (Milestone 4.3). All HTTP mocked
via respx -- zero real network access, no real API key (a dummy string
is sufficient since no request ever leaves this process)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.agents.contract import AgentOutput
from app.models.base import ModelAdapter
from app.models.errors import (
    ModelAuthError,
    ModelBadRequestError,
    ModelMalformedOutputError,
    ModelRateLimitError,
    ModelServerError,
    ModelTimeoutError,
)
from app.models.openai_adapter import OpenAIModelAdapter
from app.models.types import ModelMessage, ModelRequest

BASE_URL = "https://api.openai.com"

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
        model="gpt-4o",
        messages=[ModelMessage(role="system", content="you are an agent"), ModelMessage(role="user", content="go")],
        task_type="test_task",
        agent_name="weather_agent",
        correlation_id="corr-1",
    )
    base.update(overrides)
    return ModelRequest(**base)


def _success_body(content: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
    }


def test_satisfies_shared_model_adapter_interface():
    client = httpx.AsyncClient(base_url=BASE_URL)
    adapter = OpenAIModelAdapter(client=client, api_key="test-key")
    assert isinstance(adapter, ModelAdapter)


@pytest.mark.asyncio
@respx.mock
async def test_success_parses_content_and_usage():
    respx.post(f"{BASE_URL}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_success_body("hello back"))
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = OpenAIModelAdapter(client=client, api_key="test-key")
        response = await adapter.complete(_request())
    assert response.raw_text == "hello back"
    assert response.finish_reason == "stop"
    assert response.usage.provider == "openai"
    assert response.usage.model == "gpt-4o"
    assert response.usage.input_tokens == 20
    assert response.usage.output_tokens == 8
    assert response.usage.total_tokens == 28
    assert response.usage.correlation_id == "corr-1"


@pytest.mark.asyncio
@respx.mock
async def test_success_with_response_model_parses_structured_output():
    respx.post(f"{BASE_URL}/v1/chat/completions").mock(return_value=httpx.Response(200, json=_success_body(_VALID_JSON)))
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = OpenAIModelAdapter(client=client, api_key="test-key")
        response = await adapter.complete(_request(response_model=AgentOutput))
    assert isinstance(response.parsed, AgentOutput)


@pytest.mark.asyncio
@respx.mock
async def test_malformed_content_raises_explicitly_never_guessed():
    respx.post(f"{BASE_URL}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_success_body("not valid json"))
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = OpenAIModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelMalformedOutputError):
            await adapter.complete(_request(response_model=AgentOutput))


@pytest.mark.asyncio
@respx.mock
async def test_429_normalized_with_retry_after():
    respx.post(f"{BASE_URL}/v1/chat/completions").mock(
        return_value=httpx.Response(
            429, headers={"Retry-After": "3"}, json={"error": {"message": "rate limited"}}
        )
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = OpenAIModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelRateLimitError) as excinfo:
            await adapter.complete(_request())
    assert excinfo.value.retry_after_seconds == 3.0


@pytest.mark.asyncio
@respx.mock
async def test_429_without_retry_after_header_leaves_it_none():
    respx.post(f"{BASE_URL}/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": {"message": "rate limited"}})
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = OpenAIModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelRateLimitError) as excinfo:
            await adapter.complete(_request())
    assert excinfo.value.retry_after_seconds is None


@pytest.mark.asyncio
@respx.mock
async def test_401_normalized_to_auth_error():
    respx.post(f"{BASE_URL}/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "invalid api key"}})
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = OpenAIModelAdapter(client=client, api_key="bad-key")
        with pytest.raises(ModelAuthError):
            await adapter.complete(_request())


@pytest.mark.asyncio
@respx.mock
async def test_500_normalized_to_server_error():
    respx.post(f"{BASE_URL}/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": {"message": "internal error"}})
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = OpenAIModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelServerError):
            await adapter.complete(_request())


@pytest.mark.asyncio
@respx.mock
async def test_other_4xx_normalized_to_bad_request():
    respx.post(f"{BASE_URL}/v1/chat/completions").mock(
        return_value=httpx.Response(400, json={"error": {"message": "invalid request"}})
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = OpenAIModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelBadRequestError):
            await adapter.complete(_request())


@pytest.mark.asyncio
@respx.mock
async def test_timeout_normalized():
    respx.post(f"{BASE_URL}/v1/chat/completions").mock(side_effect=httpx.TimeoutException("timed out"))
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = OpenAIModelAdapter(client=client, api_key="test-key")
        with pytest.raises(ModelTimeoutError):
            await adapter.complete(_request())


@pytest.mark.asyncio
@respx.mock
async def test_agent_never_receives_raw_response_object():
    """Requirement 4: agent code must never receive a raw OpenAI SDK/
    response object -- only ModelResponse/errors from app.models."""
    respx.post(f"{BASE_URL}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_success_body("hello"))
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        adapter = OpenAIModelAdapter(client=client, api_key="test-key")
        response = await adapter.complete(_request())
    assert type(response).__module__.startswith("app.models")
    assert not hasattr(response, "choices")  # not a raw OpenAI response shape
