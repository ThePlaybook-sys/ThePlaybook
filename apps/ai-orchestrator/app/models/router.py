"""Model routing (Milestone 4.3, requirement 8) -- "routing must come
from the existing `model_routing_rules`/`model_registry` architecture, do
not hard-code model choice inside individual agents." Pure decision
logic over an already-fetched routing-rule row; the actual Supabase fetch
is `app.persistence.model_config.get_model_routing_rule` (Milestone 4.1)
-- kept as a separate I/O step so this module stays trivially unit-
testable with a plain dict, matching this codebase's established
"pure computation separate from I/O" convention (e.g. `sports-intel-
layer`'s `master_refresh.slate` window filtering).

**A real schema gap, discovered during this milestone's re-inspection,
flagged rather than silently worked around:** neither `model_routing_
rules` nor `model_registry` (Volume 3 Section 8) has an explicit
`provider` column -- `primary_model`/`fallback_model`/`model_name` are
bare strings ("claude-sonnet-5", "gpt-4o") with no stored vendor
attribution. `infer_provider` below is an ASSUMED, name-prefix-based
mapping (`"claude-"` -> anthropic, `"gpt-"`/`"o1-"`/`"o3-"`/`"o4-"`/
`"chatgpt-"` -> openai) -- a reasonable stopgap for this milestone's
testing purposes, but NOT a permanent architecture decision. **Recommend
adding `model_registry.provider` (and/or `model_routing_rules.
primary_provider`/`.fallback_provider`) as a schema follow-up before
Milestone 4.4 wires real routing data against this** -- an unrecognized
prefix raises `UnknownProviderError` rather than guessing, so this gap
fails loud, never silently.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.base import ModelAdapter

_ANTHROPIC_PREFIXES = ("claude-",)
_OPENAI_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "chatgpt-")


class UnknownProviderError(Exception):
    """Raised when a model name doesn't match any known provider prefix,
    or when `AdapterRegistry` has no adapter registered for a resolved
    provider name -- fails loud rather than silently defaulting to
    either provider."""


def infer_provider(model_name: str) -> str:
    """ASSUMED, name-prefix-based (see module docstring) -- ` model_
    registry`/`model_routing_rules` carry no explicit provider column
    today."""
    lowered = model_name.lower()
    if lowered.startswith(_ANTHROPIC_PREFIXES):
        return "anthropic"
    if lowered.startswith(_OPENAI_PREFIXES):
        return "openai"
    raise UnknownProviderError(f"cannot infer provider for model name {model_name!r}")


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
    `model_routing_rules` row. No Supabase client, no caching, no
    knowledge of any specific model's real capabilities (that's `model_
    registry`'s job, consulted separately/optionally for cost/latency
    enrichment, not for the primary/fallback decision itself)."""

    @staticmethod
    def route(routing_rule: dict) -> RoutingDecision:
        primary_model = routing_rule["primary_model"]
        fallback_model = routing_rule.get("fallback_model")
        return RoutingDecision(
            task_type=routing_rule["task_type"],
            primary_model=primary_model,
            primary_provider=infer_provider(primary_model),
            fallback_model=fallback_model,
            fallback_provider=infer_provider(fallback_model) if fallback_model else None,
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
