"""Deterministic fake model adapter (Milestone 4.3, requirement 7) --
what every orchestration/routing/retry test in this milestone runs
against instead of a real OpenAI/Anthropic call. No network access, no
API key, no timing dependency (a scripted `ModelTimeoutError` raises
immediately -- it never actually sleeps for `timeout_seconds`).

Scripted per-call via a queue: each `.complete()` call pops exactly one
`ScriptedSuccess` or `ScriptedFailure` from the queue given at
construction time, in order. An empty queue raises `FakeAdapterExhausted`
-- a test that runs the adapter more times than it scripted is a test
bug, not a case to silently paper over with a default response.

Structured-output validation (requirement 6) is NOT special-cased here:
a `ScriptedSuccess` goes through the exact same
`app.models.structured_output.parse_structured_output` call a real
adapter would, so "malformed output" is simply a `ScriptedSuccess` whose
`raw_text` doesn't validate against `ModelRequest.response_model` --
there is no separate "ScriptedMalformed" type, because malformed output
is a content-validation failure on an otherwise-successful call
(`errors.ModelMalformedOutputError`'s own docstring), not a distinct
provider-level failure mode.

Requirement 12 -- "fake mode must not fabricate token/cost metadata
unless a test explicitly scripts it": `ScriptedSuccess.input_tokens`/
`.output_tokens`/`.latency_ms` all default to `None`; a test that doesn't
pass them gets `None` fields on the resulting `UsageMetadata`, never a
fabricated number.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.base import ModelAdapter
from app.models.errors import ModelError
from app.models.structured_output import parse_structured_output
from app.models.types import ModelRequest, ModelResponse, UsageMetadata


class FakeAdapterExhausted(Exception):
    """Raised when `.complete()` is called more times than the
    constructor's script provides for -- a test-authoring error, not a
    real-world condition any adapter should model."""


@dataclass(frozen=True)
class ScriptedSuccess:
    """One scripted successful provider response. `raw_text` is
    validated against `ModelRequest.response_model` exactly like a real
    adapter would -- pass text that doesn't validate to script a
    "malformed output" case."""

    raw_text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class ScriptedFailure:
    """One scripted provider failure. `error` is an already-constructed
    instance from `app.models.errors` (e.g.
    `ModelRateLimitError("rate limited", retry_after_seconds=2.0)`) --
    raised verbatim, so a test controls the exact normalized error shape
    the retry engine will see."""

    error: ModelError


class FakeModelAdapter(ModelAdapter):
    def __init__(self, *, provider: str, script: list[ScriptedSuccess | ScriptedFailure]):
        self._provider = provider
        self._script = list(script)
        self.call_count = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.call_count += 1
        if not self._script:
            raise FakeAdapterExhausted(
                f"FakeModelAdapter's script was exhausted on call {self.call_count} "
                f"(model={request.model!r}, task_type={request.task_type!r})"
            )
        step = self._script.pop(0)
        if isinstance(step, ScriptedFailure):
            raise step.error

        parsed = None
        if request.response_model is not None:
            parsed = parse_structured_output(step.raw_text, request.response_model)

        usage = UsageMetadata(
            provider=self._provider,
            model=request.model,
            input_tokens=step.input_tokens,
            output_tokens=step.output_tokens,
            total_tokens=(
                step.input_tokens + step.output_tokens
                if step.input_tokens is not None and step.output_tokens is not None
                else None
            ),
            latency_ms=step.latency_ms,
            correlation_id=request.correlation_id,
            task_type=request.task_type,
            agent_name=request.agent_name,
        )
        return ModelResponse(raw_text=step.raw_text, usage=usage, parsed=parsed, finish_reason=step.finish_reason)
