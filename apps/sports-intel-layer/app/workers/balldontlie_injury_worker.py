"""BALLDONTLIE Injury Worker orchestration (Phase 8.0.5, Data Activation
Pass 1, 2026-09-07).

**A deliberately separate module from `injury_worker.py`, not a
retrofit.** `run_injury_worker` is SportsDataIO-specific end to end (a
single bulk-per-(season,week) call, `game_key_for` keyed by (team,
opponent, season, week), a day-of-week/kickoff-proximity adaptive
cadence) -- none of that shape fits BALLDONTLIE's own real endpoint
(`nfl/v1/player_injuries`, filtered by a flat team-id list, no
season/week concept at all, no opponent needed). Building a second,
honestly BALLDONTLIE-shaped orchestration function is smaller and safer
than parameterizing the existing one to serve two structurally different
providers -- the existing SportsDataIO path (and the reserved trial call
it protects) is completely untouched by this file.

**Scope, explicit and deliberate:** this worker only ever covers real
games that ALREADY carry a real, evidence-backed `game_provider_ids`
row for `provider_name='balldontlie'` -- it never guesses or constructs
a link. Today that means the 5 real Phase 7-tracked games (seeded this
same session from a live BALLDONTLIE schedule-discovery probe); any
other in-window game is simply excluded from `games_linked`, not an
error.

**No cadence/caching yet, by design, not oversight.** This module
implements exactly what HQ authorized for this pass -- "execute one
controlled real DEV pull first... only propose recurring activation
after the live proof succeeds." Adaptive cadence/TTL logic would be
added when (and only when) recurring activation is separately
authorized, following `injury_worker.py`'s own precedent at that point,
not invented ahead of that decision.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, InjuryReport
from app.adapters.providers.balldontlie import BallDontLieInjuryAdapter
from app.persistence.games import GamesQueryError, list_games_in_window
from app.persistence.injury_reports import PersistenceError, persist_injury_reports

_PROVIDER_NAME = "balldontlie"
_SPORTSDATAIO = "sportsdataio"

#: Same candidate-window convention as every other specialized worker.
_CANDIDATE_WINDOW_DAYS = 7


@dataclass
class BallDontLieInjuryWorkerResult:
    status: str  # "success" | "partial" | "failed"
    games_considered: int = 0
    games_linked: int = 0
    teams_resolved: int = 0
    reports_fetched: int = 0
    reports_persisted: int = 0
    failures: list[str] = field(default_factory=list)
    error: str | None = None


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def _resolve_provider_game_ids(
    client: httpx.AsyncClient, headers: dict, *, provider_name: str, game_ids: list[str]
) -> dict[str, str]:
    """Maps games.id -> provider_game_id for `provider_name`, the reverse
    direction of `app.persistence.game_identity.resolve_game_ids`. Mirrors
    `injury_worker.py`'s own `_reverse_resolve_sportsdataio_ids`, scoped
    to any provider rather than hardcoded to one."""
    if not game_ids:
        return {}
    response = await client.get(
        "/rest/v1/game_provider_ids",
        params={
            "provider_name": f"eq.{provider_name}",
            "game_id": f"in.({','.join(game_ids)})",
            "select": "game_id,provider_game_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GamesQueryError(f"failed to resolve {provider_name} game ids: {response.status_code} {response.text}")
    return {row["game_id"]: row["provider_game_id"] for row in response.json()}


async def _resolve_provider_team_ids(
    client: httpx.AsyncClient, headers: dict, *, provider_name: str, team_ids: list[str]
) -> dict[str, str]:
    """Maps teams.id -> provider_team_id for `provider_name` -- the same
    reverse-lookup shape as `_resolve_provider_game_ids` above, applied to
    `team_provider_ids` instead."""
    if not team_ids:
        return {}
    response = await client.get(
        "/rest/v1/team_provider_ids",
        params={
            "provider_name": f"eq.{provider_name}",
            "team_id": f"in.({','.join(team_ids)})",
            "select": "team_id,provider_team_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GamesQueryError(f"failed to resolve {provider_name} team ids: {response.status_code} {response.text}")
    return {row["team_id"]: row["provider_team_id"] for row in response.json()}


async def _resolve_sportsdataio_team_ids(
    client: httpx.AsyncClient, headers: dict, *, abbreviations: list[str]
) -> dict[str, str]:
    """Maps a SportsDataIO team abbreviation (games.home_team/.away_team's
    own namespace) -> teams.id. Forward direction, mirrors
    `app.persistence.team_identity.resolve_team_ids` exactly (not
    reimported here only to keep this module's own provider-agnostic
    helpers grouped together)."""
    if not abbreviations:
        return {}
    response = await client.get(
        "/rest/v1/team_provider_ids",
        params={
            "provider_name": f"eq.{_SPORTSDATAIO}",
            "provider_team_id": f"in.({','.join(abbreviations)})",
            "select": "team_id,provider_team_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GamesQueryError(f"failed to resolve sportsdataio team ids: {response.status_code} {response.text}")
    return {row["provider_team_id"]: row["team_id"] for row in response.json()}


async def run_balldontlie_injury_worker(
    *,
    supabase_client: httpx.AsyncClient,
    balldontlie_client: httpx.AsyncClient,
    balldontlie_api_key: str,
    now: datetime | None = None,
) -> BallDontLieInjuryWorkerResult:
    """Runs one BALLDONTLIE Injury Worker cycle. Always returns a
    `BallDontLieInjuryWorkerResult`, never raises -- same finite-job shape
    as every other specialized worker in this project."""
    headers = _auth_headers()
    now = now or datetime.now(timezone.utc)
    today: date = now.date()

    try:
        games = await list_games_in_window(
            supabase_client, headers, start=today, end=today + timedelta(days=_CANDIDATE_WINDOW_DAYS)
        )
    except GamesQueryError as exc:
        return BallDontLieInjuryWorkerResult(status="failed", error=f"failed to list candidate games: {exc}")

    if not games:
        return BallDontLieInjuryWorkerResult(status="success", games_considered=0)

    try:
        balldontlie_game_id_by_internal = await _resolve_provider_game_ids(
            supabase_client, headers, provider_name=_PROVIDER_NAME, game_ids=[g["id"] for g in games]
        )
    except GamesQueryError as exc:
        return BallDontLieInjuryWorkerResult(
            status="failed", games_considered=len(games), error=f"game identity lookup failed: {exc}"
        )

    linked_games = [g for g in games if g["id"] in balldontlie_game_id_by_internal]
    if not linked_games:
        return BallDontLieInjuryWorkerResult(status="success", games_considered=len(games), games_linked=0)

    abbrevs = sorted({g["home_team"] for g in linked_games} | {g["away_team"] for g in linked_games})
    try:
        abbrev_to_internal_team_id = await _resolve_sportsdataio_team_ids(
            supabase_client, headers, abbreviations=abbrevs
        )
        internal_team_ids = sorted(set(abbrev_to_internal_team_id.values()))
        balldontlie_team_id_by_internal = await _resolve_provider_team_ids(
            supabase_client, headers, provider_name=_PROVIDER_NAME, team_ids=internal_team_ids
        )
    except GamesQueryError as exc:
        return BallDontLieInjuryWorkerResult(
            status="failed",
            games_considered=len(games),
            games_linked=len(linked_games),
            error=f"team identity lookup failed: {exc}",
        )

    game_external_id_by_balldontlie_team_id: dict[int, str] = {}
    for game in linked_games:
        balldontlie_game_id = balldontlie_game_id_by_internal[game["id"]]
        for abbrev in (game["home_team"], game["away_team"]):
            internal_team_id = abbrev_to_internal_team_id.get(abbrev)
            if internal_team_id is None:
                continue
            balldontlie_team_id = balldontlie_team_id_by_internal.get(internal_team_id)
            if balldontlie_team_id is None:
                continue
            game_external_id_by_balldontlie_team_id[int(balldontlie_team_id)] = balldontlie_game_id

    if not game_external_id_by_balldontlie_team_id:
        return BallDontLieInjuryWorkerResult(
            status="success", games_considered=len(games), games_linked=len(linked_games), teams_resolved=0
        )

    adapter = BallDontLieInjuryAdapter(
        client=balldontlie_client,
        api_key=balldontlie_api_key,
        team_ids=sorted(game_external_id_by_balldontlie_team_id),
        game_external_id_for_team_id=lambda team_id: game_external_id_by_balldontlie_team_id.get(team_id),
    )

    try:
        response: AdapterResponse[list[InjuryReport]] = await adapter.fetch_injuries()
    except ProviderError as exc:
        return BallDontLieInjuryWorkerResult(
            status="failed",
            games_considered=len(games),
            games_linked=len(linked_games),
            teams_resolved=len(game_external_id_by_balldontlie_team_id),
            error=f"injuries fetch failed: {exc}",
        )

    persisted = 0
    failures: list[str] = []
    if response.value:
        try:
            persisted = await persist_injury_reports(response, provider_name=_PROVIDER_NAME)
        except PersistenceError as exc:
            failures.append(f"persistence failed: {exc}")

    status = "partial" if failures else "success"
    return BallDontLieInjuryWorkerResult(
        status=status,
        games_considered=len(games),
        games_linked=len(linked_games),
        teams_resolved=len(game_external_id_by_balldontlie_team_id),
        reports_fetched=len(response.value),
        reports_persisted=persisted,
        failures=failures,
    )
