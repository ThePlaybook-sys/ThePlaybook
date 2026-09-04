"""Milestone 7.1 read/write access for the deterministic Unexplained-
Movement Detection Engine. Mirrors this package's existing
`odds_snapshots.py`/`postgame_grading.py` convention exactly: injected
`httpx.AsyncClient` + headers, no self-contained client construction,
raised exceptions rather than swallowed failures.

Reads four explanatory-evidence sources -- the exact list Milestone 7.0's
own audit confirmed as real, timestamped, and comparable to
`odds_snapshots.captured_at`, plus the one gap that audit found (News)
now closed by the Pre-9/9 Data Preservation pass (`news_article_history`,
Volume 3 §4.4, v4.26):

- `injury_reports`/`weather_snapshots` -- `game_id`-scoped directly,
  same shape as `odds_snapshots` (Volume 3 §4).
- `depth_chart_snapshots` -- TEAM-scoped, not game-scoped (Volume 3 §4's
  2026-08-18 redesign). `games.home_team`/`away_team` are plain text
  names (`games` carries no `team_id` FK column at all, confirmed by
  direct migration inspection) -- resolved to `teams.id` by an exact
  `teams.name` match, no fuzzy matching, mirroring `sports-intel-layer`'s
  own `app.persistence.team_identity` "absent means unresolved"
  discipline. An unresolved team name yields no lineup evidence for that
  team, never a fabricated match.
- `news_article_history` -- team/player-scoped via `related_team_ids`/
  `related_player_ids` jsonb array columns, not `game_id`-scoped at all.
  Membership ("does this article concern one of these teams") is
  checked in Python after fetching, not via a jsonb-array PostgREST
  filter -- DEV has zero real rows to validate a `cs.{...}`/`ov.{...}`
  operator against today, and an explicit, readable Python membership
  check is safer than an unverified query-operator guess.

Writes exactly one new table target: `market_monitoring_events`
(Volume 3 §7) -- this milestone's own first real writer for a table
previously confirmed zero rows/zero code (Phase 7 Milestone 7.0's
audit). `action_taken` is always `'none'` here (Milestone 7.0/7.1
decision: no Strategy Engine consumer exists yet to act on a
classification -- that is Milestone 7.2's scope). `affected_
recommendation_ids` is left unset -- the same reason.
"""
from __future__ import annotations

import httpx


class MarketIntegrityReadError(Exception):
    """Raised when an explanatory-evidence read fails on Supabase's side."""


class MarketIntegrityWriteError(Exception):
    """Raised when a `market_monitoring_events` write fails on Supabase's side."""


async def read_injury_reports(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> list[dict]:
    """Every `injury_reports` row for `game_id`, ordered by
    `captured_at` ascending. Returns `[]` when none exist."""
    response = await client.get(
        "/rest/v1/injury_reports",
        params={"game_id": f"eq.{game_id}", "select": "id,captured_at", "order": "captured_at.asc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise MarketIntegrityReadError(
            f"failed to read injury_reports for game_id={game_id!r}: {response.status_code} {response.text}"
        )
    return response.json()


async def read_weather_snapshots(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> list[dict]:
    """Every `weather_snapshots` row for `game_id`, ordered by
    `captured_at` ascending. Returns `[]` when none exist."""
    response = await client.get(
        "/rest/v1/weather_snapshots",
        params={"game_id": f"eq.{game_id}", "select": "id,captured_at", "order": "captured_at.asc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise MarketIntegrityReadError(
            f"failed to read weather_snapshots for game_id={game_id!r}: {response.status_code} {response.text}"
        )
    return response.json()


async def resolve_team_ids_by_name(client: httpx.AsyncClient, headers: dict, *, team_names: list[str]) -> dict[str, str]:
    """Maps `teams.name` -> `teams.id` by exact match, for `team_names`.
    A name with no matching row is simply absent from the returned dict
    -- see module docstring. Returns `{}` for an empty `team_names`
    without making a request."""
    if not team_names:
        return {}
    response = await client.get(
        "/rest/v1/teams",
        params={"name": f"in.({','.join(team_names)})", "select": "id,name"},
        headers=headers,
    )
    if response.status_code != 200:
        raise MarketIntegrityReadError(f"failed to resolve team ids for {team_names!r}: {response.status_code} {response.text}")
    return {row["name"]: row["id"] for row in response.json()}


async def read_depth_chart_snapshots(client: httpx.AsyncClient, headers: dict, *, team_ids: list[str]) -> list[dict]:
    """Every `depth_chart_snapshots` row for any of `team_ids`, ordered
    by `captured_at` ascending. Returns `[]` for an empty `team_ids`
    without making a request -- an all-unresolved-teams game must not
    be treated as an error, only as "no lineup evidence available"."""
    if not team_ids:
        return []
    response = await client.get(
        "/rest/v1/depth_chart_snapshots",
        params={"team_id": f"in.({','.join(team_ids)})", "select": "id,team_id,captured_at", "order": "captured_at.asc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise MarketIntegrityReadError(
            f"failed to read depth_chart_snapshots for team_ids={team_ids!r}: {response.status_code} {response.text}"
        )
    return response.json()


async def read_news_article_history_for_teams(
    client: httpx.AsyncClient, headers: dict, *, team_ids: list[str], since: str | None = None
) -> list[dict]:
    """Reads `news_article_history` rows and filters, in Python (see
    module docstring), to those whose `related_team_ids` array contains
    any of `team_ids`. `since` (an `ingested_at` ISO timestamp) bounds
    the initial fetch so this never scans the whole table as real
    volume accumulates -- optional, since neither a Milestone 7.1
    fixture test nor DEV's current 0-row table has a volume concern
    today. Returns `[]` for an empty `team_ids` without making a
    request."""
    if not team_ids:
        return []
    params: dict[str, str] = {
        "select": "id,provider_name,article_url,published_at,ingested_at,headline,related_team_ids",
        "order": "ingested_at.asc",
    }
    if since is not None:
        params["ingested_at"] = f"gte.{since}"
    response = await client.get("/rest/v1/news_article_history", params=params, headers=headers)
    if response.status_code != 200:
        raise MarketIntegrityReadError(f"failed to read news_article_history: {response.status_code} {response.text}")
    rows = response.json()
    team_id_set = set(team_ids)
    return [row for row in rows if isinstance(row.get("related_team_ids"), list) and team_id_set & set(row["related_team_ids"])]


async def write_market_monitoring_event(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    event_type: str,
    event_data: dict,
) -> str:
    """Inserts one `market_monitoring_events` row for a qualifying
    (WATCH/ELEVATED/SEVERE) classification. `action_taken` is always
    `'none'` and `affected_recommendation_ids` is left unset at this
    milestone (see module docstring). Returns the new row's `id`."""
    payload = {"game_id": game_id, "event_type": event_type, "event_data": event_data, "action_taken": "none"}
    response = await client.post(
        "/rest/v1/market_monitoring_events",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise MarketIntegrityWriteError(f"failed to write market_monitoring_events: {response.status_code} {response.text}")
    return response.json()[0]["id"]
