"""The retry/fallback engine (Milestone 4.3, requirement 9) -- the one
place `max_attempts`/`max_elapsed_time`/per-error-type policy lives, so
neither the router nor a future agent has to reimplement it. Consumes
any two `ModelAdapter`s (primary + optional fallback); knows nothing
about OpenAI/Anthropic/Fake specifically.

**The exact retry/fallback matrix implemented, per Mac's own requirement
9 (verbatim mapping, not a reinterpretation):**

| Failure | Primary-model retry | Then |
|---|---|---|
| Malformed structured output | one repair/retry against primary | fallback if configured |
| Timeout | limited retry, only if time budget permits | fallback if configured |
| 429 rate limit | respect `Retry-After` if within the wait cap; otherwise none | fallback if configured (avoids hammering) |
| 5xx / provider unavailable | limited retry (fixed backoff) | fallback if configured |
| Auth / invalid key | **no retry** | fallback if configured (fallback may be a different provider with different credentials) |
| Other non-transient 4xx | **no retry** | fallback if configured |

"Limited retry" is implemented as one shared, configurable
`RetryFallbackPolicy.max_attempts_per_model` (default 2 -- the initial
attempt plus one retry) applied uniformly to malformed/timeout/5xx,
rather than a different hardcoded number per failure type -- Mac's own
requirement 9 gives qualitative language ("one," "limited") for each but
no differing exact counts, so one shared, clearly-named, easily-tuned
number is the simplest faithful implementation, flagged here rather than
silently picking three different unexplained magic numbers.

**"One repair/retry" for malformed output, precisely what "repair" means
here:** a same-request retry against the same model -- this milestone
does NOT implement re-prompting with the validation error appended (a
real "ask the model to fix its own mistake" repair loop). That's a
genuine refinement a later milestone can add without changing this
engine's public shape (the retry loop already exists; only what request
is retried would change) -- flagged explicitly as a scope decision, not
silently assumed to be already built.

**Budget enforcement:** `max_total_elapsed_seconds` is checked before
every attempt (primary and fallback alike) -- once exceeded, no further
attempt is made anywhere, fallback included, and
`errors.ModelBudgetExceededError` is raised. `max_attempts_per_model`
bounds each model independently.

**Circuit breaker seam used, not a real breaker:** `circuit_breaker.
allow(provider)` is checked before ever attempting a provider;
`record_outcome` is called after every attempt. The default
`NoopCircuitBreaker` (`app.models.circuit_breaker`) never refuses and
never tracks anything -- see that module's docstring for why a real one
isn't built yet.

**Future cost accounting for retries/fallback (requirement 11):** the
returned `ModelResponse.usage` reflects only the *successful* attempt's
own token/cost fields (never fabricated from a failed attempt) --
`attempt_count` and `used_fallback` are the aggregate signal a future
cost-tracking consumer needs to know "this recommendation cost N calls,
not 1," without this engine inventing a cost number no attempt actually
reported.

**Milestone 5.4 pre-implementation fix (Decision BF):** `execute()`
previously ran the fallback candidate against the exact same `request`
object built for the primary -- meaning `request.model` (fixed to the
caller's `decision.primary_model` before `execute()` is ever called) was
sent to, and echoed back in `usage.model` by, the fallback adapter too.
`provider`/`used_fallback` were never affected (both are set by this
engine itself, from `provider_name`/`is_fallback`, never from the
request) -- only `model_name` provenance was wrong under fallback. Fixed
by accepting an explicit `fallback_model` and swapping it into a
per-candidate request via `dataclasses.replace` immediately before that
candidate's own attempts, rather than threading two separately-built
`ModelRequest`s through every caller.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace

from app.models.base import ModelAdapter
from app.models.circuit_breaker import CircuitBreaker, NoopCircuitBreaker
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
from app.models.types import ModelRequest, ModelResponse


@dataclass(frozen=True)
class RetryFallbackPolicy:
    max_attempts_per_model: int = 2
    max_total_elapsed_seconds: float = 30.0
    rate_limit_max_wait_seconds: float = 10.0
    backoff_base_seconds: float = 0.5


@dataclass
class AttemptRecord:
    provider: str
    model: str
    outcome: str  # "success" | "malformed" | "timeout" | "rate_limit" | "server_error" | "auth_error" | "bad_request" | "budget_exceeded"
    elapsed_seconds: float
    error: BaseException | None = None


@dataclass
class _CandidateExhausted:
    """Internal sentinel: this candidate's attempts are done (no
    success), distinguishing "ran out of attempts, try the next
    candidate" from "ran out of time budget, stop everywhere."""

    budget_exceeded: bool


class RetryEngine:
    def __init__(
        self,
        *,
        policy: RetryFallbackPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        sleep=None,
        clock=None,
    ):
        self._policy = policy or RetryFallbackPolicy()
        self._circuit_breaker = circuit_breaker or NoopCircuitBreaker()
        # Injectable clock/sleep -- tests never actually wait in real time,
        # matching this codebase's existing preference for deterministic,
        # fast tests over real timing dependencies.
        self._sleep = sleep
        self._clock = clock or time.monotonic

    async def execute(
        self,
        *,
        primary: ModelAdapter,
        primary_provider: str,
        request: ModelRequest,
        fallback: ModelAdapter | None = None,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
    ) -> ModelResponse:
        """`fallback_model` (Decision BF): the model identity the fallback
        PROVIDER should actually be asked for. `None` (a fallback-less
        call, or a caller not yet updated) preserves the pre-fix behavior
        of reusing `request.model` unchanged -- every caller that DOES
        configure a fallback must pass its own `decision.fallback_model`
        here, never leave this `None` while also passing `fallback=`."""
        start = self._clock()
        attempts: list[AttemptRecord] = []

        for provider_name, adapter, candidate_request, is_fallback in self._candidates(
            primary, primary_provider, request, fallback, fallback_provider, fallback_model
        ):
            if not self._circuit_breaker.allow(provider_name):
                continue
            outcome = await self._run_against(adapter, provider_name, candidate_request, start, attempts)
            if isinstance(outcome, ModelResponse):
                outcome.usage.attempt_count = len(attempts)
                outcome.usage.used_fallback = is_fallback
                return outcome
            if outcome.budget_exceeded:
                raise ModelBudgetExceededError(
                    f"model retry/fallback budget exceeded after {self._clock() - start:.2f}s "
                    f"({len(attempts)} attempt(s)) for task_type={request.task_type!r}"
                ) from _last_error(attempts)

        raise ModelAllAttemptsFailedError(
            f"all configured model(s) failed for task_type={request.task_type!r} "
            f"after {len(attempts)} attempt(s): "
            f"{[(a.provider, a.outcome) for a in attempts]}"
        ) from _last_error(attempts)

    @staticmethod
    def _candidates(primary, primary_provider, request, fallback, fallback_provider, fallback_model):
        yield primary_provider, primary, request, False
        if fallback is not None:
            # Decision BF: the fallback candidate gets its OWN request,
            # carrying the fallback's own model identity -- `request`
            # itself (built by the caller for the primary) is never
            # mutated or reused verbatim here. `fallback_model=None`
            # (an un-migrated caller) falls back to the old, buggy-but-
            # explicit behavior of reusing `request.model` rather than
            # silently guessing.
            fallback_request = replace(request, model=fallback_model) if fallback_model is not None else request
            yield fallback_provider, fallback, fallback_request, True

    async def _run_against(
        self,
        adapter: ModelAdapter,
        provider_name: str,
        request: ModelRequest,
        start: float,
        attempts: list[AttemptRecord],
    ) -> ModelResponse | _CandidateExhausted:
        attempt_in_model = 0
        while attempt_in_model < self._policy.max_attempts_per_model:
            elapsed = self._clock() - start
            if elapsed >= self._policy.max_total_elapsed_seconds:
                return _CandidateExhausted(budget_exceeded=True)
            attempt_in_model += 1

            try:
                response = await adapter.complete(request)
            except ModelAuthError as exc:
                self._circuit_breaker.record_outcome(provider_name, succeeded=False)
                attempts.append(_record(provider_name, request.model, "auth_error", start, self._clock, exc))
                return _CandidateExhausted(budget_exceeded=False)  # no retry, per the matrix
            except ModelBadRequestError as exc:
                self._circuit_breaker.record_outcome(provider_name, succeeded=False)
                attempts.append(_record(provider_name, request.model, "bad_request", start, self._clock, exc))
                return _CandidateExhausted(budget_exceeded=False)  # no retry, per the matrix
            except ModelRateLimitError as exc:
                self._circuit_breaker.record_outcome(provider_name, succeeded=False)
                attempts.append(_record(provider_name, request.model, "rate_limit", start, self._clock, exc))
                wait = exc.retry_after_seconds
                remaining_budget = self._policy.max_total_elapsed_seconds - (self._clock() - start)
                if wait is None or wait > self._policy.rate_limit_max_wait_seconds or wait > remaining_budget:
                    return _CandidateExhausted(budget_exceeded=False)  # avoid hammering; move to fallback
                if self._sleep is not None:
                    await self._sleep(wait)
                continue
            except ModelTimeoutError as exc:
                self._circuit_breaker.record_outcome(provider_name, succeeded=False)
                attempts.append(_record(provider_name, request.model, "timeout", start, self._clock, exc))
                continue  # limited retry, bounded by max_attempts_per_model and the elapsed check above
            except ModelServerError as exc:
                self._circuit_breaker.record_outcome(provider_name, succeeded=False)
                attempts.append(_record(provider_name, request.model, "server_error", start, self._clock, exc))
                if self._sleep is not None:
                    await self._sleep(self._policy.backoff_base_seconds)
                continue
            except ModelMalformedOutputError as exc:
                self._circuit_breaker.record_outcome(provider_name, succeeded=False)
                attempts.append(_record(provider_name, request.model, "malformed", start, self._clock, exc))
                continue  # one repair/retry, bounded by max_attempts_per_model
            else:
                self._circuit_breaker.record_outcome(provider_name, succeeded=True)
                attempts.append(_record(provider_name, request.model, "success", start, self._clock, None))
                return response

        return _CandidateExhausted(budget_exceeded=False)


def _record(provider, model, outcome, start, clock, error) -> AttemptRecord:
    return AttemptRecord(provider=provider, model=model, outcome=outcome, elapsed_seconds=clock() - start, error=error)


def _last_error(attempts: list[AttemptRecord]) -> BaseException | None:
    for attempt in reversed(attempts):
        if attempt.error is not None:
            return attempt.error
    return None
