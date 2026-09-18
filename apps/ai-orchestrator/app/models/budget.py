"""A hard, counted ceiling on outbound model requests (2026-09-18).

**Why this exists rather than an arithmetic bound.** Until now the only
protection against an LLM fan-out was a calculation -- games per run
multiplied by an assumed calls-per-game. That is an estimate about code,
not a control over it: it holds exactly as long as nobody adds an agent,
a retry, a second pass, or a loop. HQ's requirement is explicit, and
correct -- the ceiling has to live at the outbound boundary and *refuse*,
so that a bound cannot be exceeded even if the orchestration above it
changes in ways this file has never heard of.

**Where the boundary is.** Every model call in this service, without
exception, goes `Agent -> ModelRouter.route -> AdapterRegistry.get ->
ModelAdapter.complete`. `complete()` is the one method that reaches a
provider. Wrapping it is therefore sufficient AND necessary: sufficient
because nothing else talks to a provider, necessary because counting
anywhere higher (agents attempted, candidates evaluated) counts
intentions rather than requests, and the retry engine can turn one
intention into several requests.

**Fail closed, loudly.** Exhausting the budget raises
`LlmBudgetExceededError`. It is deliberately NOT a
`app.models.errors` failure type: those are per-attempt provider
failures that the retry engine is designed to absorb and retry, which is
the precise opposite of what a budget breach must do. A breach is a
control-plane fault about the run, not a transient fault about one
request, and it must not be retried into further spend.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.base import ModelAdapter
from app.models.router import AdapterRegistry
from app.models.types import ModelRequest, ModelResponse


class LlmBudgetExceededError(Exception):
    """Raised at the adapter boundary when a request would exceed the
    authorized ceiling. Carries the numbers so the failure explains
    itself without needing the log."""

    def __init__(self, *, limit: int, attempted: int) -> None:
        self.limit = limit
        self.attempted = attempted
        super().__init__(
            f"LLM request refused: this run has already spent its authorized ceiling of "
            f"{limit} model requests (attempt #{attempted}). Refusing rather than "
            f"truncating -- an incomplete run is never reported as a complete one."
        )


@dataclass
class CallBudget:
    """One run's remaining allowance, shared by every adapter in a
    registry so the count is across ALL providers rather than per
    provider -- an anthropic call and an openai call spend the same
    budget."""

    limit: int
    used: int = field(default=0)

    def consume(self) -> None:
        """Reserves one request, or refuses. Called immediately BEFORE
        the provider request is issued, never after: a request that was
        sent and then failed has still been spent, and counting on
        success would let a retry storm bypass the ceiling entirely."""
        attempted = self.used + 1
        if attempted > self.limit:
            raise LlmBudgetExceededError(limit=self.limit, attempted=attempted)
        self.used = attempted

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit


@dataclass(frozen=True)
class BudgetedModelAdapter(ModelAdapter):
    """Wraps exactly one real adapter, spending from a shared budget
    before delegating. Implements `ModelAdapter` so it is
    indistinguishable to the router, the retry engine and every agent --
    nothing upstream needs to know it exists, which is what makes the
    ceiling unbypassable rather than merely conventional."""

    inner: ModelAdapter
    budget: CallBudget

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.budget.consume()
        return await self.inner.complete(request)


def budgeted_registry(registry: AdapterRegistry, budget: CallBudget) -> AdapterRegistry:
    """Returns a registry whose every adapter spends from `budget`.

    An empty registry stays empty -- a provider with no configured key is
    still absent, and `AdapterRegistry.get` still raises
    `UnknownProviderError` for it, exactly as before. This function adds
    a ceiling; it never adds a provider.
    """
    return AdapterRegistry(
        adapters={name: BudgetedModelAdapter(inner=adapter, budget=budget) for name, adapter in registry.adapters.items()}
    )
