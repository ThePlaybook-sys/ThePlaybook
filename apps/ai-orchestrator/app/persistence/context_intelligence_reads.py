"""Read-only access for the Phase 8.1 Contextual Intelligence Foundation
Pass (2026-09-08), new and additive -- does not modify or import from
any Phase 4/Milestone 7.1 persistence module, only sits alongside them.
Mirrors this package's own established convention exactly (injected
`httpx.AsyncClient` + headers, no self-contained client construction,
raised exceptions rather than swallowed failures, `[]`/`None` for "really
nothing here" vs. a raised exception for a real read failure).

**Table-wide reads, not per-game.** Unlike `odds_snapshots.py`/
`market_integrity.py`'s per-game readers, this module's job is building
the CROSS-GAME comparable pools this pass's "comparable historical
context" instruction requires -- `read_all_weather_snapshots`/
`read_all_odds_snapshots` fetch every row in the table, matching
`app.persistence.market_integrity.read_news_article_history_for_teams`'s
own established precedent for this project's real current scale (a
handful of real rows per table -- 2026-09-07's Phase 8.0.5 closeout
confirmed 4 real weather rows, 138 odds rows, 97 news rows; fetching all
and filtering/grouping in Python is simple, honest, and correct at this
volume, the same reasoning that precedent's own module docstring already
gives)."""
from __future__ import annotations

import httpx

from app.context_intelligence.player_performance import extract_msf_team_provider_ids


class ContextIntelligenceReadError(Exception):
    """Raised when a context-intelligence read fails on Supabase's side."""


