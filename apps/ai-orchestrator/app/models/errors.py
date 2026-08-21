"""Normalized model-provider errors (Milestone 4.3, requirement 2).

Every adapter (`OpenAIModelAdapter`, `AnthropicModelAdapter`,
`FakeModelAdapter`) raises exclusively from this hierarchy -- never a raw
vendor SDK/HTTP exception. This is the same normalization discipline
Volume 2 Section 8's provider-adapter pattern already established for
sports data providers, applied here to model providers: nothing upstream
(the retry engine, the router, an eventual agent) should ever need to
know whether a failure came from OpenAI's or Anthropic's REST API, only
which normalized category it falls into.

Classification below is CONFIRMED FROM PROVIDER DOCUMENTATION for the
HTTP-status-code mapping (both OpenAI's and Anthropic's public API
references document these codes identically: 401/403 authentication,
429 rate limit, 5xx server error, other 4xx client error) -- this is
standard REST convention, not a vendor-specific guess.
"""
from __future__ import annotations


class ModelError(Exception):
    """Base class for every normalized model-provider error. Carries the
    originating raw exception as `__cause__` (via `raise ... from exc`)
    at every adapter call site -- nothing about the underlying failure is
    lost, only wrapped, matching this codebase's existing
    `AgentContractError`/`GamesReadError`/etc. one-exception-per-boundary
    convention."""


class ModelTimeoutError(ModelError):
    """The request did not complete within `ModelRequest.timeout_seconds`."""


class ModelRateLimitError(ModelError):
    """HTTP 429. `retry_after_seconds` is the provider's own `Retry-After`
    header value when present, `None` when the provider didn't supply
    one -- never fabricated as a default wait time."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ModelServerError(ModelError):
    """HTTP 5xx -- the provider itself is failing/unavailable, not a
    request-shape problem."""


class ModelAuthError(ModelError):
    """HTTP 401/403 -- invalid/missing API key or insufficient permission.
    Never retried (Milestone 4.3 requirement 9's retry/fallback matrix) --
    a bad credential doesn't self-correct by trying again."""


class ModelBadRequestError(ModelError):
    """Any other non-transient 4xx (400, 404, 422, etc.) -- the request
    itself was malformed at the transport/API-contract level (not to be
    confused with `ModelMalformedOutputError`, which is about the model's
    *response content* failing structured-output validation). Never
    retried automatically -- retrying an identical malformed request
    produces the identical error."""


class ModelMalformedOutputError(ModelError):
    """The provider call itself succeeded (200 OK), but the response
    content failed structured-output validation against the
    `ModelRequest.response_model` the caller supplied (e.g.
    `AgentOutput`/`MetaAgentOutput`, Milestone 4.2). Distinct from every
    error above, which are all transport/API-level failures -- this one
    is a content-quality failure on an otherwise-successful call. Carries
    the underlying validation error as `__cause__`."""


class ModelBudgetExceededError(ModelError):
    """Raised by the retry/fallback engine (`app.models.retry_policy`),
    never by an individual adapter -- `RetryFallbackPolicy.
    max_total_elapsed_seconds` was reached before any attempt (primary or
    fallback) succeeded. Distinct from `ModelAllAttemptsFailedError`:
    this one specifically means "we ran out of time," not "we ran out of
    configured attempts/candidates while time remained.\""""


class ModelAllAttemptsFailedError(ModelError):
    """Raised by the retry/fallback engine when every configured
    candidate (primary, and fallback if configured) exhausted its
    attempts without success, and the reason was NOT running out of the
    elapsed-time budget (that case raises `ModelBudgetExceededError`
    instead). Carries the underlying last real error as `__cause__`."""
