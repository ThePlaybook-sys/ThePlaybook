"""MANSA NFL Provider Gap Test (2026-09-03) -- MySportsFeeds v2.1.

TEMPORARY, DIAGNOSTIC-ONLY module, same shape and same "temporary probe,
then revert" discipline as `app.diagnostics.nfl_bakeoff` (the earlier
BALLDONTLIE/API-SPORTS bake-off, see
`docs/ops/nfl-provider-bakeoff-2026-09-03.md`) -- not a `ProviderAdapter`,
never wired into any permanent route. Invoked once, at process startup,
from a dev-only, flag-gated hook (see `app.main`), because this
workspace's own egress policy blocks direct HTTPS to
`mysportsfeeds.com`/`api.mysportsfeeds.com` (confirmed the same way as
every other vendor domain in the prior bake-off) and to this service's
own public Railway domain -- so results are retrieved via
`logger.warning` lines in Railway's deploy logs, never an HTTP response.

Endpoint paths, auth scheme, and season-string convention below are
CONFIRMED FROM THE OFFICIAL `mysportsfeeds-node` npm package source
(published and maintained by MySportsFeeds' own team,
`brad.barkhouse@mysportsfeeds.com`) -- `lib/API_v2_1.js`/`API_v2_0.js`/
`API_v1_0.js`, not guessed, since direct docs access is blocked the same
way it was for BALLDONTLIE/API-SPORTS.

Base URL: https://api.mysportsfeeds.com/v2.1/pull
Auth: HTTP Basic -- username=API key, password="MYSPORTSFEEDS" (literal
string, confirmed from the SDK's own `authenticate()` usage example).
URL shape: {base}/{league}/{season}/{extra_path}{endpoint}.json, where
`extra_path` is `games/{id}/` for game-scoped feeds (boxscore/playbyplay/
lineup) and `current_season`/`injuries` need no season segment at all.

Call budget: 12 calls total, directly targeting the four gaps this test
was authorized for (current-season team stats, play-by-play, box
scores, lineups) plus the cross-cutting evaluation criteria (standings,
injuries, freshness/corrections via `latest_updates`). Paced 2s apart by
default; MySportsFeeds' real per-minute limit isn't documented in the
SDK, so `_call()` adaptively backs off to 10s between calls the moment
any response's `retry-after` header or a 429 is observed, mirroring the
lesson learned the hard way during the BALLDONTLIE bake-off.
"""
from __future__ import annotations

import asyncio
import base64
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

_MSF_PASSWORD = "MYSPORTSFEEDS"  # CONFIRMED literal, not a real password -- SDK's own authenticate() example


