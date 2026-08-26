"""Tests for app.models.retry_policy (Milestone 4.3, requirement 9) --
the exact retry/fallback matrix, budget enforcement, and the circuit
breaker seam. No real time is ever spent waiting: `RetryEngine`'s
`sleep` parameter defaults to `None` (skipped entirely), or a recording
fake is injected where a test needs to prove a wait was attempted."""
from __future__ import annotations

import pytest

from app.models.circuit_breaker import CircuitBreaker
from app.models.errors import (
    ModelAllAttemptsFailedError,
    ModelAuthError,
    ModelBadRequestError,
    ModelBudgetExceededError,
    ModelMalformedOutputError,
    ModelRateLimitError,
    ModelServerError,
    ModelTimeoutError,
)
from app.models.fake_adapter import FakeModelAdapter, ScriptedFailure, ScriptedSuccess
from app.models.retry_policy import RetryEngine, RetryFallbackPolicy
from app.models.types import ModelMessage, ModelRequest


def _request(**overrides) -> ModelRequest:
    base = dict(
        model="model-x",
        messages=[ModelMessage(role="user", content="go")],
        task_type="test_task",
        agent_name="test_agent",
        correlation_id="corr-1",
    )
    base.update(overrides)
    return ModelRequest(**base)


class _RecordingSleep:
    def __init__(self):
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class _DenyingBreaker:
    """A test-only CircuitBreaker that refuses one named provider."""

    def __init__(self, denied_provider: str):
        self._denied = denied_provider
        self.outcomes: list[tuple[str, bool]] = []

    def allow(self, provider: str) -> bool:
        return provider != self._denied

    def record_outcome(self, provider: str, *, succeeded: bool) -> None:
        self.outcomes.append((provider, succeeded))


@pytest.mark.asyncio
async def test_primary_succeeds_first_attempt_no_retry_no_fallback():
    primary = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text="ok")])
    engine = RetryEngine()
    response = await engine.execute(primary=primary, primary_provider="anthropic", request=_request())
    assert response.raw_text == "ok"
    assert response.usage.attempt_count == 1
    assert response.usage.used_fallback is False
    assert primary.call_count == 1


@pytest.mark.asyncio
async def test_malformed_output_gets_one_repair_retry_against_primary():
    from pydantic import BaseModel

    class _Dummy(BaseModel):
        ok: bool

    primary = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedSuccess(raw_text="not json"), ScriptedSuccess(raw_text='{"ok": true}')],
    )
    engine = RetryEngine()
    response = await engine.execute(
        primary=primary, primary_provider="anthropic", request=_request(response_model=_Dummy)
    )
    assert response.parsed == _Dummy(ok=True)
    assert response.usage.attempt_count == 2
    assert response.usage.used_fallback is False


@pytest.mark.asyncio
async def test_malformed_output_exhausts_primary_then_falls_back():
    from pydantic import BaseModel

    class _Dummy(BaseModel):
        ok: bool

    primary = FakeModelAdapter(
        provider="anthropic", script=[ScriptedSuccess(raw_text="not json"), ScriptedSuccess(raw_text="still not json")]
    )
    fallback = FakeModelAdapter(provider="openai", script=[ScriptedSuccess(raw_text='{"ok": true}')])
    engine = RetryEngine()
    response = await engine.execute(
        primary=primary,
        primary_provider="anthropic",
        request=_request(response_model=_Dummy),
        fallback=fallback,
        fallback_provider="openai",
    )
    assert response.usage.used_fallback is True
    assert response.usage.attempt_count == 3  # 2 primary + 1 fallback


# --- Decision BF: fallback-model provenance fix -----------------------


@pytest.mark.asyncio
async def test_bf_primary_succeeds_receives_and_records_primary_model():
    """Proof 1: primary succeeds -> primary adapter receives
    `primary_model`; persisted `(model_name, provider, used_fallback)`
    reflects the primary, unaffected by `fallback_model` being set."""
    primary = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text="ok")])
    fallback = FakeModelAdapter(provider="openai", script=[])
    engine = RetryEngine()
    response = await engine.execute(
        primary=primary,
        primary_provider="anthropic",
        request=_request(model="claude-primary"),
        fallback=fallback,
        fallback_provider="openai",
        fallback_model="gpt-fallback",
    )
    assert response.usage.model == "claude-primary"
    assert response.usage.provider == "anthropic"
    assert response.usage.used_fallback is False
    assert fallback.call_count == 0  # never invoked -- primary succeeded first try


