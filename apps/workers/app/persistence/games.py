"""Read-only `games` access (Milestone 4.9). Mirrors `ai-orchestrator`'s
own `app.persistence.games` eligibility policy -- `scheduled` is the
only pregame-recommendation-eligible status (carried forward unchanged
from Milestone 4.1/4.2's approved policy; this module does not
re-derive or second-guess it, it only reads by the same filter)."""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx


class GamesReadError(Exception):
    """Raised when a `games` read fails on Supabase's side."""


#: How far ahead a game must kick off to be a recommendation candidate at
#: all. A worker-level scoping decision that deliberately reuses the SAME
#: numeric value as Master Refresh's canonical `[today, today + 7 days)`
#: operating horizon (Volume 2 §8 v4.4, stated once in
#: `sports-intel-layer`'s `app.master_refresh.slate`), for the same
#: practical reason the Odds Worker's own `_CANDIDATE_WINDOW_DAYS` does:
#: Master Refresh only prepares `daily_game_intelligence` this far out, and
#: the specialized workers only poll odds/injuries/weather this far out, so
#: there is nothing for a recommendation to be built FROM beyond it. This
#: is not a reinterpretation of that horizon -- per its own docstring it
#: "governs Master Refresh's own game-identity/assembly work only" -- it is
#: this worker declaring its own, numerically aligned.
#:
#: **This constant is the fix for a real, live selection defect
#: (2026-09-17).** Before it, this read filtered on `status='scheduled'`
#: and nothing else, so the 06:15 cron selected **every remaining game in
#: the season** -- 257 of them, kicking off from that morning through
#: 2027-01-10 -- and dispatched one `ai-orchestrator` call per game. A
#: recommendation run must never process an entire season merely because
#: those games exist canonically.
RECOMMENDATION_WINDOW_DAYS = 7

#: How close to kickoff a game must be before it may enter its FIRST paid
#: recommendation cycle (HQ Recomputation V1 owner decision, 2026-09-18).
#:
#: **This does not replace the 7-day horizon above, and the two are not the
#: same kind of rule.** `RECOMMENDATION_WINDOW_DAYS` is the canonical
#: operating horizon every specialized worker shares -- what the system
#: prepares data for. This is an ADDITIONAL, narrower gate on *expensive
#: inference specifically*: a game can be fully prepared, fully eligible,
#: and still not worth paying a committee for until kickoff is close
#: enough that the lines and context have settled. Both bounds are sent in
#: the query so the intent stays legible rather than collapsing into
#: whichever number happens to be smaller.
#:
#: **The boundary is inclusive**: a game exactly 36h out IS eligible. Stated
#: explicitly because "at exactly 36 hours" is a case HQ asked to be
#: deterministic, and `<=` vs `<` is the whole of that determinism.
FIRST_PAID_RUN_WINDOW_HOURS = 36