def _auth_header(api_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{api_key}:{_MSF_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def _cap_list_fields(body: Any, *, max_items: int = 6) -> Any:
    """Same safety net as the BALLDONTLIE/API-SPORTS bake-off's own
    `_cap_list_fields` -- caps top-level lists so one oversized response
    can't blow past a single Railway log line's practical size limit.
    Applied only to the LOGGED copy, never to the body callers use for ID
    extraction (that bug, and its fix, is documented in
    `app.diagnostics.nfl_bakeoff`'s own history -- not repeated here)."""
    if isinstance(body, list):
        if len(body) > max_items:
            return {
                "_capped_list": body[:max_items],
                "_total_count": len(body),
                "_truncated_for_log": True,
            }
        return body
    if not isinstance(body, dict):
        return body
    capped = dict(body)
    for key, value in body.items():
        if isinstance(value, list) and len(value) > max_items:
            capped[key] = value[:max_items]
            capped[f"_{key}_total_count"] = len(value)
            capped[f"_{key}_truncated_for_log"] = True
    return capped


async def _call(
    client: httpx.AsyncClient, path: str, *, headers: dict, params: dict | None = None
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        response = await client.get(path, headers=headers, params=params or {})
    except httpx.HTTPError as exc:
        return {
            "path": path,
            "params": params or {},
            "http_status": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}",
            "response_headers": {},
            "raw_body": None,
        }
    latency_ms = round((time.monotonic() - started) * 1000, 1)
    # Keep every header that could speak to freshness/rate-limit/caching
    # semantics -- MSF's own conditional-GET (304) convention, per the
    # official SDK's `force=false` default param, is exactly the kind of
    # signal worth preserving here.
    interesting_headers = {
        k: v
        for k, v in response.headers.items()
        if any(term in k.lower() for term in ("ratelimit", "retry-after", "last-modified", "etag", "cache"))
    }
    try:
        body = response.json() if response.content else None
    except ValueError:
        body = {"_non_json_body_preview": response.text[:300]}
    return {
        "path": path,
        "params": params or {},
        "http_status": response.status_code,
        "latency_ms": latency_ms,
        "error": None,
        "response_headers": interesting_headers,
        "raw_body": body,
    }


def _guess_season_slugs(now: datetime) -> tuple[str, str]:
    """Fallback only, used if `current_season` can't be parsed. NFL's own
    season-naming convention (confirmed from the SDK's own README
    examples, e.g. "2015-2016-regular") labels a season by its start
    year and the following year -- the season that starts in a given
    August runs into the following February."""
    start_year = now.year if now.month >= 7 else now.year - 1
    current = f"{start_year}-{start_year + 1}-regular"
    prior = f"{start_year - 1}-{start_year}-regular"
    return current, prior


def _extract_season_slug(body: Any) -> str | None:
    """Defensive parsing -- the real `current_season` response shape
    isn't captured anywhere reachable from this session, so this tries
    every plausible key rather than assuming one."""
    if not isinstance(body, dict):
        return None
    season = body.get("season")
    if isinstance(season, dict):
        for key in ("slug", "name", "id"):
            value = season.get(key)
            if isinstance(value, str):
                return value
    for key in ("slug", "season"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    return None


def _first_game_id(body: Any) -> int | str | None:
    if not isinstance(body, dict):
        return None
    games = body.get("games")
    if isinstance(games, list) and games:
        entry = games[0]
        if isinstance(entry, dict):
            game = entry.get("schedule") or entry.get("game") or entry
            if isinstance(game, dict):
                return game.get("id")
    return None


def _prior_season_slug(slug: str) -> str:
    match = re.match(r"^(\d{4})-(\d{4})-(.+)$", slug)
    if not match:
        return slug
    start, end, kind = match.groups()
    return f"{int(start) - 1}-{int(end) - 1}-{kind}"


async def run_msf_bakeoff(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    headers = _auth_header(api_key)
    calls: list[dict[str, Any]] = []
    delay = 2.0

    async def step(category: str, path: str, params: dict | None = None) -> dict[str, Any]:
        nonlocal delay
        result = await _call(client, path, headers=headers, params=params)
        result["category"] = category
        logged = dict(result)
        logged["raw_body"] = _cap_list_fields(result["raw_body"])
        calls.append(logged)
        if result["http_status"] == 429 or result["response_headers"].get("retry-after"):
            delay = max(delay, 10.0)
        await asyncio.sleep(delay)
        return result

    current_season_probe = await step("current_season", "/nfl/current_season.json")
    current_slug = _extract_season_slug(current_season_probe["raw_body"])
    fallback_current, fallback_prior = _guess_season_slugs(datetime.now(timezone.utc))
    used_fallback_season = current_slug is None
    if current_slug is None:
        current_slug = fallback_current
    prior_slug = _prior_season_slug(current_slug) if not used_fallback_season else fallback_prior

    await step(
        "schedules_current_season",
        f"/nfl/{current_slug}/week/1/games.json",
    )
    prior_games = await step(
        "schedules_prior_season_completed",
        f"/nfl/{prior_slug}/week/1/games.json",
    )
    game_id = _first_game_id(prior_games["raw_body"])

    await step(
        "box_score",
        f"/nfl/{prior_slug}/games/{game_id}/boxscore.json" if game_id else f"/nfl/{prior_slug}/games/unknown/boxscore.json",
    )
    await step(
        "play_by_play",
        f"/nfl/{prior_slug}/games/{game_id}/playbyplay.json" if game_id else f"/nfl/{prior_slug}/games/unknown/playbyplay.json",
    )
    await step(
        "lineup",
        f"/nfl/{prior_slug}/games/{game_id}/lineup.json" if game_id else f"/nfl/{prior_slug}/games/unknown/lineup.json",
    )
    await step(
        "team_gamelogs_current_season",
        f"/nfl/{current_slug}/team_gamelogs.json",
    )
    await step(
        "team_gamelogs_prior_season",
        f"/nfl/{prior_slug}/team_gamelogs.json",
    )
    await step(
        "team_stats_totals_current_season",
        f"/nfl/{current_slug}/team_stats_totals.json",
    )
    await step(
        "standings_prior_season",
        f"/nfl/{prior_slug}/standings.json",
    )
    await step("injuries_current", "/nfl/injuries.json")
    await step(
        "latest_updates_current_season",
        f"/nfl/{current_slug}/latest_updates.json",
    )

    return {
        "calls": calls,
        "resolved_ids": {
            "current_season_slug": current_slug,
            "prior_season_slug": prior_slug,
            "used_fallback_season_guess": used_fallback_season,
            "sample_game_id": game_id,
        },
        "note": (
            "No live/in-progress NFL game existed at test time (2026 season "
            "kicks off 2026-09-09; this test ran 2026-09-03), so Near-Realtime "
            "vs delayed-tier freshness value could not be empirically measured "
            "-- box score/PBP/lineup were tested against a completed PRIOR "
            "season game instead, which is a valid completeness/granularity "
            "test but not a freshness/tier-value test."
        ),
    }
