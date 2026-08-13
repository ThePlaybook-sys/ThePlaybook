"""REST computation (Volume 3 §4.1 `daily_game_intelligence.rest`,
Phase 3E-2, Decision 2, 2026-08-13).

Semantic definition, exactly as approved -- not invented here, restated
so the code and the decision stay in sync:

    rest_days = days since the team's most recent status='final' game
    before this game's scheduled_start.

Only a 'final' game counts as "the previous game" -- a still-scheduled,
canceled, or never-finalized postponed game is not a played game and must
not be used. UTC calendar dates for this initial implementation (Mac's
explicit simplification, matching the same choice already made for slate
windowing).

No bye-week flag: per Mac's explicit instruction, the elevated rest_days
number itself is sufficient for 3E-2 -- no separate `is_bye_week_return`
field is added. A season opener (no previous final game at all) is
`rest_days: None` + `season_opener: True`, never a fabricated 0 or 7 --
this is the same null-not-neutral principle already established for
public_betting/sharp_money (Decision 3).
"""
from __future__ import annotations

from datetime import datetime


def compute_rest(*, current_scheduled_start: datetime, previous_game: dict | None) -> dict:
    """Pure function: `previous_game` is the dict returned by
    `app.persistence.games.find_previous_final_game` (or None). Returns
    the `rest` payload for `daily_game_intelligence`.
    """
    if previous_game is None:
        return {"rest_days": None, "season_opener": True}

    previous_start = previous_game["scheduled_start"]
    if isinstance(previous_start, str):
        previous_start = datetime.fromisoformat(previous_start.replace("Z", "+00:00"))

    rest_days = (current_scheduled_start.date() - previous_start.date()).days
    return {"rest_days": rest_days, "season_opener": False}