async def read_all_weather_snapshots(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    """Every `weather_snapshots` row in the table (`game_id`,
    `weather_data`, `captured_at`), oldest first. Real scale today: a
    handful of rows (Phase 8.0.5's own live-verified count). Callers are
    responsible for filtering to rows carrying `weather_data.source ==
    "weatherapi"` -- the one real, disclosed marker (Phase 8.0.5 Weather
    Activation) that distinguishes a real captured observation from the
    one pre-existing fixture row, which carries no `source` key at all."""
    response = await client.get(
        "/rest/v1/weather_snapshots",
        params={"select": "game_id,weather_data,captured_at", "order": "captured_at.asc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(f"failed to read weather_snapshots: {response.status_code} {response.text}")
    return response.json()


async def read_all_odds_snapshots(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    """Every `odds_snapshots` row in the table (`game_id`, `sportsbook`,
    `market_type`, `line_data`, `captured_at`), oldest first. Used to
    build the cross-game comparable pool for market-movement similarity
    -- the target game's own history is read via the existing
    `app.persistence.odds_snapshots.read_odds_snapshots` (Milestone 4.5),
    unchanged, not duplicated here."""
    response = await client.get(
        "/rest/v1/odds_snapshots",
        params={"select": "game_id,sportsbook,market_type,line_data,captured_at", "order": "captured_at.asc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(f"failed to read odds_snapshots: {response.status_code} {response.text}")
    return response.json()


async def read_game_venue_context(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> dict | None:
    """Reads the one `games` row this pass's venue dimension needs
    (`id`, `home_team`, `away_team`, `scheduled_start`, `venue_id`,
    `venue_lat`, `venue_long`, `venue_type`, `stadium`). A separate,
    dedicated read rather than widening `app.persistence.games.get_game`
    (Phase 4, Milestone 4.1/4.4, frozen) -- mirrors that same package's
    own `get_game_for_grading` precedent: "grading is a new, unrelated
    consumer with its own field needs," applied identically here. Returns
    `None` when no row exists."""
    response = await client.get(
        "/rest/v1/games",
        params={
            "id": f"eq.{game_id}",
            "select": "id,home_team,away_team,scheduled_start,venue_id,venue_lat,venue_long,venue_type,stadium",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(f"failed to read game {game_id!r}: {response.status_code} {response.text}")
    rows = response.json()
    return rows[0] if rows else None


async def read_venue(client: httpx.AsyncClient, headers: dict, *, venue_id: str) -> dict | None:
    """Reads one canonical `venues` row (sport-agnostic since Phase
    8.0.5 Pass 2 -- reused here with zero redesign, per this pass's own
    multi-sport architecture rule). Returns `None` when no row exists."""
    response = await client.get(
        "/rest/v1/venues",
        params={"id": f"eq.{venue_id}", "select": "id,name,city,state,venue_type"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(f"failed to read venue {venue_id!r}: {response.status_code} {response.text}")
    rows = response.json()
    return rows[0] if rows else None


async def read_all_player_stats(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    """Every `player_stats` row in the table (`id`, `player_id`, `game_id`,
    `stats`, `created_at`) -- real scale as of the Player Performance
    Context Foundation pass (2026-09-15): 1,551 rows, still small enough
    to fetch wholesale and filter/group in Python, matching this module's
    own established "download once" convention at every previous scale
    this project has had. A future pass at materially larger real scale
    (post-Week-1, multi-season) may need a `player_id`-scoped read
    instead -- not needed yet, not built here."""
    response = await client.get(
        "/rest/v1/player_stats",
        params={"select": "id,player_id,game_id,stats,created_at", "order": "created_at.asc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(f"failed to read player_stats: {response.status_code} {response.text}")
    return response.json()


async def read_games_by_ids(client: httpx.AsyncClient, headers: dict, *, game_ids: list[str]) -> dict[str, dict]:
    """Batch `games` read keyed by `id` (`scheduled_start`, `home_team`,
    `away_team`) for exactly the game_ids a caller already knows it needs
    -- the shape `player_performance.py`'s `games_by_id` parameter expects.
    Returns `{}` for an empty `game_ids` without making a request, same
    empty-input discipline as `market_integrity.resolve_team_ids_by_name`."""
    if not game_ids:
        return {}
    response = await client.get(
        "/rest/v1/games",
        params={"id": f"in.({','.join(game_ids)})", "select": "id,scheduled_start,home_team,away_team"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(
            f"failed to read games for game_ids={game_ids!r}: {response.status_code} {response.text}"
        )
    return {row["id"]: row for row in response.json()}


async def read_player_stats_for_player(client: httpx.AsyncClient, headers: dict, *, player_id: str) -> list[dict]:
    """Every `player_stats` row for exactly one `player_id` (`id`,
    `player_id`, `game_id`, `stats`, `created_at`) -- the targeted
    alternative to `read_all_player_stats` used by `engine.py`'s real
    per-player dimension request (Player Performance Engine Integration
    pass, 2026-09-15): fetching one player's own rows instead of the
    whole table is both more efficient and the more natural shape once
    this dimension is reachable via a real `player_id`-scoped API call,
    rather than the standalone module-level testing `read_all_player_
    stats` was built for."""
    response = await client.get(
        "/rest/v1/player_stats",
        params={"player_id": f"eq.{player_id}", "select": "id,player_id,game_id,stats,created_at", "order": "created_at.asc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(
            f"failed to read player_stats for player_id={player_id!r}: {response.status_code} {response.text}"
        )
    return response.json()


async def read_player_identity(client: httpx.AsyncClient, headers: dict, *, player_id: str) -> dict | None:
    """Reads the one real `players` row (`id`, `name`, `position`,
    `team_id`) `player_performance.py` needs for `player_name`/`position`/
    `player_team_id`. Returns `None` when no row exists."""
    response = await client.get(
        "/rest/v1/players",
        params={"id": f"eq.{player_id}", "select": "id,name,position,team_id"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(
            f"failed to read player {player_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def read_game_events_raw_payloads(
    client: httpx.AsyncClient, headers: dict, *, game_ids: list[str], provider_name: str
) -> dict[str, dict]:
    """One real `raw_payload` per `game_id` (the first captured, by
    `captured_at` ascending) for `provider_name` -- team-identity fields
    inside a real MySportsFeeds `game_boxscore` payload are invariant
    across repeat captures of the same game (unlike `player_stats`'
    `snapCounts`, see `observation_identity.py`), so "first found" is a
    correct, simple choice, not a tie-break decision the way
    `resolve_canonical_observation` is for player stats. Returns `{}` for
    an empty `game_ids` without making a request."""
    if not game_ids:
        return {}
    response = await client.get(
        "/rest/v1/game_events",
        params={
            "game_id": f"in.({','.join(game_ids)})",
            "provider_name": f"eq.{provider_name}",
            "select": "game_id,raw_payload",
            "order": "captured_at.asc",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(
            f"failed to read game_events for game_ids={game_ids!r} provider_name={provider_name!r}: "
            f"{response.status_code} {response.text}"
        )
    result: dict[str, dict] = {}
    for row in response.json():
        result.setdefault(row["game_id"], row["raw_payload"])
    return result


async def read_team_provider_ids(
    client: httpx.AsyncClient, headers: dict, *, provider_name: str, provider_team_ids: list[str]
) -> dict[str, dict]:
    """Maps `provider_team_id -> {"team_id", "name"}` for `provider_name`
    -- the real, canonical `team_provider_ids` + `teams` identity chain
    (the same table sports-intel-layer's own game/player identity
    resolvers already rely on, read here for the first time from
    ai-orchestrator). Two plain reads composed in Python, matching this
    module's own established convention (see `build_contextual_
    intelligence`'s own three-read venue composition). Returns `{}` for
    an empty `provider_team_ids` without making a request."""
    if not provider_team_ids:
        return {}
    mapping_response = await client.get(
        "/rest/v1/team_provider_ids",
        params={
            "provider_name": f"eq.{provider_name}",
            "provider_team_id": f"in.({','.join(provider_team_ids)})",
            "select": "team_id,provider_team_id",
        },
        headers=headers,
    )
    if mapping_response.status_code != 200:
        raise ContextIntelligenceReadError(
            f"failed to read team_provider_ids for provider_name={provider_name!r}: "
            f"{mapping_response.status_code} {mapping_response.text}"
        )
    mapping_rows = mapping_response.json()
    team_ids = sorted({row["team_id"] for row in mapping_rows})
    if not team_ids:
        return {}

    teams_response = await client.get(
        "/rest/v1/teams",
        params={"id": f"in.({','.join(team_ids)})", "select": "id,name"},
        headers=headers,
    )
    if teams_response.status_code != 200:
        raise ContextIntelligenceReadError(
            f"failed to read teams for team_ids={team_ids!r}: {teams_response.status_code} {teams_response.text}"
        )
    names_by_team_id = {row["id"]: row["name"] for row in teams_response.json()}

    return {
        row["provider_team_id"]: {"team_id": row["team_id"], "name": names_by_team_id.get(row["team_id"])}
        for row in mapping_rows
    }


async def resolve_team_identity_for_games(
    client: httpx.AsyncClient, headers: dict, *, game_ids: list[str], provider_name: str = "mysportsfeeds"
) -> dict[str, dict]:
    """The real opponent-identity resolution chain (Player Performance
    Engine Integration pass, 2026-09-15) -- composes the two reads above
    plus `player_performance.extract_msf_team_provider_ids`'s own pure
    parsing into one `{game_id: {"home_team_id", "home_team_name",
    "away_team_id", "away_team_name"}}` map, entirely from real,
    already-persisted canonical identity data:

        game_events.raw_payload (real MySportsFeeds game_boxscore capture)
            -> body.game.homeTeam.id / awayTeam.id (real MSF numeric ids)
        -> team_provider_ids (provider_name='mysportsfeeds') -> team_id
        -> teams.name

    Never a hardcoded team/abbreviation, never a fuzzy match -- exact
    numeric provider-id equality only. A game with no real `game_events`
    row for `provider_name`, or whose raw payload doesn't carry the
    expected MSF shape, or whose extracted provider team id has no
    `team_provider_ids` mapping yet, is simply absent from the returned
    dict -- `player_performance.py`'s own `resolve_opponent_by_team_id`
    already handles a missing/partial entry as an honest, disclosed
    "opponent unavailable" result, never a guess. Returns `{}` for an
    empty `game_ids` without making a request."""
    if not game_ids:
        return {}

    raw_payloads = await read_game_events_raw_payloads(
        client, headers, game_ids=game_ids, provider_name=provider_name
    )

    extracted_by_game: dict[str, tuple[str, str]] = {}
    all_provider_team_ids: set[str] = set()
    for game_id, raw_payload in raw_payloads.items():
        extracted = extract_msf_team_provider_ids(raw_payload)
        if extracted is not None:
            extracted_by_game[game_id] = extracted
            all_provider_team_ids.update(extracted)

    team_by_provider_id = await read_team_provider_ids(
        client, headers, provider_name=provider_name, provider_team_ids=sorted(all_provider_team_ids)
    )

    result: dict[str, dict] = {}
    for game_id, (home_provider_id, away_provider_id) in extracted_by_game.items():
        home = team_by_provider_id.get(home_provider_id)
        away = team_by_provider_id.get(away_provider_id)
        result[game_id] = {
            "home_team_id": home["team_id"] if home else None,
            "home_team_name": home["name"] if home else None,
            "away_team_id": away["team_id"] if away else None,
            "away_team_name": away["name"] if away else None,
        }
    return result


async def read_games_sharing_venue(
    client: httpx.AsyncClient, headers: dict, *, venue_id: str, exclude_game_id: str
) -> list[dict]:
    """Every OTHER real `games` row (`id`, `scheduled_start`) sharing
    `venue_id` -- the venue dimension's own comparable-sample-size
    signal ("how many other tracked games do we have real data for at
    this exact venue"). Returns `[]` when none exist."""
    response = await client.get(
        "/rest/v1/games",
        params={
            "venue_id": f"eq.{venue_id}",
            "id": f"neq.{exclude_game_id}",
            "select": "id,scheduled_start",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(
            f"failed to read games sharing venue_id={venue_id!r}: {response.status_code} {response.text}"
        )
    return response.json()


__all__ = [
    "ContextIntelligenceReadError",
    "read_all_weather_snapshots",
    "read_all_odds_snapshots",
    "read_all_player_stats",
    "read_player_stats_for_player",
    "read_player_identity",
    "read_games_by_ids",
    "read_game_events_raw_payloads",
    "read_team_provider_ids",
    "resolve_team_identity_for_games",
    "read_game_venue_context",
    "read_venue",
    "read_games_sharing_venue",
]
