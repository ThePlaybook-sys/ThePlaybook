"""Provider-neutral model request/response/usage shapes (Milestone 4.3,
requirement 2).

Plain dataclasses, deliberately not Pydantic models -- unlike
`AgentOutput`/`MetaAgentOutput` (Milestone 4.2), nothing here is an
external-facing, validated contract; these are internal orchestration
plumbing passed between the router, an adapter, and the retry engine, all
within this one process. `ModelRequest.response_model` holds a Pydantic
*class* (e.g. `AgentOutput`) as a field value, which a Pydantic model
can't cleanly type without `arbitrary_types_allowed` friction for zero
real benefit here.

This is the one shape every adapter (`FakeModelAdapter`,
`OpenAIModelAdapter`, `AnthropicModelAdapter`) speaks — "Agent -> Model
Router -> provider-neutral model interface -> [OpenAI adapter / Anthropic
adapter / FakeModelAdapter]" (the approved Milestone 4.3 architecture):
nothing past the adapter boundary ever sees a raw OpenAI/Anthropic SDK or
REST response object.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class ModelMessage:
    """One turn of the system/user prompt input. `role` is deliberately a
    plain str, not an enum -- both providers' real APIs use "system"/
    "user"/"assistant" directly, and constraining it further isn't this
    milestone's job."""

    role: str
    content: str


@dataclass(frozen=True)
class ModelRequest:
    """Provider-neutral request shape -- requirement 2's full field list.

    `response_model`: when set, the adapter must parse its response as
    JSON and validate it against this Pydantic model before returning a
    successful `ModelResponse` -- a failure raises
    `ModelMalformedOutputError` (errors.py), never a guessed/filled-in
    default (requirement 6). `None` means the caller doesn't expect
    structured output at all (e.g. a future plain-prose use, if one ever
    exists) -- Milestone 4.4+'s real agents will always set this to
    `AgentOutput` or `MetaAgentOutput` (Milestone 4.2), but this module
    has no hardcoded dependency on either -- any Pydantic model works.

    `task_type`/`agent_name`/`correlation_id` are carried through
    unchanged into the resulting `UsageMetadata` -- this is what makes a
    usage record traceable back to which agent/task/recommendation it
    belongs to (Volume 2 Section 9's correlation-ID discipline, applied
    to model calls specifically).
    """

    model: str
    messages: list[ModelMessage]
    task_type: str
    agent_name: str
    correlation_id: str
    response_model: type[BaseModel] | None = None
    timeout_seconds: float = 30.0
    max_output_tokens: int | None = None
    temperature: float | None = None


@dataclass
class UsageMetadata:
    """Normalized usage/cost metadata -- requirement 11's full field
    list. Every token/cost field is `int | None` / `float | None`,
    defaulting to `None`, never `0` -- requirement 12's "fake mode must
    not fabricate token/cost metadata unless a test explicitly scripts
    it" applies equally to the real adapters: a provider response that
    doesn't report usage produces `None` fields here, never a fabricated
    zero (the same null-not-neutral discipline Milestone 4.1's DGI reads
    and Milestone 4.2's contract both already established).

    `attempt_count`/`used_fallback` are populated by the retry engine
    (`app.models.retry_policy`), not by an individual adapter call -- a
    single bare adapter `.complete()` call always returns
    `attempt_count=1, used_fallback=False`; only the engine that actually
    orchestrates retries/fallback knows the real totals.
    """

    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None
    attempt_count: int = 1
    used_fallback: bool = False
    estimated_cost_usd: float | None = None
    correlation_id: str | None = None
    task_type: str | None = None
    agent_name: str | None = None


@dataclass
class ModelResponse:
    """What an adapter (or the retry engine) returns on success.
    `parsed` holds the `response_model`-validated instance when
    `ModelRequest.response_model` was set; `raw_text` always holds the
    provider's raw text content, even when `parsed` is also present --
    never discarded, useful for logging/debugging without a second call."""

    raw_text: str
    usage: UsageMetadata
    parsed: BaseModel | None = None
    finish_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
