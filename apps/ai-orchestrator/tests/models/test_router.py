"""Tests for app.models.router (Milestone 4.3, requirement 8)."""
from __future__ import annotations

import pytest

from app.models.fake_adapter import FakeModelAdapter
from app.models.router import AdapterRegistry, ModelRouter, UnknownProviderError, infer_provider


@pytest.mark.parametrize(
    "model_name,expected",
    [
        ("claude-sonnet-5", "anthropic"),
        ("claude-opus-5", "anthropic"),
        ("claude-haiku-4-5-20251001", "anthropic"),
        ("gpt-4o", "openai"),
        ("gpt-4o-mini", "openai"),
        ("o1-preview", "openai"),
        ("chatgpt-4o-latest", "openai"),
    ],
)
def test_infer_provider_known_prefixes(model_name, expected):
    assert infer_provider(model_name) == expected


def test_infer_provider_unrecognized_model_raises():
    with pytest.raises(UnknownProviderError):
        infer_provider("some-mystery-model-9000")


def test_route_selects_primary_and_fallback_provider():
    rule = {
        "task_type": "injury_analysis",
        "primary_model": "claude-sonnet-5",
        "fallback_model": "claude-haiku-4-5-20251001",
        "min_tier_for_second_pass": "elite",
    }
    decision = ModelRouter.route(rule)
    assert decision.primary_model == "claude-sonnet-5"
    assert decision.primary_provider == "anthropic"
    assert decision.fallback_model == "claude-haiku-4-5-20251001"
    assert decision.fallback_provider == "anthropic"
    assert decision.min_tier_for_second_pass == "elite"


def test_route_cross_provider_primary_and_fallback():
    rule = {"task_type": "consensus_reconciliation", "primary_model": "gpt-4o", "fallback_model": "claude-sonnet-5"}
    decision = ModelRouter.route(rule)
    assert decision.primary_provider == "openai"
    assert decision.fallback_provider == "anthropic"


def test_route_with_no_fallback_configured():
    rule = {"task_type": "solo_task", "primary_model": "claude-opus-5", "fallback_model": None}
    decision = ModelRouter.route(rule)
    assert decision.fallback_model is None
    assert decision.fallback_provider is None


def test_adapter_registry_returns_registered_adapter():
    fake = FakeModelAdapter(provider="anthropic", script=[])
    registry = AdapterRegistry(adapters={"anthropic": fake})
    assert registry.get("anthropic") is fake


def test_adapter_registry_missing_provider_raises_clearly():
    registry = AdapterRegistry(adapters={})
    with pytest.raises(UnknownProviderError):
        registry.get("openai")
