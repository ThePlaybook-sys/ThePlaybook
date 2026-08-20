"""Assembles and upserts `daily_game_intelligence` working rows (Volume 3
§4.1, Phase 3E-2).

**Field ownership is the load-bearing decision in this module, not an
implementation detail.** The upsert payload only ever includes the fields
Master Refresh actually owns or has an honest answer for:

    game_id, teams, players, odds, props, weather, injuries, news,
    rest, stadium, travel, public_betting, sharp_money, last_updated

`ai_scores`/`momentum`/`matchup_ratings`/`ev_calculations`/
`confidence_scores`/`recommendation_candidates` are Phase 4/5 outputs
(Volume 4 territory) and are **deliberately never included in the
payload at all** -- not written as null, omitted entirely. PostgREST's
`resolution=merge-duplicates` upsert only touches columns present in the
request body: omitting these means a fresh row gets their SQL column
default (NULL, i.e. "not produced yet") and an existing row's values
(once a later phase starts writing them) are never clobbered by this
worker's daily run. Writing them as an explicit `null` would have been
wrong in a different way -- it would silently erase real Phase 4/5 data
on every Master Refresh run once that data starts existing.

`public_betting`/`sharp_money`, by contrast, ARE part of Master Refresh's
own assembled field set (Decision 3, 2026-08-13) -- they're written as an
explicit `null`, asserting "checked, unavailable" rather than "not our
column."

**A real gap surfaced while building this, flagged rather than papered
over:** none of `odds_snapshots`/`injury_reports`/`weather_snapshots`
persist which adapter/provider produced the row (no `provider_name`
column exists on any of them, confirmed by direct inspection of the
Phase 1 migration). `AdapterResponse.source` exists at the adapter layer
but was never threaded through to persistence. This module falls back to
Volume 2 §8's *default-vendor* table (Odds/Props -> the_odds_api,
Injuries -> sportsdataio, Weather -> weatherapi) for the `source` field in
each category's metadata object -- an inferred default, not a value
actually read back from the row. Flagged as a follow-up: these snapshot
tables arguably need their own `provider_name` column.

**`confidence` is deliberately omitted from every metadata object.**
`AdapterResponse`'s own docstring already establishes that Playbook
confidence is a downstream-derived value Phase 3 has no basis to compute
-- Master Refresh follows that same discipline rather than fabricating a
number here.

**`status` (freshness)** is computed from each snapshot's `captured_at`
against `CATEGORY_TTL_SECONDS` (Phase 3D): `fresh` within one TTL window,
`needs_refresh` within three, `stale` beyond -- an ASSUMED threshold
multiplier, same provenance tier as `CATEGORY_TTL_SECONDS` itself. No
snapshot at all means no metadata object -- never a fabricated status.

**`odds` vs. `props`:** both live in the same `odds_snapshots` table,
distinguished only by `market_type` (`OddsLine.market_type` docstring:
"'moneyline' | 'spread' | 'total' | 'prop'"). This module reads the
latest row for each set separately (`market_type != 'prop'` for odds,
`market_type = 'prop'` for props). Each is a **single most-recent row**,
not a full multi-sportsbook board -- a known simplification (there is no
Odds Worker yet to have written more than one), flagged rather than
presented as complete.

**`news`** has no snapshot table (see `app/persistence/snapshots.py`;
Phase 3E-7, Mac's approved Option A -- the smallest additive move,
persistence history for News remains deferred, unaffected by this note).
Master Refresh itself still has no fresher source to offer and still only
ever reads back whatever `news` already holds (`read_existing_news`
below, unchanged) -- but as of 3E-7 that value is no longer always
whatever a prior run's placeholder was: `app.workers.news_worker` now
writes current-state news directly into this same column via `write_news`
below, on its own 15-minute cadence, entirely independent of Master
Refresh's daily run. `write_news` PATCHes/upserts only the `game_id` and
`news` columns (same `resolution=merge-duplicates`, columns-present-only
semantics as `upsert_daily_game_intelligence`) -- it never touches odds/
weather/injuries/etc., matching the same field-ownership discipline this
whole module is built around. A News provider failure or an unresolved
team for a given cycle means `write_news` is simply not called for that
game this cycle -- whatever `news` already held stays exactly as it was,
never overwritten with an empty/neutral value (see `news_worker.py`'s own
docstring for the full failure/stale-data reasoning).

**`travel`** is always written as `None` for 3E-2 (Decision 3) -- durable
venue coordinates aren't modeled yet (flagged as a follow-up architecture
item, not built here).
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.adapters.cache import CATEGORY_TTL_SECONDS

#: Volume 2 §8's named default vendor per category -- used only as the
#: `source` label in assembled metadata, since the snapshot tables
#: themselves carry no provider attribution (see module docstring).
#: Keyed identically to `CATEGORY_TTL_SECONDS` -- both are looked up by the
#: same `category` argument in `_metadata` below, so they must agree on
#: the normalized category name (`app.adapters.models.DataCategory.
#: PLAYER_PROPS` is `"player_props"`, never the bare `"props"` this dict
#: and `build_payload`'s own `category="props"` call site both used to say
#: -- a pre-existing bug, confirmed 2026-08-20 to have never been
#: exercised by any prior test: `_freshness_status` raised `KeyError:
#: 'props'` the first time this module's props branch ever ran against a
#: real (non-null) `props_row`, which happened only once DEMO-3's
#: scenario-runner integration test drove the full Pregame Worker ->
#: targeted daily_game_intelligence refresh path end to end).
_DEFAULT_VENDOR = {
    "odds": "the_odds_api",
    "player_props": "the_odds_api",
    "injuries": "sportsdataio",
    "weather": "weatherapi",
}


class DailyGameIntelligenceError(Exception):
    """Raised when a `daily_game_intelligence` read or write fails on
    Supabase's side."""


