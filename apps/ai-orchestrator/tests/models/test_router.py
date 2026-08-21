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


# --- canonical model_registry-backed provider resolution (Milestone 4.4 pre-check) ---


def test_route_resolves_provider_from_model_registry_lookup_not_name():
    """The canonical path: provider comes from a model_registry-derived
    dict, not from parsing the model name at all -- proven with a model
    name that would infer WRONG under the deprecated prefix guesser."""
    rule = {"task_type": "injury_analysis", "primary_model": "gpt-mystery-9000", "fallback_model": None}
    decision = ModelRouter.route(rule, model_providers={"gpt-mystery-9000": "anthropic"})
    assert decision.primary_provider == "anthropic"  # NOT "openai", despite the "gpt-" name


def test_route_cross_provider_via_registry_lookup():
    rule = {"task_type": "consensus_reconciliation", "primary_model": "gpt-4o", "fallback_model": "claude-sonnet-5"}
    decision = ModelRouter.route(rule, model_providers={"gpt-4o": "openai", "claude-sonnet-5": "anthropic"})
    assert decision.primary_provider == "openai"
    assert decision.fallback_provider == "anthropic"


def test_route_model_missing_from_registry_lookup_raises_not_silently_guesses():
    """Requirement: 'a routing rule that references a model missing from
    canonical model_registry should eventually produce a clear
    configuration error rather than silently guessing its provider from
    its name.' Proven here, now -- not deferred."""
    rule = {"task_type": "injury_analysis", "primary_model": "claude-sonnet-5", "fallback_model": None}
    with pytest.raises(UnknownProviderError, match="claude-sonnet-5"):
        ModelRouter.route(rule, model_providers={"claude-opus-5": "anthropic"})  # primary model absent from lookup


def test_route_fallback_missing_from_registry_lookup_also_raises():
    rule = {"task_type": "injury_analysis", "primary_model": "claude-sonnet-5", "fallback_model": "claude-haiku-4-5-20251001"}
    with pytest.raises(UnknownProviderError, match="claude-haiku-4-5-20251001"):
        ModelRouter.route(rule, model_providers={"claude-sonnet-5": "anthropic"})  # fallback absent


def test_route_with_no_lookup_at_all_still_falls_back_to_deprecated_inference():
    """Backward compatibility, explicitly temporary -- callers that don't
    supply model_providers at all still get the pre-v4.13 behavior."""
    rule = {"task_type": "injury_analysis", "primary_model": "claude-sonnet-5", "fallback_model": None}
    decision = ModelRouter.route(rule)  # no model_providers kwarg
    assert decision.primary_provider == "anthropic"
