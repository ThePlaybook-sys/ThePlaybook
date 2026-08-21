"""Tests for app.models.circuit_breaker (Milestone 4.3, requirement 10)."""
from __future__ import annotations

from app.models.circuit_breaker import NoopCircuitBreaker


def test_noop_always_allows():
    breaker = NoopCircuitBreaker()
    assert breaker.allow("openai") is True
    assert breaker.allow("anthropic") is True
    assert breaker.allow("anything") is True


def test_noop_record_outcome_does_nothing_and_does_not_raise():
    breaker = NoopCircuitBreaker()
    breaker.record_outcome("openai", succeeded=True)
    breaker.record_outcome("openai", succeeded=False)
    assert breaker.allow("openai") is True  # unaffected by recorded failures
