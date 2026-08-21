"""OpenAI adapter (Milestone 4.3) -- built directly against OpenAI's
public Chat Completions REST API via `httpx`, the same convention every
other provider adapter in this repository already uses (The Odds API,
SportsDataIO, WeatherAPI, NewsAPI -- Volume 2 Section 8's adapter
pattern), rather than the official `openai` Python SDK.

**Dependency-policy decision (Milestone 4.3, requirement 14), evaluated
and decided against, not silently skipped:** the official `openai`/
`anthropic` SDKs were installed and inspected during this milestone. At
the versions available in this environment (`openai==3.3.1`,
`anthropic==1.0.0`), both SDKs' `http_client` constructor parameter
expects their own vendored `httpx2.AsyncClient` transport, not a plain
`httpx.AsyncClient` -- injecting a mockable, respx-compatible transport
(this codebase's established testing convention for every existing
adapter) would require depending on that vendored transport type
directly, adding real version-coupling risk for zero functional benefit
at a milestone that makes zero live calls either way. OpenAI's Chat
Completions API and Anthropic's Messages API are both simple, stable,
well-documented JSON REST APIs -- raw `httpx` reproduces 100% of what's
needed (request building, response parsing, error normalization) with
zero new SDK dependency and full consistency with every other adapter in
this codebase. Neither package was added to `requirements.txt`. Flagged
explicitly for Mac's review, not treated as uncontroversially settled --
see the Milestone 4.3 completion report.

**CONFIRMED FROM PROVIDER DOCUMENTATION (OpenAI's public API reference,
stable since the Chat Completions API's release), never live-verified in
this project (zero live calls made or authorized):** request shape
(`model`/`messages`/`max_tokens`/`temperature`), response shape
(`choices[0].message.content`, `choices[0].finish_reason`,
`usage.prompt_tokens`/`.completion_tokens`/`.total_tokens`), error body
shape (`{"error": {"message", "type", "code"}}`), and standard HTTP
status-code semantics (401 auth, 429 rate limit with an optional
`Retry-After` header, 5xx server error, other 4xx client error).
"""
from __future__ import annotations

import time

import httpx

from app.models.base import ModelAdapter
from app.models.errors import (
    ModelAuthError,
    ModelBadRequestError,
    ModelRateLimitError,
    ModelServerError,
    ModelTimeoutError,
)
from app.models.structured_output import parse_structured_output
from app.models.types import ModelRequest, ModelResponse, UsageMetadata

_PROVIDER = "openai"
_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


class OpenAIModelAdapter(ModelAdapter):
    """`client` is an injectable `httpx.AsyncClient` (constructed with
    `base_url="https://api.openai.com"` in real use) -- exactly the same
    transport-injection convention `sports-intel-layer`'s provider
    adapters already use, which is what makes this fully respx-mockable
    in tests without ever needing a real API key or network access."""

    def __init__(self, *, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def complete(self, request: ModelRequest) -> ModelResponse:
        payload: dict = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        headers = {"Authorization": f"Bearer {self._api_key}"}
        started = time.monotonic()
        try:
            response = await self._client.post(
                _CHAT_COMPLETIONS_PATH, json=payload, headers=headers, timeout=request.timeout_seconds
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"OpenAI request timed out after {request.timeout_seconds}s") from exc
        latency_ms = (time.monotonic() - started) * 1000

        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise ModelRateLimitError(
                f"OpenAI rate limit: {_error_message(response)}", retry_after_seconds=retry_after
            )
        if response.status_code in (401, 403):
            raise ModelAuthError(f"OpenAI authentication failed: {_error_message(response)}")
        if response.status_code >= 500:
            raise ModelServerError(f"OpenAI server error ({response.status_code}): {_error_message(response)}")
        if response.status_code >= 400:
            raise ModelBadRequestError(f"OpenAI request rejected ({response.status_code}): {_error_message(response)}")

        body = response.json()
        choice = body["choices"][0]
        raw_text = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")
        usage_body = body.get("usage") or {}

        parsed = None
        if request.response_model is not None:
            parsed = parse_structured_output(raw_text, request.response_model)

        usage = UsageMetadata(
            provider=_PROVIDER,
            model=request.model,
            input_tokens=usage_body.get("prompt_tokens"),
            output_tokens=usage_body.get("completion_tokens"),
            total_tokens=usage_body.get("total_tokens"),
            latency_ms=latency_ms,
            correlation_id=request.correlation_id,
            task_type=request.task_type,
            agent_name=request.agent_name,
        )
        return ModelResponse(raw_text=raw_text, usage=usage, parsed=parsed, finish_reason=finish_reason)


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        return body.get("error", {}).get("message", response.text)
    except ValueError:
        return response.text


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
