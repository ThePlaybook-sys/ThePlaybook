"""Read-only `recommendations` access for paid-cycle eligibility
(HQ Recomputation V1 owner decision, 2026-09-18).

**The question this module answers:** has this canonical game already
completed a paid intelligence cycle?

**Why it is game-scoped rather than run-scoped, which is the whole point.**
`ai-orchestrator` already refuses to recompute a `correlation_id` that
reached `cycle_completed_at`. But `correlation_id` is
`f"{master_refresh_run_id}:{game_id}"`, and a NEW `master_refresh_runs` row
is created every morning by `cron-schedule-refresh`. So that check is a
crash-retry protection scoped to one run, and it provably never fires
across days -- dev held three refresh runs dated 2026-09-16, -17 and -18,
each of which would have minted a fresh correlation and re-run the full
committee on identical evidence.

HQ's V1 rule is explicit that **`run_id` must not be the semantic reason a
game becomes eligible again**. So the identity used here is the canonical
`games.id` itself, and the evidence is `recommendations.cycle_completed_at`
-- both already persisted, which is why this needed no schema addition.

**What counts as "completed" is deliberately outcome-blind.**
`mark_recommendation_cycle_completed` is called unconditionally as the last
step once every candidate has been attempted, so a legitimate No Bet, a
bankroll-preservation product and a real recommendation all set it. That
matches HQ's rule exactly: a No Bet IS a completed paid cycle.

**What does NOT count**, equally deliberately: a cycle that never reached
its normal end leaves `cycle_completed_at` NULL and stays retryable, and a
game refused by the deterministic pre-LLM gate creates no row at all. Both
cost nothing and must remain free to try again later.
"""
from __future__ import annotations

import httpx


class RecommendationsReadError(Exception):
    """Raised when a `recommendations` read fails on Supabase's side."""


async def read_game_ids_with_completed_paid_cycle(
    client: httpx.AsyncClient, headers: dict, *, game_ids: list[str]
) -> set[str]:
    """Of `game_ids`, returns the subset that has already completed at
    least one paid intelligence cycle.

    Returns an empty set for an empty input without calling Supabase --
    an empty `in.()` filter is both wasteful and a PostgREST syntax risk.

    Deliberately returns a `set`: the caller subtracts it from the slate,
    and set semantics make "this game is done" idempotent no matter how
    many `recommendations` rows a game accumulated historically.
    """
    if not game_ids:
        return set()

    response = await client.get(
        "/rest/v1/recommendations",
        params={
            "game_id": f"in.({','.join(game_ids)})",
            # `not.is.null` is the completed-cycle test. A row existing is
            # NOT sufficient -- Milestone 4.9 creates it as the very first
            # step, before any real work, so a crashed attempt would
            # otherwise look identical to a finished one.
            "cycle_completed_at": "not.is.null",
            "select": "game_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise RecommendationsReadError(
            f"failed to read completed paid cycles: {response.status_code} {response.text}"
        )
    return {row["game_id"] for row in response.json()}