def _freshness_status(captured_at: str, *, category: str, now: datetime) -> str:
    ttl = CATEGORY_TTL_SECONDS[category]
    captured = captured_at
    if isinstance(captured, str):
        captured = datetime.fromisoformat(captured.replace("Z", "+00:00"))
    age_seconds = (now - captured).total_seconds()
    if age_seconds <= ttl:
        return "fresh"
    if age_seconds <= ttl * 3:
        return "needs_refresh"
    return "stale"


def _metadata(value: dict, *, category: str, captured_at: str, now: datetime) -> dict:
    return {
        "value": value,
        "source": _DEFAULT_VENDOR[category],
        "last_updated": captured_at,
        "status": _freshness_status(captured_at, category=category, now=now),
    }


async def read_existing_news(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> object:
    """Preserves whatever `news` already holds -- see module docstring's
    explanation of why there's no fresher source to read from yet."""
    response = await client.get(
        "/rest/v1/daily_game_intelligence",
        params={"game_id": f"eq.{game_id}", "select": "news"},
        headers=headers,
    )
    if response.status_code != 200:
        raise DailyGameIntelligenceError(
            f"failed to read existing news for game {game_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0]["news"] if rows else None


async def read_existing_players(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> object:
    """Preserves whatever `players` already holds -- Phase 3E-8's targeted
    Pregame refresh (`app.master_refresh.game_refresh.
    refresh_daily_game_intelligence_for_game`) doesn't re-fetch rosters
    (out of scope for a T-minus-5-minute odds/props/injury/weather refresh
    -- roster composition doesn't change in the final 5 minutes before
    kickoff), so it reads this back and passes it through verbatim, exactly
    mirroring `read_existing_news`'s identical reasoning for a field this
    call doesn't own refreshing."""
    response = await client.get(
        "/rest/v1/daily_game_intelligence",
        params={"game_id": f"eq.{game_id}", "select": "players"},
        headers=headers,
    )
    if response.status_code != 200:
        raise DailyGameIntelligenceError(
            f"failed to read existing players for game {game_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0]["players"] if rows else None


def build_payload(
    *,
    game_id: str,
    teams: dict,
    players: dict | None,
    odds_row: dict | None,
    props_row: dict | None,
    injury_row: dict | None,
    weather_row: dict | None,
    existing_news: object,
    rest: dict,
    stadium: dict | None,
    now: datetime | None = None,
) -> dict:
    """Pure assembly: builds the upsert payload from already-fetched
    inputs. Kept separate from the DB-write step below so field-ownership
    behavior is directly unit-testable without mocking HTTP."""
    now = now or datetime.now(timezone.utc)

    payload: dict = {
        "game_id": game_id,
        "teams": teams,
        "players": players,
        "odds": (
            _metadata(
                {"sportsbook": odds_row["sportsbook"], "market_type": odds_row["market_type"], "line_data": odds_row["line_data"]},
                category="odds",
                captured_at=odds_row["captured_at"],
                now=now,
            )
            if odds_row
            else None
        ),
        "props": (
            _metadata(
                {"sportsbook": props_row["sportsbook"], "market_type": props_row["market_type"], "line_data": props_row["line_data"]},
                category="player_props",
                captured_at=props_row["captured_at"],
                now=now,
            )
            if props_row
            else None
        ),
        "injuries": (
            _metadata(injury_row["report_data"], category="injuries", captured_at=injury_row["captured_at"], now=now)
            if injury_row
            else None
        ),
        "weather": (
            _metadata(weather_row["weather_data"], category="weather", captured_at=weather_row["captured_at"], now=now)
            if weather_row
            else None
        ),
        "news": existing_news,
        "travel": None,
        "rest": rest,
        "stadium": stadium,
        "public_betting": None,
        "sharp_money": None,
        "last_updated": now.isoformat(),
    }
    return payload


async def write_news(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    articles: list[dict],
    source: str,
    now: datetime,
) -> None:
    """Writes current-state news for one game (Phase 3E-7, News Worker's
    own write path) -- scoped to exactly `game_id` and `news`, via the same
    `on_conflict=game_id` / `resolution=merge-duplicates` upsert idiom
    `upsert_daily_game_intelligence` below uses, so a fresh row (no Master
    Refresh assembly has run for this game yet) is created with every
    other column left at its SQL default, and an existing row's other
    columns are left completely untouched -- never clobbered by this
    narrower, News-only write. `articles` is already the
    already-JSON-serializable article list (callers pass
    `NewsArticle.model_dump(mode="json")` output); this function doesn't
    know or care about the `NewsArticle` model itself, keeping it
    consistent with this module's existing pattern of taking already-shaped
    dicts (`odds_row`, `weather_row`, etc. above) rather than importing
    adapter models.

    `status` is always written as `"fresh"` -- correct at the instant of
    writing (age zero, matching `CATEGORY_TTL_SECONDS["news"]`'s definition
    of freshness), and, same as the metadata objects `build_payload`
    assembles above, is never recomputed on read. This is not a new gap:
    it's the identical characteristic `existing_news`'s pass-through
    already had before this function existed, just now applied to a value
    this module itself produces instead of one it merely forwards.
    """
    payload = {
        "game_id": game_id,
        "news": {
            "value": articles,
            "source": source,
            "last_updated": now.isoformat(),
            "status": "fresh",
        },
    }
    response = await client.post(
        "/rest/v1/daily_game_intelligence",
        params={"on_conflict": "game_id"},
        json=payload,
        headers={**headers, "Prefer": "resolution=merge-duplicates"},
    )
    if response.status_code not in (200, 201, 204):
        raise DailyGameIntelligenceError(
            f"failed to write news for game {game_id}: "
            f"{response.status_code} {response.text}"
        )


async def upsert_daily_game_intelligence(client: httpx.AsyncClient, headers: dict, payload: dict) -> None:
    response = await client.post(
        "/rest/v1/daily_game_intelligence",
        params={"on_conflict": "game_id"},
        json=payload,
        headers={**headers, "Prefer": "resolution=merge-duplicates"},
    )
    if response.status_code not in (200, 201, 204):
        raise DailyGameIntelligenceError(
            f"failed to upsert daily_game_intelligence for game "
            f"{payload['game_id']}: {response.status_code} {response.text}"
        )
