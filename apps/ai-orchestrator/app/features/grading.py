"""Milestone 5.4's deterministic grading engine (Decisions BI/BJ) --
decides WIN/LOSS/PUSH/VOID_NO_ACTION/PENDING_MISSING_DATA for one already
-frozen leg (`market_type`/`selection`/`point`, `recommendation_legs`'
own bet-defining fields -- immutable by construction, see the Milestone
5.4 migration's own docstring) against the game's authoritative final
facts. No LLM call, no persistence, no I/O of any kind lives here --
pure functions only, exactly like `app.features.consensus`/`app.features.
strategy` before it, so grading logic can be unit-tested without a
database or a model adapter.

**Reuses `resolve_candidate_direction`'s own home/away/over/under
resolution** (`app.features.consensus`, Milestone 4.7) rather than
reimplementing selection-matching -- a moneyline/spread candidate's
`selection` is already required to equal `games.home_team`/`away_team`
verbatim (Decision I's own established rule); grading piggybacks on that
exact same matching rule instead of inventing a second one.

**`market_type == "prop"` is deliberately unsupported, not degraded**
(Decision BJ: "do NOT pretend player props are operational... keep prop
grading structurally extensible but inactive... do not fabricate prop
settlement"). `grade_leg` raises `MarketGradingUnsupportedError` for it --
the orchestration layer (Milestone 5.4's worker) catches this and skips
the leg entirely, writing no grade event at all, rather than persisting
a wrong or fabricated outcome. The `market_type` branch already exists in
`grade_leg`'s own dispatch, so wiring up real prop grading later needs no
structural change here, only a new branch's implementation.

**Moneyline tie -> PUSH**, not WIN/LOSS: a genuine final-score tie (rare
but real, e.g. NFL regular-season overtime ties) is a standard,
industry-wide sportsbook moneyline push rule, not an invented one --
included here rather than left as an unhandled case that would otherwise
silently mis-grade under WIN/LOSS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.features.consensus import CandidateDirectionError, resolve_candidate_direction

GRADING_VERSION = "v1"

LEG_OUTCOMES = ("WIN", "LOSS", "PUSH", "VOID_NO_ACTION", "PENDING_MISSING_DATA")
PRODUCT_OUTCOMES = LEG_OUTCOMES + ("NOT_APPLICABLE", "MIXED_SETTLED")

_VOID_GAME_STATUSES = ("postponed", "canceled")


class MarketGradingUnsupportedError(Exception):
    """Raised by `grade_leg` for a `market_type` this engine cannot yet
    grade (currently: `"prop"`). Never caught and converted into a
    fabricated outcome -- the caller must skip the leg."""


@dataclass(frozen=True)
class LegGradeResult:
    outcome: str  # one of LEG_OUTCOMES
    authoritative_result: dict[str, Any]  # frozen copy of the facts graded against


def grade_leg(
    *,
    market_type: str,
    selection: str,
    point: float | None,
    home_team: str,
    away_team: str,
    game_status: str,
    final_score: dict[str, float] | None,
) -> LegGradeResult:
    """Grades one leg. `game_status`/`final_score` are the game's
    CURRENT values at call time -- the caller (the grading worker) is
    responsible for only calling this once `is_reconciliation_complete`
    is true for that game (Decision BH); this function itself has no
    opinion on timing, it only grades whatever facts it's handed and
    freezes them into the returned `authoritative_result`.

    Raises `MarketGradingUnsupportedError` for `market_type == "prop"`.
    Raises `CandidateDirectionError` (from `app.features.consensus`) if
    `selection` doesn't match `home_team`/`away_team` for a moneyline/
    spread candidate, or isn't `"Over"`/`"Under"` for a total -- a
    malformed leg is a real bug, never silently graded as pending.
    """
    if market_type == "prop":
        raise MarketGradingUnsupportedError(
            "player_prop grading is not yet implemented (Decision BJ) -- leg must be skipped, not graded"
        )

    if game_status in _VOID_GAME_STATUSES:
        return LegGradeResult(outcome="VOID_NO_ACTION", authoritative_result={"game_status": game_status})

    if final_score is None or final_score.get("home") is None or final_score.get("away") is None:
        return LegGradeResult(outcome="PENDING_MISSING_DATA", authoritative_result={"game_status": game_status, "final_score": final_score})

    home_score = float(final_score["home"])
    away_score = float(final_score["away"])
    authoritative_result = {"game_status": game_status, "final_score": {"home": home_score, "away": away_score}}

    if market_type == "moneyline":
        direction = resolve_candidate_direction(
            market_type=market_type, selection=selection, home_team=home_team, away_team=away_team
        )
        if home_score == away_score:
            return LegGradeResult(outcome="PUSH", authoritative_result=authoritative_result)
        winner = "home" if home_score > away_score else "away"
        outcome = "WIN" if direction == winner else "LOSS"
        return LegGradeResult(outcome=outcome, authoritative_result=authoritative_result)

    if market_type == "spread":
        if point is None:
            raise CandidateDirectionError("spread candidate has no point -- cannot grade")
        direction = resolve_candidate_direction(
            market_type=market_type, selection=selection, home_team=home_team, away_team=away_team
        )
        own_score, opponent_score = (home_score, away_score) if direction == "home" else (away_score, home_score)
        adjusted = own_score + point
        if adjusted == opponent_score:
            outcome = "PUSH"
        elif adjusted > opponent_score:
            outcome = "WIN"
        else:
            outcome = "LOSS"
        return LegGradeResult(outcome=outcome, authoritative_result=authoritative_result)

    if market_type == "total":
        if point is None:
            raise CandidateDirectionError("total candidate has no point -- cannot grade")
        direction = resolve_candidate_direction(
            market_type=market_type, selection=selection, home_team=home_team, away_team=away_team
        )
        total_points = home_score + away_score
        if total_points == point:
            outcome = "PUSH"
        elif direction == "over":
            outcome = "WIN" if total_points > point else "LOSS"
        else:  # "under"
            outcome = "WIN" if total_points < point else "LOSS"
        return LegGradeResult(outcome=outcome, authoritative_result=authoritative_result)

    raise MarketGradingUnsupportedError(f"unrecognized market_type={market_type!r}")


def rollup_product_outcome(*, recommendation_type: str, leg_outcomes: list[str]) -> tuple[str, dict[str, int] | None]:
    """Derives a product-level `(outcome, leg_outcome_counts)` pair from
    already-graded leg outcomes (Decisions BK/BL/BM). Never called for a
    `no_bet`/`bankroll_preservation` product -- those are NOT_APPLICABLE
    by construction, decided by the caller before this function is
    reached (there are no legs to look at for either).

    `single`: exactly one leg -- the product mirrors that leg's own
    outcome verbatim, `leg_outcome_counts=None` (a count of one thing
    tells you nothing a plain outcome doesn't already say).

    `multiple_singles`: PENDING_MISSING_DATA while ANY leg lacks a
    terminal grade (WIN/LOSS/PUSH/VOID_NO_ACTION are all terminal;
    PENDING_MISSING_DATA is not) -- never a partial/premature rollup
    (Decision BK: "Do not prematurely assign a product-level result").
    Once every leg is terminal, `MIXED_SETTLED` with the full breakdown
    in `leg_outcome_counts` -- the rollup never collapses or discards
    which legs won/lost/pushed/voided.
    """
    if recommendation_type == "single":
        if len(leg_outcomes) != 1:
            raise ValueError(f"single product must have exactly one leg outcome, got {len(leg_outcomes)}")
        return leg_outcomes[0], None

    if recommendation_type == "multiple_singles":
        if not leg_outcomes:
            raise ValueError("multiple_singles product has no leg outcomes to roll up")
        terminal = {"WIN", "LOSS", "PUSH", "VOID_NO_ACTION"}
        if any(outcome not in terminal for outcome in leg_outcomes):
            return "PENDING_MISSING_DATA", None
        counts: dict[str, int] = {}
        for outcome in leg_outcomes:
            counts[outcome] = counts.get(outcome, 0) + 1
        return "MIXED_SETTLED", counts

    raise ValueError(f"rollup_product_outcome does not apply to recommendation_type={recommendation_type!r}")
