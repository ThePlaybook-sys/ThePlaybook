"""Circuit breaker seam (Milestone 4.3, requirement 10) -- deliberately
NOT a real distributed circuit breaker. Mac's explicit instruction: do
not build one unless direct inspection proves it necessary; design the
seam/state for one and document it for later.

**Why not now, concretely:** a real circuit breaker (trip on N failures
within a window, half-open probe, shared trip state across concurrent
requests/processes) only earns its complexity once live traffic exists to
actually overwhelm a failing provider -- this milestone makes zero live
calls, and `app.models.retry_policy`'s own per-request budget
(`RetryFallbackPolicy.max_total_elapsed_seconds`/`max_attempts_per_model`)
already bounds the damage a single failing request can do. Volume 2
Section 10 does call for "circuit breakers on the Orchestrator to stop a
single runaway request... from cascading into a token-exhaustion cost or
availability incident" -- that requirement is about *within one request*
(exactly what the retry engine's elapsed-time/call-count budget already
enforces), not necessarily a cross-request, provider-health-tracking
breaker. Whether the stronger, shared-state version is also needed is a
real open question, not decided here -- flagged for whichever milestone
first runs real traffic and can observe whether it's actually needed.

**The seam this module reserves, so wiring a real implementation later
never requires touching `retry_policy.py`'s call sites:** a
`CircuitBreaker` Protocol with two methods -- `allow(provider: str) ->
bool` (checked before attempting a call) and `record_outcome(provider:
str, *, succeeded: bool) -> None` (called after every attempt, success or
failure). `NoopCircuitBreaker` is the only implementation that exists
today: `allow` always returns `True`, `record_outcome` does nothing. The
retry engine depends only on the `CircuitBreaker` Protocol, not on
`NoopCircuitBreaker` specifically, so a future stateful implementation is
a drop-in replacement.
"""
from __future__ import annotations

from typing import Protocol


class CircuitBreaker(Protocol):
    def allow(self, provider: str) -> bool:
        """Return `False` to refuse even attempting `provider` right now
        (tripped). `NoopCircuitBreaker` always returns `True`."""
        ...

    def record_outcome(self, provider: str, *, succeeded: bool) -> None:
        """Called once per attempt, success or failure, so a real
        implementation can update its trip state. `NoopCircuitBreaker`
        does nothing."""
        ...


class NoopCircuitBreaker:
    """The only `CircuitBreaker` implementation built in Milestone 4.3 --
    never refuses a call, never tracks anything. `app.models.retry_policy`
    depends on the `CircuitBreaker` Protocol above, not on this class
    directly, specifically so a future stateful breaker can be swapped in
    with zero change to the retry engine's own call sites."""

    def allow(self, provider: str) -> bool:
        return True

    def record_outcome(self, provider: str, *, succeeded: bool) -> None:
        return None