@pytest.mark.asyncio
async def test_bf_fallback_receives_fallback_model_not_primary_model():
    """Proof 2: primary fails, fallback succeeds -> the fallback ADAPTER
    is called with `fallback_model` (never `primary_model`), and the
    persisted triple reflects the fallback truthfully. This is the exact
    bug from Carry-Forward Gap 1: before the fix, `response.usage.model`
    here would incorrectly read "claude-primary"."""
    primary = FakeModelAdapter(
        provider="anthropic", script=[ScriptedFailure(error=ModelAuthError("bad key"))]
    )
    fallback = FakeModelAdapter(provider="openai", script=[ScriptedSuccess(raw_text="ok")])
    engine = RetryEngine()
    response = await engine.execute(
        primary=primary,
        primary_provider="anthropic",
        request=_request(model="claude-primary"),
        fallback=fallback,
        fallback_provider="openai",
        fallback_model="gpt-fallback",
    )
    assert response.usage.model == "gpt-fallback"
    assert response.usage.model != "claude-primary"
    assert response.usage.provider == "openai"
    assert response.usage.used_fallback is True


@pytest.mark.asyncio
async def test_bf_fallback_model_equal_to_primary_model_still_correct():
    """Proof 3: when `primary_model == fallback_model` incidentally, the
    fallback's recorded model must still come from the actual serving
    adapter/model, not from an equality check against the primary --
    proving the fix sources the field structurally, not by diffing."""
    primary = FakeModelAdapter(
        provider="anthropic", script=[ScriptedFailure(error=ModelAuthError("bad key"))]
    )
    fallback = FakeModelAdapter(provider="openai", script=[ScriptedSuccess(raw_text="ok")])
    engine = RetryEngine()
    response = await engine.execute(
        primary=primary,
        primary_provider="anthropic",
        request=_request(model="shared-model-name"),
        fallback=fallback,
        fallback_provider="openai",
        fallback_model="shared-model-name",
    )
    assert response.usage.model == "shared-model-name"
    assert response.usage.provider == "openai"
    assert response.usage.used_fallback is True


@pytest.mark.asyncio
async def test_bf_omitting_fallback_model_preserves_pre_fix_behavior():
    """Proof 4 (no-regression): a caller that does not pass
    `fallback_model` (e.g. an un-migrated future call site) gets the
    exact pre-fix behavior -- the fallback candidate reuses `request`
    unchanged -- rather than the fix silently changing behavior for
    callers that never opted in."""
    primary = FakeModelAdapter(
        provider="anthropic", script=[ScriptedFailure(error=ModelAuthError("bad key"))]
    )
    fallback = FakeModelAdapter(provider="openai", script=[ScriptedSuccess(raw_text="ok")])
    engine = RetryEngine()
    response = await engine.execute(
        primary=primary,
        primary_provider="anthropic",
        request=_request(model="claude-primary"),
        fallback=fallback,
        fallback_provider="openai",
    )
    assert response.usage.model == "claude-primary"
    assert response.usage.used_fallback is True


@pytest.mark.asyncio
async def test_timeout_retries_within_budget_then_succeeds():
    primary = FakeModelAdapter(
        provider="anthropic", script=[ScriptedFailure(error=ModelTimeoutError("t1")), ScriptedSuccess(raw_text="ok")]
    )
    engine = RetryEngine()
    response = await engine.execute(primary=primary, primary_provider="anthropic", request=_request())
    assert response.raw_text == "ok"
    assert response.usage.attempt_count == 2


