"""Provider-error contract every adapter must translate vendor errors into.

Callers (workers, the caching boundary, eventually agents) only ever handle
these types -- a vendor-specific exception (an httpx error, a vendor SDK's
own exception class, an unexpected response shape, etc.) must never escape
an adapter implementation. This is what keeps "swap the vendor behind an
adapter" from leaking into error-handling code anywhere upstream, not just
into data shape.
"""
from __future__ import annotations


class ProviderError(Exception):
    """Base for every error an adapter can raise. Callers should generally
    catch this rather than a specific subclass, unless they need to react
    differently to rate limiting vs. an outage."""

    def __init__(self, message: str, *, provider: str):
        super().__init__(message)
        self.provider = provider


class ProviderAuthError(ProviderError):
    """Invalid, expired, or missing credentials for this provider."""


class ProviderRateLimitError(ProviderError):
    """Provider rejected the call due to rate limiting or quota exhaustion."""

    def __init__(self, message: str, *, provider: str, retry_after_seconds: float | None = None):
        super().__init__(message, provider=provider)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailableError(ProviderError):
    """Provider is unreachable, timed out, or returned a 5xx. The
    "simulated provider outage" scenario Phase 3's testing requirements
    call for should raise this."""


class ProviderDataError(ProviderError):
    """Provider responded successfully but the payload couldn't be
    normalized into our internal models (unexpected shape, missing
    required fields, etc.)."""
