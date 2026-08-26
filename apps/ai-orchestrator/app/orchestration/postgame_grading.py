"""Milestone 5.4's Postgame Review orchestration -- ties the deterministic
grading engine (`app.features.grading`) to persistence
(`app.persistence.postgame_grading`) for one game at a time, plus a
separate slate-level `bankroll_preservation` sweep. Reachable only from
`app.main`'s new internal endpoint, called by `apps/workers` once it has
discovered which game_ids are grading-eligible (Decision BY -- the
existing worker infrastructure discovers eligibility and dispatches;
this module never self-schedules).

**Reconciliation-eligibility (Decision BH), the actual mechanism used.**
`app.workers.reconciliation.is_reconciliation_complete` (sports-intel-
layer) takes a `checks_done: frozenset[str]` that is held ONLY in the
calling process's memory (that module's own docstring: "no worker-run-
history persistence layer exists yet") -- a separate service/process
(this one) cannot read it. This module instead recomputes the same
condition from durable state: `games.finalized_at` (persisted by the
Postgame Worker on the `final` transition) plus
`RECONCILIATION_WINDOW_HOURS = 72`, copied from -- and required to stay
in sync with -- `app.workers.reconciliation.CHECKPOINT_OFFSETS[-1]`
(sports-intel-layer, `("+72h", timedelta(hours=72))`), the same approved
schedule's final checkpoint. This is NOT "wait N minutes after kickoff"
(the pattern Decision BH explicitly forbids) -- it waits a fixed,
already-Mac-approved duration after a real, durable state transition
(finalization), using the exact number the existing schedule already
uses. It is an honest, flagged limitation, not a silent redesign: it
does not verify that every individual checkpoint actually ran
successfully, only that enough wall-clock time has passed for all of
them to have had their chance -- see the Milestone 5.4 completion report
for the full disposition of this gap.

**Postponed/canceled games are never gated on `finalized_at`** -- the
Postgame Worker only ever stamps `finalized_at` on a `final` transition,
so a postponed/canceled game would never satisfy the wait above. Those
statuses grade immediately as `VOID_NO_ACTION` via `app.features.
grading.grade_leg`'s own branch -- no reconciliation process exists for
them to wait on in the first place.

**`no_bet`/`bankroll_preservation` products never wait on any game data
at all** (Decisions BL/BM) -- their outcome is `NOT_APPLICABLE`
unconditionally, so they are graded opportunistically the moment they
are encountered, never gated by `_is_grading_eligible`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from app.features.consensus import CandidateDirectionError
from app.features.grading import GRADING_VERSION, MarketGradingUnsupportedError, grade_leg, rollup_product_outcome
from app.persistence.games import get_game_for_grading
from app.persistence.postgame_grading import (
    persist_leg_grade,
    persist_product_grade,
    read_latest_leg_grade_event,
    read_no_bet_products_by_game,
    read_recommendation_legs_by_game,
    read_recommendation_legs_by_product,
    read_recommendation_product,
    read_ungraded_bankroll_preservation_product_ids,
)

#: See module docstring -- MUST stay in sync with sports-intel-layer's
#: `app.workers.reconciliation.CHECKPOINT_OFFSETS[-1]` (`"+72h"`).
RECONCILIATION_WINDOW_HOURS = 72

_VOID_GAME_STATUSES = ("postponed", "canceled")
_UNGRADED_TERMINAL_PLACEHOLDER = "PENDING_MISSING_DATA"


@dataclass
class LegGradingResult:
    leg_id: str
    recommendation_product_id: str
    status: str  # "created" | "unchanged" | "corrected" | "skipped_not_eligible" | "skipped_unsupported_market" | "failed"
    outcome: str | None = None
    error: str | None = None


@dataclass
class ProductGradingResult:
    product_id: str
    status: str  # "created" | "unchanged" | "corrected" | "skipped_incomplete"
    outcome: str | None = None
    grade_event_id: str | None = None


@dataclass
class GameGradingResult:
    game_id: str
    status: str  # "graded" | "game_not_found"
    legs: list[LegGradingResult] = field(default_factory=list)
    no_bet_products: list[ProductGradingResult] = field(default_factory=list)
    products: list[ProductGradingResult] = field(default_factory=list)


def _is_grading_eligible(game: dict, now: datetime) -> bool:
    """See module docstring. `postponed`/`canceled` are eligible
    immediately; `final` is eligible only once
    `RECONCILIATION_WINDOW_HOURS` have elapsed since `finalized_at`;
    anything else (`scheduled`/`live`, or `final` with no `finalized_at`
    yet stamped) is not."""
    status = game["status"]
    if status in _VOID_GAME_STATUSES:
        return True
    if status != "final":
        return False
    finalized_at = game.get("finalized_at")
    if finalized_at is None:
        return False
    if isinstance(finalized_at, str):
        finalized_at = datetime.fromisoformat(finalized_at.replace("Z", "+00:00"))
    return now.astimezone(timezone.utc) >= finalized_at.astimezone(timezone.utc) + timedelta(hours=RECONCILIATION_WINDOW_HOURS)


async def _grade_no_bet_products(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, grading_version: str
) -> list[ProductGradingResult]:
    rows = await read_no_bet_products_by_game(client, headers, game_id=game_id)
    results = []
    for row in rows:
        status, event_id = await persist_product_grade(
            client,
            headers,
            recommendation_product_id=row["id"],
            grading_version=grading_version,
            outcome="NOT_APPLICABLE",
            leg_outcome_counts=None,
            correction_source=None,
        )
        results.append(ProductGradingResult(product_id=row["id"], status=status, outcome="NOT_APPLICABLE", grade_event_id=event_id))
    return results


async def _maybe_rollup_product(
    client: httpx.AsyncClient, headers: dict, *, recommendation_product_id: str, grading_version: str
) -> ProductGradingResult | None:
    """Computes and persists a product-level rollup ONLY once every one
    of its legs has a terminal grade for `grading_version` (Decision BK
    -- never a premature/partial rollup). Returns `None` (no write) when
    the product isn't a leg-bearing type here, or isn't ready yet."""
    product = await read_recommendation_product(client, headers, recommendation_product_id=recommendation_product_id)
    if product is None or product["recommendation_type"] not in ("single", "multiple_singles"):
        return None

    legs = await read_recommendation_legs_by_product(client, headers, recommendation_product_id=recommendation_product_id)
    leg_outcomes: list[str] = []
    for leg in legs:
        event = await read_latest_leg_grade_event(
            client, headers, recommendation_leg_id=leg["id"], grading_version=grading_version
        )
        # No event yet -- e.g. this leg's game hasn't reached reconciliation-
        # eligibility, or its market_type is currently unsupported (prop) --
        # treated as still-pending, never fabricated as a terminal result.
        leg_outcomes.append(event["outcome"] if event is not None else _UNGRADED_TERMINAL_PLACEHOLDER)

    try:
        outcome, counts = rollup_product_outcome(recommendation_type=product["recommendation_type"], leg_outcomes=leg_outcomes)
    except ValueError:
        return None

    if outcome == "PENDING_MISSING_DATA":
        return ProductGradingResult(product_id=recommendation_product_id, status="skipped_incomplete", outcome=outcome)

    status, event_id = await persist_product_grade(
        client,
        headers,
        recommendation_product_id=recommendation_product_id,
        grading_version=grading_version,
        outcome=outcome,
        leg_outcome_counts=counts,
    )
    return ProductGradingResult(product_id=recommendation_product_id, status=status, outcome=outcome, grade_event_id=event_id)


async def grade_game(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    now: datetime | None = None,
    grading_version: str = GRADING_VERSION,
) -> GameGradingResult:
    """Grades every `recommendation_leg`/`no_bet` product tied to
    `game_id`, then rolls up any leg-bearing product whose every leg is
    now terminally graded. Never raises for a single leg's grading
    failure -- isolated into that leg's own `LegGradingResult`, matching
    every other per-unit isolation boundary already established in this
    codebase (fan-out, candidate evaluation, explanation generation,
    activation snapshots)."""
    now = now or datetime.now(timezone.utc)

    game = await get_game_for_grading(client, headers, game_id=game_id)
    if game is None:
        return GameGradingResult(game_id=game_id, status="game_not_found")

    no_bet_results = await _grade_no_bet_products(client, headers, game_id=game_id, grading_version=grading_version)

    legs = await read_recommendation_legs_by_game(client, headers, game_id=game_id)
    eligible = _is_grading_eligible(game, now)

    leg_results: list[LegGradingResult] = []
    touched_product_ids: set[str] = set()
    for leg in legs:
        if not eligible:
            leg_results.append(
                LegGradingResult(leg_id=leg["id"], recommendation_product_id=leg["recommendation_product_id"], status="skipped_not_eligible")
            )
            continue
        try:
            result = grade_leg(
                market_type=leg["market_type"],
                selection=leg["selection"],
                point=leg["point"],
                home_team=game["home_team"],
                away_team=game["away_team"],
                game_status=game["status"],
                final_score=game.get("final_score"),
            )
        except MarketGradingUnsupportedError as exc:
            leg_results.append(
                LegGradingResult(
                    leg_id=leg["id"], recommendation_product_id=leg["recommendation_product_id"],
                    status="skipped_unsupported_market", error=str(exc),
                )
            )
            continue
        except CandidateDirectionError as exc:
            leg_results.append(
                LegGradingResult(
                    leg_id=leg["id"], recommendation_product_id=leg["recommendation_product_id"], status="failed", error=str(exc)
                )
            )
            continue

        status, _ = await persist_leg_grade(
            client,
            headers,
            recommendation_leg_id=leg["id"],
            game_id=game_id,
            grading_version=grading_version,
            outcome=result.outcome,
            authoritative_result=result.authoritative_result,
        )
        leg_results.append(
            LegGradingResult(
                leg_id=leg["id"], recommendation_product_id=leg["recommendation_product_id"], status=status, outcome=result.outcome
            )
        )
        touched_product_ids.add(leg["recommendation_product_id"])

    product_results: list[ProductGradingResult] = []
    for product_id in touched_product_ids:
        rollup = await _maybe_rollup_product(client, headers, recommendation_product_id=product_id, grading_version=grading_version)
        if rollup is not None:
            product_results.append(rollup)

    return GameGradingResult(game_id=game_id, status="graded", legs=leg_results, no_bet_products=no_bet_results, products=product_results)


async def grade_pending_bankroll_preservation_products(
    client: httpx.AsyncClient, headers: dict, *, grading_version: str = GRADING_VERSION
) -> list[ProductGradingResult]:
    """Grades every `bankroll_preservation` product NOT_APPLICABLE
    (Decision BM) -- unconditional, no game-data dependency at all, so
    this never gates on reconciliation-eligibility the way leg grading
    does."""
    product_ids = await read_ungraded_bankroll_preservation_product_ids(client, headers)
    results = []
    for product_id in product_ids:
        status, event_id = await persist_product_grade(
            client,
            headers,
            recommendation_product_id=product_id,
            grading_version=grading_version,
            outcome="NOT_APPLICABLE",
            leg_outcome_counts=None,
            correction_source=None,
        )
        results.append(ProductGradingResult(product_id=product_id, status=status, outcome="NOT_APPLICABLE", grade_event_id=event_id))
    return results
