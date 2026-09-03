"""MANSA NFL Provider Bake-Off (2026-09-03) -- BALLDONTLIE vs API-SPORTS.

TEMPORARY, DIAGNOSTIC-ONLY module. This is not a provider adapter and does
not implement `app.adapters.base`'s `ProviderAdapter` contract -- it exists
solely to make a small, curated, budget-bounded set of live calls against
both candidate NFL providers so a real data-quality comparison against the
existing SportsDataIO benchmark can be written up. It is invoked once, at
process startup, from a dev-only, flag-gated hook (see `app/main.py`) --
this workspace's own egress policy blocks direct HTTPS to both vendor
domains (and, it turns out, to this service's own public Railway domain),
so results are retrieved via `logger.warning` lines in Railway's deploy
logs rather than an HTTP response body, the same "log it, since nothing
can call back in" lesson this project already learned during the Phase
7.0B Gate B discovery probes (see PROGRESS.md, 2026-09-02 entries -- that
probe also had to switch from `logger.info` to `logger.warning` because
this service's root logger defaults to WARNING). This module is expected
to be reverted, and `RUN_NFL_BAKEOFF`/`BALLDONTLIE_API_KEY`/
`API_SPORTS_NFL_KEY` left exactly as Mac set them, once the bake-off
report is delivered.

Neither `BALLDONTLIE_API_KEY` nor `API_SPORTS_NFL_KEY` is ever logged or
included in any returned payload -- both are used exactly once each, as an
outbound request header, by `app.master_refresh.production_clients.
build_bakeoff_clients()` (never here, never in `app.main`), matching the
credential-isolation convention `SPORTSDATAIO_API_KEY`/`THE_ODDS_API_KEY`
already established in that same module.

Call budget (confirmed against the official `balldontlie` PyPI package's
`nfl/api.py` source for BALLDONTLIE's real endpoint paths -- WebFetch to
both vendor domains directly is blocked by this workspace's own egress
policy, so no docs page could be scraped live for either provider):
  BALLDONTLIE: 9 calls (teams, active players/roster, current-season
    games, prior-season games, injuries, standings, player stats,
    season stats, one advanced-stats category). No team-stats or
    play-by-play call is attempted -- neither endpoint exists anywhere in
    the official SDK's `NFLApi` (see its own module docstring / `api.py`),
    so a live 404 would add cost without adding information.
  API-SPORTS: 10 calls (leagues discovery, teams, players/roster,
    injuries, standings, games, games/events, team statistics, player
    statistics, one historical-season games call). Endpoint names here
    are inferred from this vendor's own consistent conventions across its
    other sport verticals (confirmed by inspecting the `apisports` PyPI
    package's bundled OpenAPI specs for baseball/basketball/hockey) plus
    public documentation excerpts (WebSearch, since direct docs access is
    blocked) -- each call's own real result is the actual confirmation,
    not the guess.
Total: 19 calls across both providers, run once. BALLDONTLIE's free tier
is documented at 5 requests/minute; a 3-second pacing gap is used between
its calls (not needed for API-SPORTS, whose documented limit is
requests/day, not requests/minute).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

import httpx

_BDL_SEASON_HISTORICAL = 2025  # last fully-completed NFL season as of 2026-09-03
_BDL_SEASON_CURRENT = 2026
_ASP_DEFAULT_LEAGUE_ID = 1  # fallback only if /leagues discovery fails to identify NFL
_ASP_DEFAULT_SEASON = 2025


async def _call(
    client: httpx.AsyncClient, path: str, *, headers: dict, params: dict | None = None
) -> dict[str, Any]:
    """Shared call+capture for both providers. Never raises -- a transport
    failure becomes a recorded `error` field, exactly like every other
    result, so one bad call can't abort the rest of the bake-off."""
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    started = time.monotonic()
    try:
        response = await client.get(path, headers=headers, params=clean_params)
    except httpx.HTTPError as exc:
        return {
            "path": path,
            "params": clean_params,
            "http_status": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}",
            "rate_limit_headers": {},
            "raw_body": None,
        }
    latency_ms = round((time.monotonic() - started) * 1000, 1)
    rate_limit_headers = {
        k: v
        for k, v in response.headers.items()
        if "ratelimit" in k.lower() or k.lower() == "retry-after"
    }
    try:
        body = response.json()
    except ValueError:
        body = {"_non_json_body_preview": response.text[:300]}
    return {
        "path": path,
        "params": clean_params,
        "http_status": response.status_code,
        "latency_ms": latency_ms,
        "error": None,
        "rate_limit_headers": rate_limit_headers,
        "raw_body": _cap_list_fields(body),
    }