async def read_eligible_game_ids(client: httpx.AsyncClient, headers: dict, *, now: datetime) -> list[str]:
    """Returns the `id` of every game eligible for a recommendation this
    cycle. Three filters, all deterministic and all enforced in the query
    rather than in Python, so an unbounded slate can never reach the
    dispatch loop in the first place:

    1. `status='scheduled'` -- never `live`/`final`/`postponed`/`canceled`,
       matching `ai-orchestrator`'s `PREGAME_WORKFLOW_ELIGIBLE_STATUSES`
       exactly. A completed game can never enter recommendation
       processing; there is nothing to recommend about a game that has
       already been played.
    2. `scheduled_start >= now` -- genuinely upcoming. `status` alone is
       not sufficient: a game whose provider never moved it off
       `scheduled` stays "eligible" forever under a status-only filter,
       which is exactly how two 2026-08 fixtures were still being
       dispatched in mid-September.
    3. `scheduled_start < now + RECOMMENDATION_WINDOW_DAYS` -- inside the
       authorized horizon. Beyond it there are no fresh odds, no
       assembled intelligence, and therefore nothing a committee could
       reason over; dispatching anyway spends the game-level fan-out to
       produce a guaranteed `no_configured_sportsbook_has_fresh_data`.
    4. `scheduled_start <= now + FIRST_PAID_RUN_WINDOW_HOURS` -- close
       enough to kickoff to be worth paying a committee for at all (HQ
       Recomputation V1). An additional gate on expensive inference, not a
       replacement for the horizon above.

    Returns `[]` when none qualify -- never fabricated, and an empty slate
    is a legitimate, non-error outcome (most of the week, for NFL)."""
    window_end = now + timedelta(days=RECOMMENDATION_WINDOW_DAYS)
    paid_run_cutoff = now + timedelta(hours=FIRST_PAID_RUN_WINDOW_HOURS)
    response = await client.get(
        "/rest/v1/games",
        params={
            "status": "eq.scheduled",
            # Three bounds, all in the query. `gte`/`lt` are the canonical
            # 7-day horizon; `lte` is the additional 36-hour first-paid-run
            # gate (HQ Recomputation V1). Sent separately rather than
            # pre-collapsed to whichever is smaller, so the horizon is
            # preserved rather than replaced.
            "scheduled_start": [
                f"gte.{now.isoformat()}",
                f"lt.{window_end.isoformat()}",
                f"lte.{paid_run_cutoff.isoformat()}",
            ],
            "select": "id",
            # Chronological, per Volume 5's "Neutral ordering (HQ Final
            # Decision 1): game-scoped cards order by
            # `games.scheduled_start` ... Never EV or confidence."
            #
            # `id.asc` is a TIEBREAK, not a second ranking rule, and it is
            # needed: a real NFL Sunday puts eight games at the same
            # 17:00 UTC kickoff, so `scheduled_start` alone leaves the
            # order among them unspecified by PostgREST and therefore
            # irreproducible between calls. A row id carries no
            # intelligence -- it is not EV, confidence, or any judgment
            # about the game -- so breaking ties on it keeps the set
            # "unordered-by-intelligence" exactly as Decision 1 requires,
            # while making a prefix of the slate deterministic.
            "order": "scheduled_start.asc,id.asc",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GamesReadError(f"failed to read eligible games: {response.status_code} {response.text}")
    return [row["id"] for row in response.json()]


#: Milestone 5.4 -- how far back this worker looks for grading
#: candidates. DERIVED, not a Blueprint number (same class of decision as
#: `sports-intel-layer`'s own `_RECONCILIATION_LOOKBACK_DAYS`): wide
#: enough that a game finalized just past `ai-orchestrator`'s
#: RECONCILIATION_WINDOW_HOURS (72h) is never missed, generous enough to
#: also catch a late SportsDataIO correction arriving after that window
#: without scanning the entire table's history forever. Flagged in the
#: Milestone 5.4 completion report as an accepted MVP scope choice, not
#: an exhaustive/unbounded guarantee.
GRADING_CANDIDATE_LOOKBACK_DAYS = 14


async def read_grading_candidate_game_ids(client: httpx.AsyncClient, headers: dict, *, now: datetime) -> list[str]:
    """Returns every game_id that is a Postgame Grading candidate this
    cycle: `postponed`/`canceled` (gradeable immediately, no waiting --
    see `app.orchestration.postgame_grading`'s own reasoning for why),
    or `final` and finalized within the lookback window. `ai-
    orchestrator`'s own endpoint is the one that actually checks
    reconciliation-eligibility per game (Decision BH) -- this read is
    deliberately generous/coarse, matching the Recommendation Worker's
    own "discover broadly, let the domain service decide" split (Decision
    BY: this service never duplicates AI/business logic, including
    grading-readiness logic)."""
    window_start = (now - timedelta(days=GRADING_CANDIDATE_LOOKBACK_DAYS)).isoformat()
    response = await client.get(
        "/rest/v1/games",
        params={
            "select": "id",
            "or": (
                f"(status.eq.postponed,status.eq.canceled,"
                f"and(status.eq.final,finalized_at.gte.{window_start}))"
            ),
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GamesReadError(f"failed to read grading candidate games: {response.status_code} {response.text}")
    return [row["id"] for row in response.json()]
