"""Deterministic market/line-movement feature extraction (Milestone 4.5,
Decisions on Vegas Line / Closing Line Movement Agents). Pure functions
only -- no I/O, mirroring `app.features.travel`'s separation of
computation from persistence.

**CONFIRMED FROM THE ACTUAL PRODUCTION ADAPTER, not the friendlier demo
fixture shape.** `odds_snapshots.line_data` as written by the real
`TheOddsApiOddsAdapter` (`apps/sports-intel-layer/app/adapters/providers/
the_odds_api.py`) is `{"outcomes": [...]}` -- The Odds API v4's own raw
array of `{"name": ..., "price": ..., "point": ...}`, one entry per side
(team name for moneyline/spread, `"Over"`/`"Under"` for totals). The
`{"home": -120, "away": 100}` shape that appears in
`apps/sports-intel-layer/app/demo/starter_data.py` and the demo scenario
JSON files is a **demo-only convenience shape that never reaches
production** -- building against it here would mean the Vegas Line /
Closing Line Movement Agents silently see zero real data in production
while every test looked green. This module works only against the real
`{"outcomes": [...]}` shape.

Movement requires at least two snapshots of the *same* `(sportsbook,
market_type)` pair, ordered by `captured_at`. A single snapshot has a
`latest_price`/`latest_point` (an actual current fact) but produces
`price_movement`/`point_movement`/`direction` of `None` with
`insufficient_history=True` -- never a fabricated `0` movement, per Mac's
explicit instruction.

**No multi-sportsbook consensus math is performed here, deliberately**
(Mac's instruction: "Do not implement multi-book synthetic consensus math
during 4.5"). Each `(sportsbook, market_type, side)` combination gets its
own independent `LineMovementFeatures` entry -- the agent reasons over
each book's real observations directly.

**"Closing line" terminology is deliberately avoided in this module.**
There is currently no reliable signal in this architecture for "this was
the last snapshot before the market closed" -- the Odds Worker's cadence
(Phase 3E-4) is adaptive/window-aware, not close-triggered. Every field
here is named `latest_*`, never `closing_*`, so nothing downstream can
mistake "the most recent observation we happen to have" for a confirmed
close. `app.agents.closing_line_movement.ClosingLineMovementAgent` carries
this same distinction explicitly into its evidence.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineMovementFeatures:
    sportsbook: str
    market_type: str
    side: str
    opening_price: float | None
    latest_price: float | None
    price_movement: float | None
    opening_point: float | None
    latest_point: float | None
    point_movement: float | None
    direction: str | None  # "up" | "down" | None (None if no movement or unknown)
    sample_count: int
    insufficient_history: bool


def parse_outcomes(line_data: dict | None) -> dict[str, dict]:
    """Extracts `{side_name: {"price": ..., "point": ...}}` from one
    snapshot's raw `line_data`. Returns `{}` for a missing/malformed
    `outcomes` array rather than raising -- one malformed snapshot must
    not take down movement computation for the rest (same per-row
    isolation discipline as every Phase 3 ingestion module)."""
    if not isinstance(line_data, dict):
        return {}
    outcomes = line_data.get("outcomes")
    if not isinstance(outcomes, list):
        return {}
    result: dict[str, dict] = {}
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        name = outcome.get("name")
        if name is None:
            continue
        result[name] = {"price": outcome.get("price"), "point": outcome.get("point")}
    return result


def _group_by_book_and_market(snapshots: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Groups already chronologically-ordered snapshots by
    `(sportsbook, market_type)`, preserving each group's relative order
    (Python dicts/lists preserve insertion order) -- no re-sorting is
    performed here, so callers must pass snapshots already ordered by
    `captured_at` ascending (as `app.persistence.odds_snapshots.
    read_odds_snapshots` returns them)."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in snapshots:
        key = (row["sportsbook"], row["market_type"])
        groups.setdefault(key, []).append(row)
    return groups


def _compute_group_movement(ordered_snapshots: list[dict]) -> list[LineMovementFeatures]:
    """One group's (sportsbook, market_type) movement, one
    `LineMovementFeatures` per distinct side found in the most recent
    snapshot."""
    if not ordered_snapshots:
        return []
    sportsbook = ordered_snapshots[0]["sportsbook"]
    market_type = ordered_snapshots[0]["market_type"]
    sample_count = len(ordered_snapshots)
    insufficient = sample_count < 2

    latest_outcomes = parse_outcomes(ordered_snapshots[-1].get("line_data"))
    first_outcomes = parse_outcomes(ordered_snapshots[0].get("line_data"))

    features: list[LineMovementFeatures] = []
    for side, latest in latest_outcomes.items():
        first = None if insufficient else first_outcomes.get(side)

        price_movement = None
        if first is not None and first.get("price") is not None and latest.get("price") is not None:
            price_movement = latest["price"] - first["price"]

        point_movement = None
        if first is not None and first.get("point") is not None and latest.get("point") is not None:
            point_movement = latest["point"] - first["point"]

        primary_movement = point_movement if point_movement is not None else price_movement
        direction = None
        if primary_movement is not None and primary_movement != 0:
            direction = "up" if primary_movement > 0 else "down"

        features.append(
            LineMovementFeatures(
                sportsbook=sportsbook,
                market_type=market_type,
                side=side,
                opening_price=first.get("price") if first is not None else None,
                latest_price=latest.get("price"),
                price_movement=price_movement,
                opening_point=first.get("point") if first is not None else None,
                latest_point=latest.get("point"),
                point_movement=point_movement,
                direction=direction,
                sample_count=sample_count,
                insufficient_history=insufficient,
            )
        )
    return features


def compute_line_movement(snapshots: list[dict]) -> list[LineMovementFeatures]:
    """`snapshots` is every `odds_snapshots` row for one game, ordered by
    `captured_at` ascending (mixed sportsbooks/market_types), exactly as
    `app.persistence.odds_snapshots.read_odds_snapshots` returns them.
    Groups by `(sportsbook, market_type)` first, then computes movement
    independently per group -- no cross-book blending. Returns `[]` for
    an empty input."""
    features: list[LineMovementFeatures] = []
    for group_rows in _group_by_book_and_market(snapshots).values():
        features.extend(_compute_group_movement(group_rows))
    return features