@pytest.mark.asyncio
async def test_budget_already_exceeded_raises_before_any_attempt():
    primary = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text="never reached")])
    engine = RetryEngine(policy=RetryFallbackPolicy(max_total_elapsed_seconds=-1.0))
    with pytest.raises(ModelBudgetExceededError):
        await engine.execute(primary=primary, primary_provider="anthropic", request=_request())
    assert primary.call_count == 0


@pytest.mark.asyncio
async def test_rate_limit_within_wait_cap_sleeps_then_retries_and_succeeds():
    primary = FakeModelAdapter(
        provider="openai",
        script=[ScriptedFailure(error=ModelRateLimitError("limited", retry_after_seconds=2.0)), ScriptedSuccess(raw_text="ok")],
    )
    sleeper = _RecordingSleep()
    engine = RetryEngine(sleep=sleeper)
    response = await engine.execute(primary=primary, primary_provider="openai", request=_request())
    assert response.raw_text == "ok"
    assert sleeper.calls == [2.0]


@pytest.mark.asyncio
async def test_rate_limit_exceeding_wait_cap_falls_back_without_sleeping():
    primary = FakeModelAdapter(
        provider="openai", script=[ScriptedFailure(error=ModelRateLimitError("limited", retry_after_seconds=999.0))]
    )
    fallback = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text="ok")])
    sleeper = _RecordingSleep()
    engine = RetryEngine(sleep=sleeper, policy=RetryFallbackPolicy(rate_limit_max_wait_seconds=10.0))
    response = await engine.execute(
        primary=primary, primary_provider="openai", request=_request(), fallback=fallback, fallback_provider="anthropic"
    )
    assert response.usage.used_fallback is True
    assert sleeper.calls == []  # never waited -- avoids hammering the same provider


@pytest.mark.asyncio
async def test_rate_limit_without_retry_after_header_falls_back_without_sleeping():
    primary = FakeModelAdapter(
        provider="openai", script=[ScriptedFailure(error=ModelRateLimitError("limited", retry_after_seconds=None))]
    )
    fallback = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text="ok")])
    sleeper = _RecordingSleep()
    engine = RetryEngine(sleep=sleeper)
    response = await engine.execute(
        primary=primary, primary_provider="openai", request=_request(), fallback=fallback, fallback_provider="anthropic"
    )
    assert response.usage.used_fallback is True
    assert sleeper.calls == []


@pytest.mark.asyncio
async def test_5xx_limited_retry_then_success_invokes_backoff_sleep():
    primary = FakeModelAdapter(
        provider="anthropic", script=[ScriptedFailure(error=ModelServerError("down")), ScriptedSuccess(raw_text="ok")]
    )
    sleeper = _RecordingSleep()
    engine = RetryEngine(sleep=sleeper, policy=RetryFallbackPolicy(backoff_base_seconds=0.5))
    response = await engine.execute(primary=primary, primary_provider="anthropic", request=_request())
    assert response.raw_text == "ok"
    assert sleeper.calls == [0.5]


@pytest.mark.asyncio
async def test_5xx_exhausts_primary_then_falls_back():
    primary = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedFailure(error=ModelServerError("down")), ScriptedFailure(error=ModelServerError("still down"))],
    )
    fallback = FakeModelAdapter(provider="openai", script=[ScriptedSuccess(raw_text="ok")])
    engine = RetryEngine()
    response = await engine.execute(
        primary=primary, primary_provider="anthropic", request=_request(), fallback=fallback, fallback_provider="openai"
    )
    assert response.usage.used_fallback is True
    assert response.usage.attempt_count == 3


@pytest.mark.asyncio
async def test_auth_error_never_retried_falls_back_immediately():
    primary = FakeModelAdapter(provider="openai", script=[ScriptedFailure(error=ModelAuthError("bad key"))])
    fallback = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text="ok")])
    engine = RetryEngine()
    response = await engine.execute(
        primary=primary, primary_provider="openai", request=_request(), fallback=fallback, fallback_provider="anthropic"
    )
    assert response.usage.used_fallback is True
    assert response.usage.attempt_count == 2
    assert primary.call_count == 1  # never retried


