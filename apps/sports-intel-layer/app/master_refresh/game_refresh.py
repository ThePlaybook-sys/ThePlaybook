"""Per-game daily_game_intelligence assembly/refresh (Phase 3E-2, extracted
Phase 3E-8 Decision 4).

**Extracted from `app.master_refresh.run.run_master_refresh`'s own
per-game loop, not rewritten -- identical async-call sequence, behavior
unchanged for Master Refresh's own daily callers.** Phase 3E-8's Pregame
Worker needs the exact same "read whatever odds/props/injuries/weather/
news/rest currently holds and upsert one daily_game_intelligence row"
behavior Master Refresh already had, but for a single targeted game
immediately after a T-minus-5-minute refresh, not once daily for the
whole slate -- Decision 4's explicit instruction was to "reuse the
existing scoped daily_game_intelligence assembly/update behavior wherever
possible" rather than build a second, competing assembly path.

**`rosters` is optional, unlike Master Refresh's own call site.** Master
Refresh always has a freshly-fetched `rosters` dict (it just fetched every
team's roster this run) and passes it through. Pregame Worker does not
fetch rosters at all (out of Decision 3's explicit worker list -- Roster/
`players` composition doesn't change in the final 5 minutes before
kickoff, so there's nothing new to refresh there) -- when `rosters` is
omitted, this function reads back whatever `daily_game_intelligence.
players` already holds via `read_existing_players` and preserves it
verbatim, the same pattern `existing_news`/`read_existing_news` already
established for the identical "not this call's field to own" situation.
Since Master Refresh already wrote the internal `player_id` enrichment
below into that same row, the read-back passthrough carries it forward
automatically -- Pregame Worker needs no separate identity resolution.

**`player_ids` (Phase 3F-4): minimal reconciliation, not a durable-table
read path.** `daily_game_intelligence.players` stays the fresh
roster-fetch passthrough (Decision, 3F-4 report) -- this is *not* a
rebuild from `players`/`roster_memberships`/`depth_chart_snapshots`.
The one real gap those 3F-1 tables closed that the raw fetch alone
can't -- a stable internal `players.id` for joining to `player_stats`/
future postgame or recommendation systems -- is added by looking up each
entry's already-known `player_external_id` in a `player_id` mapping the
caller resolves once, batched, via `player_identity.resolve_player_ids`
(Master Refresh does this once for the whole slate, not per-team/
per-game -- see `run.py`). A player absent from the mapping (never
durably ingested yet, or this cycle's `persist_roster` failed before
reaching them) gets `player_id: None` -- never fabricated, never
name-matched. This is a deliberate, honest signal: the roster/depth-chart
*content* shown is still the freshest available data even when identity
resolution lags, but the internal identity link is only ever present when
truly confirmed."""
from __future__ import annotations

from datetime import datetime

import httpx

from app.adapters.models import RosterEntry
from app.master_refresh.rest import compute_rest
from app.persistence.daily_game_intelligence import (
    DailyGameIntelligenceError,
    build_payload,
    read_existing_news,
    read_existing_players,
    upsert_daily_game_intelligence,
)
from app.persistence.games import find_previous_final_game
from app.persistence.snapshots import latest_injury_report, latest_odds_line, latest_prop_line, latest_weather_snapshot


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _enrich_roster(roster: list[RosterEntry], player_ids: dict[str, str]) -> list[dict]:
    """Phase 3F-4: adds the resolved internal `players.id` alongside every
    field the raw roster fetch already exposed (team/player_external_id/
    player_name/position/depth_chart_rank) -- unchanged, not redesigned.
    `player_ids` maps `player_external_id` -> internal `players.id` (see
    `player_identity.resolve_player_ids`); an entry absent from it gets
    `player_id: None`, never fabricated, never guessed by name."""
    return [
        {**entry.model_dump(mode="json"), "player_id": player_ids.get(entry.player_external_id)}
        for entry in roster
    ]


def _build_stadium(game: dict) -> dict | None:
    """Phase 3F-3: surfaces `games.venue_lat`/`.venue_long`/`.venue_type`
    (stored since 3E-6, never previously read back into
    `daily_game_intelligence.stadium`) alongside the existing `.stadium`
    name. Current-state only -- these are `games` columns, overwritten in
    place by whatever the Schedule adapter last reported, not a
    historical venue system. A field genuinely unknown stays `None`
    (never fabricated); the whole object collapses to `None` only when
    literally nothing about the venue is known, matching every other
    category's "no data at all -> None" convention elsewhere in this
    payload (odds/props/injuries/weather)."""
    name = game.get("stadium")
    lat = game.get("venue_lat")
    lon = game.get("venue_long")
    venue_type = game.get("venue_type")
    if name is None and lat is None and lon is None and venue_type is None:
        return None
    return {"name": name, "latitude": lat, "longitude": lon, "venue_type": venue_type}


async def refresh_daily_game_intelligence_for_game(
    client: httpx.AsyncClient,
    headers: dict,
    game: dict,
    *,
    rosters: dict[str, list[RosterEntry] | None] | None = None,
    player_ids: dict[str, str] | None = None,
) -> None:
    """Reads back the currently-persisted odds/props/injuries/weather/news
    for `game`, recomputes `rest`, and upserts the resulting
    daily_game_intelligence row. Raises GamesQueryError/
    DailyGameIntelligenceError on failure -- callers decide isolation
    (Master Refresh isolates per-game already; Pregame Worker does the
    same around its own single call)."""
    game_id = game["id"]
    scheduled_start = _parse_datetime(game["scheduled_start"])

    home_previous = await find_previous_final_game(client, headers, team=game["home_team"], before=scheduled_start)
    away_previous = await find_previous_final_game(client, headers, team=game["away_team"], before=scheduled_start)
    rest = {
        "home": compute_rest(current_scheduled_start=scheduled_start, previous_game=home_previous),
        "away": compute_rest(current_scheduled_start=scheduled_start, previous_game=away_previous),
    }

    odds_row = await latest_odds_line(client, headers, game_id=game_id)
    props_row = await latest_prop_line(client, headers, game_id=game_id)
    injury_row = await latest_injury_report(client, headers, game_id=game_id)
    weather_row = await latest_weather_snapshot(client, headers, game_id=game_id)
    existing_news = await read_existing_news(client, headers, game_id=game_id)

    if rosters is not None:
        home_roster = rosters.get(game["home_team"])
        away_roster = rosters.get(game["away_team"])
        players = None
        if home_roster is not None or away_roster is not None:
            ids = player_ids or {}
            players = {
                "home": _enrich_roster(home_roster, ids) if home_roster is not None else None,
                "away": _enrich_roster(away_roster, ids) if away_roster is not None else None,
            }
    else:
        players = await read_existing_players(client, headers, game_id=game_id)

    payload = build_payload(
        game_id=game_id,
        teams={"home": game["home_team"], "away": game["away_team"]},
        players=players,
        odds_row=odds_row,
        props_row=props_row,
        injury_row=injury_row,
        weather_row=weather_row,
        existing_news=existing_news,
        rest=rest,
        stadium=_build_stadium(game),
    )
    await upsert_daily_game_intelligence(client, headers, payload)
