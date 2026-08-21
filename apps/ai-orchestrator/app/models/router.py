"""Model routing (Milestone 4.3, requirement 8; provider resolution
corrected Milestone 4.4 pre-check, Decision 2). Pure decision logic over
an already-fetched routing-rule row (+ an optional model-name -> provider
lookup); the actual Supabase fetches are `app.persistence.model_config.
get_model_routing_rule`/`get_model` (Milestone 4.1) -- kept as separate
I/O steps so this module stays trivially unit-testable with plain dicts.

**Provider resolution, corrected (Milestone 4.4 pre-check, 2026-08-21).**
`model_registry.provider` (Volume 3 v4.13) is now the canonical source of
model-to-provider identity -- resolved via a `model_providers: dict[str,
str]` lookup the caller builds from `model_registry` rows (model_name ->
provider), not from the model's own name string. `infer_provider`'s
name-prefix mapping (`"claude-"` -> anthropic, `"gpt-"`/`"o1-"`/`"o3-"`/
`"o4-"`/`"chatgpt-"` -> openai) is kept, but **only** as an explicitly-
deprecated fallback for callers that don't supply a `model_providers`
lookup at all (backward compatibility for existing tests/fixture flows
written before v4.13 -- Mac's own instruction: "may remain temporarily...
if genuinely needed during migration, but... must not silently rescue
missing production model-registry configuration forever").

**The actual "must not silently rescue" enforcement:** once a caller DOES
supply `model_providers`, that dict is authoritative -- a model name
missing from it is a real configuration error (a routing rule referencing
a model that was never registered in `model_registry`), not a case to
fall back to guessing from the name. `route()` raises `UnknownProviderError`
in that case rather than silently inferring. Only the *no-lookup-supplied-
at-all* case still falls back to `infer_provider`.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.base import ModelAdapter

_ANTHROPIC_PREFIXES = ("claude-",)
_OPENAI_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "chatgpt-")


class UnknownProviderError(Exception):
    """Raised when a model's provider cannot be resolved -- either a
    `model_providers` lookup was supplied but doesn't contain the model
    (a real configuration gap: the routing rule references a model never
    registered in `model_registry`), or no lookup was supplied and the
    deprecated name-prefix fallback also doesn't recognize the model.
    Also raised by `AdapterRegistry` when no adapter is registered for a
    resolved provider name. Fails loud rather than silently defaulting to
    either provider."""


def infer_provider(model_name: str) -> str:
    """DEPRECATED (Milestone 4.4 pre-check, 2026-08-21) -- name-prefix
    guessing, kept only as `route()`'s fallback for callers that don't
    supply a `model_registry`-backed `model_providers` lookup at all. Do
    not call this directly for new code; resolve provider via
    `model_registry.provider` (Volume 3 v4.13) instead."""
    lowered = model_name.lower()
    if lowered.startswith(_ANTHROPIC_PREFIXES):
        return "anthropic"
    if lowered.startswith(_OPENAI_PREFIXES):
        return "openai"
    raise UnknownProviderError(f"cannot infer provider for model name {model_name!r}")


def _resolve_provider(model_name: str, model_providers: dict[str, str] | None) -> str:
    if model_providers is not None:
        try:
            return model_providers[model_name]
        except KeyError:
            raise UnknownProviderError(
                f"model {model_name!r} is referenced by a routing rule but has no "
                f"corresponding model_registry.provider entry -- register it in "
                f"model_registry before routing to it"
            ) from None
    # No lookup supplied at all: deprecated fallback, not the canonical path.
    return infer_provider(model_name)


@dataclass(frozen=True)
class RoutingDecision:
    task_type: str
    primary_model: str
    primary_provider: str
    fallback_model: str | None
    fallback_provider: str | None
    min_tier_for_second_pass: str | None


class ModelRouter:
    """Stateless -- `route()` is a pure function of an already-fetched
    `model_routing_rules` row plus an optional `model_registry`-derived
    `model_providers` lookup."""

    @staticmethod
    def route(routing_rule: dict, *, model_providers: dict[str, str] | None = None) -> RoutingDecision:
        primary_model = routing_rule["primary_model"]
        fallback_model = routing_rule.get("fallback_model")
        return RoutingDecision(
            task_type=routing_rule["task_type"],
            primary_model=primary_model,
            primary_provider=_resolve_provider(primary_model, model_providers),
            fallback_model=fallback_model,
            fallback_provider=_resolve_provider(fallback_model, model_providers) if fallback_model else None,
            min_tier_for_second_pass=routing_rule.get("min_tier_for_second_pass"),
        )


@dataclass(frozen=True)
class AdapterRegistry:
    """Maps a provider name ("openai"/"anthropic"/"fake"/...) to an
    already-constructed `ModelAdapter` instance. Supplied by the caller --
    a later milestone wires real `OpenAIModelAdapter`/
    `AnthropicModelAdapter` instances; tests wire `FakeModelAdapter`
    instances. This registry has no knowledge of API keys, HTTP clients,
    or construction details -- purely a lookup."""

    adapters: dict[str, ModelAdapter]

    def get(self, provider: str) -> ModelAdapter:
        try:
            return self.adapters[provider]
        except KeyError:
            raise UnknownProviderError(f"no adapter registered for provider {provider!r}") from None