def _cap_list_fields(body: Any, *, max_items: int = 6) -> Any:
    """Safety net, not a substitute for the per-call `per_page`/pagination
    params already used above -- caps any top-level list (BALLDONTLIE's
    `data`, API-SPORTS's `response`) to a small sample so one
    unexpectedly-large response can't blow past a single Railway log
    line's practical size limit. The original count is preserved
    alongside the sample, never silently dropped."""
    if not isinstance(body, dict):
        return body
    capped = dict(body)
    for key, value in body.items():
        if isinstance(value, list) and len(value) > max_items:
            capped[key] = value[:max_items]
            capped[f"_{key}_total_count"] = len(value)
            capped[f"_{key}_truncated_for_log"] = True
    return capped


def _bdl_find_team_id(body: dict | None, *, abbreviation: str) -> int | None:
    if not isinstance(body, dict):
        return None
    for team in body.get("data") or []:
        if isinstance(team, dict) and team.get("abbreviation") == abbreviation:
            return team.get("id")
    return None


def _bdl_first_id(body: dict | None) -> int | None:
    if not isinstance(body, dict):
        return None
    data = body.get("data") or []
    if data and isinstance(data[0], dict):
        return data[0].get("id")
    return None


async def run_balldontlie_bakeoff(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    headers = {"Authorization": api_key, "Accept": "application/json"}
    calls: list[dict[str, Any]] = []

    async def step(category: str, path: str, params: dict | None = None) -> dict[str, Any]:
        result = await _call(client, path, headers=headers, params=params)
        result["category"] = category
        result["provider"] = "balldontlie"
        calls.append(result)
        await asyncio.sleep(3.0)  # documented free-tier pace: 5 requests/minute
        return result

    teams = await step("teams", "/nfl/v1/teams")
    kc_id = _bdl_find_team_id(teams["raw_body"], abbreviation="KC")

    await step(
        "rosters_active_players",
        "/nfl/v1/players/active",
        {"team_ids[]": kc_id, "per_page": 5},
    )
    await step(
        "schedules_current_season",
        "/nfl/v1/games",
        {"seasons[]": _BDL_SEASON_CURRENT, "weeks[]": 1, "per_page": 5},
    )
    historical_games = await step(
        "schedules_historical_final",
        "/nfl/v1/games",
        {"seasons[]": _BDL_SEASON_HISTORICAL, "weeks[]": 1, "per_page": 5},
    )
    game_id = _bdl_first_id(historical_games["raw_body"])

    await step(
        "injuries",
        "/nfl/v1/player_injuries",
        {"team_ids[]": kc_id, "per_page": 5},
    )
    await step("standings", "/nfl/v1/standings", {"season": _BDL_SEASON_HISTORICAL})
    await step(
        "player_stats",
        "/nfl/v1/stats",
        {"game_ids[]": game_id, "per_page": 3},
    )
    await step(
        "season_stats",
        "/nfl/v1/season_stats",
        {"season": _BDL_SEASON_HISTORICAL, "team_id": kc_id, "per_page": 3},
    )
    await step(
        "advanced_stats_passing",
        "/nfl/v1/advanced_stats/passing",
        {"season": _BDL_SEASON_HISTORICAL, "week": 1},
    )

    return {
        "calls": calls,
        "resolved_ids": {"kc_team_id": kc_id, "sample_game_id": game_id},
        "not_attempted": {
            "team_stats": (
                "No team-level stats endpoint exists in the official balldontlie "
                "PyPI package's NFLApi (app.py has teams/players/games/stats/"
                "standings/injuries/season_stats/advanced_stats only -- 'stats' "
                "and 'season_stats' are both player-scoped, never team-scoped). "
                "Not called live -- confirmed absent from the vendor's own SDK "
                "source, not merely undocumented."
            ),
            "play_by_play": (
                "No play-by-play/game-events endpoint exists anywhere in the "
                "same SDK source. Not called live for the same reason as above."
            ),
        },
    }


def _asp_find_nfl_league(body: dict | None) -> tuple[int | None, int | None]:
    if not isinstance(body, dict):
        return None, None
    for league in body.get("response") or []:
        if not isinstance(league, dict):
            continue
        name = str(league.get("name", ""))
        if "NFL" in name.upper():
            seasons = league.get("seasons") or []
            latest = None
            for s in seasons:
                year = s.get("season") if isinstance(s, dict) else s
                if isinstance(year, int) and (latest is None or year > latest):
                    latest = year
            return league.get("id"), latest
    return None, None


def _asp_find_team_id(body: dict | None, *, name_contains: str) -> int | None:
    if not isinstance(body, dict):
        return None
    for entry in body.get("response") or []:
        team = entry.get("team") if isinstance(entry, dict) and "team" in entry else entry
        if isinstance(team, dict) and name_contains.lower() in str(team.get("name", "")).lower():
            return team.get("id")
    return None


def _asp_first_game_id(body: dict | None) -> int | None:
    if not isinstance(body, dict):
        return None
    response = body.get("response") or []
    if response and isinstance(response[0], dict):
        game = response[0]
        return game.get("game", {}).get("id") if "game" in game else game.get("id")
    return None


async def run_api_sports_bakeoff(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    headers = {"x-apisports-key": api_key, "Accept": "application/json"}
    calls: list[dict[str, Any]] = []

    async def step(category: str, path: str, params: dict | None = None) -> dict[str, Any]:
        result = await _call(client, path, headers=headers, params=params)
        result["category"] = category
        result["provider"] = "api_sports"
        calls.append(result)
        await asyncio.sleep(0.5)
        return result

    leagues = await step("leagues_discovery", "/leagues")
    league_id, season = _asp_find_nfl_league(leagues["raw_body"])
    used_fallback_league = league_id is None
    if league_id is None:
        league_id, season = _ASP_DEFAULT_LEAGUE_ID, _ASP_DEFAULT_SEASON

    teams = await step("teams", "/teams", {"league": league_id, "season": season})
    kc_id = _asp_find_team_id(teams["raw_body"], name_contains="Chiefs")

    await step("rosters", "/players", {"team": kc_id, "season": season})
    await step("injuries", "/injuries", {"team": kc_id})
    await step("standings", "/standings", {"league": league_id, "season": season})
    games = await step(
        "schedules", "/games", {"league": league_id, "season": season, "team": kc_id}
    )
    game_id = _asp_first_game_id(games["raw_body"])
    await step("games_events_playbyplay", "/games/events", {"id": game_id})
    await step(
        "team_statistics",
        "/teams/statistics",
        {"league": league_id, "season": season, "team": kc_id},
    )
    await step("players_statistics", "/players/statistics", {"season": season, "team": kc_id})
    await step(
        "historical_games",
        "/games",
        {"league": league_id, "season": (season - 5) if season else None, "team": kc_id},
    )

    return {
        "calls": calls,
        "resolved_ids": {
            "league_id": league_id,
            "season": season,
            "used_fallback_league_guess": used_fallback_league,
            "kc_team_id": kc_id,
            "sample_game_id": game_id,
        },
    }


async def run_nfl_bakeoff(
    balldontlie: tuple[httpx.AsyncClient, str] | None,
    api_sports: tuple[httpx.AsyncClient, str] | None,
) -> dict[str, Any]:
    """Top-level entry point the diagnostic endpoint calls. Either provider
    being unavailable (missing credential) never blocks testing the other
    -- each side is fully independent."""
    report: dict[str, Any] = {}

    if balldontlie is not None:
        client, api_key = balldontlie
        report["balldontlie"] = await run_balldontlie_bakeoff(client, api_key)
    else:
        report["balldontlie"] = {"error": "BALLDONTLIE_API_KEY not configured"}

    if api_sports is not None:
        client, api_key = api_sports
        report["api_sports"] = await run_api_sports_bakeoff(client, api_key)
    else:
        report["api_sports"] = {"error": "API_SPORTS_NFL_KEY not configured"}

    return report
