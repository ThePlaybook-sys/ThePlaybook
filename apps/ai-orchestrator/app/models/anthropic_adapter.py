"""Anthropic adapter (Milestone 4.3) -- built directly against
Anthropic's public Messages REST API via `httpx`, same convention as
`app.models.openai_adapter` and every other provider adapter in this
repository. See `openai_adapter.py`'s module docstring for the full
dependency-policy reasoning (official SDK evaluated and not used, not
silently skipped).

**CONFIRMED FROM PROVIDER DOCUMENTATION (Anthropic's public API
reference), never live-verified in this project (zero live calls made or
authorized):** request shape (`model`/`max_tokens`/`system`/`messages`,
`system` passed as a distinct top-level field rather than a message with
`role="system"` -- the one real shape difference from OpenAI's Chat
Completions API), response shape (`content[0].text`, `stop_reason`,
`usage.input_tokens`/`.output_tokens`), error body shape
(`{"type": "error", "error": {"type", "message"}}`), and standard HTTP
status-code semantics (401 auth, 429 rate limit with an optional
`Retry-After` header, 5xx server error including Anthropic's own 529
"overloaded" -- treated identically to any other 5xx, since it's the
same "provider itself is failing" category -- and other 4xx client
error).
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

_PROVIDER = "anthropic"
_MESSAGES_PATH = "/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 4096


class AnthropicModelAdapter(ModelAdapter):
    """`client` is an injectable `httpx.AsyncClient` (constructed with
    `base_url="https://api.anthropic.com"` in real use) -- identical
    transport-injection convention to every other adapter in this
    codebase, fully respx-mockable."""

    def __init__(self, *, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def complete(self, request: ModelRequest) -> ModelResponse:
        system_prompt = "\n\n".join(m.content for m in request.messages if m.role == "system") or None
        user_messages = [
            {"role": m.role, "content": m.content} for m in request.messages if m.role != "system"
        ]

        payload: dict = {
            "model": request.model,
            "max_tokens": request.max_output_tokens or _DEFAULT_MAX_TOKENS,
            "messages": user_messages,
        }
        if system_prompt is not None:
            payload["system"] = system_prompt
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        headers = {"x-api-key": self._api_key, "anthropic-version": _ANTHROPIC_VERSION}
        started = time.monotonic()
        try:
            response = await self._client.post(
                _MESSAGES_PATH, json=payload, headers=headers, timeout=request.timeout_seconds
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"Anthropic request timed out after {request.timeout_seconds}s") from exc
        latency_ms = (time.monotonic() - started) * 1000

        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise ModelRateLimitError(
                f"Anthropic rate limit: {_error_message(response)}", retry_after_seconds=retry_after
            )
        if response.status_code in (401, 403):
            raise ModelAuthError(f"Anthropic authentication failed: {_error_message(response)}")
        if response.status_code >= 500:
            raise ModelServerError(f"Anthropic server error ({response.status_code}): {_error_message(response)}")
        if response.status_code >= 400:
            raise ModelBadRequestError(
                f"Anthropic request rejected ({response.status_code}): {_error_message(response)}"
            )

        body = response.json()
        raw_text = "".join(block["text"] for block in body["content"] if block.get("type") == "text")
        finish_reason = body.get("stop_reason")
        usage_body = body.get("usage") or {}

        parsed = None
        if request.response_model is not None:
            parsed = parse_structured_output(raw_text, request.response_model)

        input_tokens = usage_body.get("input_tokens")
        output_tokens = usage_body.get("output_tokens")
        usage = UsageMetadata(
            provider=_PROVIDER,
            model=request.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None),
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