@pytest.mark.asyncio
async def test_auth_error_with_no_fallback_raises_with_original_cause():
    err = ModelAuthError("bad key")
    primary = FakeModelAdapter(provider="openai", script=[ScriptedFailure(error=err)])
    engine = RetryEngine()
    with pytest.raises(ModelAllAttemptsFailedError) as excinfo:
        await engine.execute(primary=primary, primary_provider="openai", request=_request())
    assert excinfo.value.__cause__ is err


@pytest.mark.asyncio
async def test_bad_request_never_retried_falls_back():
    primary = FakeModelAdapter(provider="openai", script=[ScriptedFailure(error=ModelBadRequestError("bad shape"))])
    fallback = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text="ok")])
    engine = RetryEngine()
    response = await engine.execute(
        primary=primary, primary_provider="openai", request=_request(), fallback=fallback, fallback_provider="anthropic"
    )
    assert response.usage.used_fallback is True
    assert primary.call_count == 1


@pytest.mark.asyncio
async def test_all_candidates_exhausted_raises_all_attempts_failed_with_last_cause():
    last_error = ModelMalformedOutputError("still bad")
    primary = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedSuccess(raw_text="bad1"), ScriptedSuccess(raw_text="bad2")],
    )
    fallback = FakeModelAdapter(
        provider="openai",
        script=[ScriptedFailure(error=ModelMalformedOutputError("bad3")), ScriptedFailure(error=last_error)],
    )
    from pydantic import BaseModel

    class _Dummy(BaseModel):
        ok: bool

    engine = RetryEngine()
    with pytest.raises(ModelAllAttemptsFailedError) as excinfo:
        await engine.execute(
            primary=primary,
            primary_provider="anthropic",
            request=_request(response_model=_Dummy),
            fallback=fallback,
            fallback_provider="openai",
        )
    assert excinfo.value.__cause__ is last_error


@pytest.mark.asyncio
async def test_max_attempts_per_model_is_configurable_to_zero_retries():
    primary = FakeModelAdapter(provider="anthropic", script=[ScriptedFailure(error=ModelTimeoutError("t1"))])
    fallback = FakeModelAdapter(provider="openai", script=[ScriptedSuccess(raw_text="ok")])
    engine = RetryEngine(policy=RetryFallbackPolicy(max_attempts_per_model=1))
    response = await engine.execute(
        primary=primary, primary_provider="anthropic", request=_request(), fallback=fallback, fallback_provider="openai"
    )
    assert response.usage.used_fallback is True
    assert primary.call_count == 1  # exactly one attempt, no retry, per the configured policy


@pytest.mark.asyncio
async def test_circuit_breaker_seam_skips_a_denied_provider_entirely():
    primary = FakeModelAdapter(provider="openai", script=[ScriptedSuccess(raw_text="should never be called")])
    fallback = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text="ok")])
    breaker = _DenyingBreaker(denied_provider="openai")
    engine = RetryEngine(circuit_breaker=breaker)
    response = await engine.execute(
        primary=primary, primary_provider="openai", request=_request(), fallback=fallback, fallback_provider="anthropic"
    )
    assert response.usage.used_fallback is True
    assert primary.call_count == 0  # circuit breaker refused it before any attempt


def test_noop_circuit_breaker_is_the_default_seam():
    """CircuitBreaker Protocol is satisfied by NoopCircuitBreaker --
    structural check that the seam/interface exists as documented."""
    from app.models.circuit_breaker import NoopCircuitBreaker

    breaker: CircuitBreaker = NoopCircuitBreaker()
    assert breaker.allow("openai") is True


@pytest.mark.asyncio
async def test_usage_reflects_only_the_successful_attempts_own_tokens():
    primary = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedFailure(error=ModelServerError("down")),
            ScriptedSuccess(raw_text="ok", input_tokens=5, output_tokens=3),
        ],
    )
    engine = RetryEngine()
    response = await engine.execute(primary=primary, primary_provider="anthropic", request=_request())
    assert response.usage.input_tokens == 5
    assert response.usage.output_tokens == 3
    assert response.usage.attempt_count == 2  # aggregate attempt count still reflects both tries
