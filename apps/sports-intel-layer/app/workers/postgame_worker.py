"""Postgame Ingestion Worker orchestration (Phase 3E-8).

Volume 2 §8's own cadence row (v4.2/v4.2.1): "Event-triggered by
`GameFinished` (§4.5), plus a small number of bounded reconciliation
checks -- not continuous polling | Fetches a game's final score, final
team stats, and final player stats when that game's status transitions to
final... performs the initial fetch plus a small, fixed number of
reconciliation checks over a bounded post-finalization window, then treats
the stored record as authoritative." §4.2.1 explicitly separates this from
Postgame Review (Phase 5): this worker does not grade recommendations,
change agent weights, or produce a review.

**Game-final detection -- the smaller polling/status-scan approach (Mac's
explicit Decision 2, 2026-08-18), NOT the full `GameFinished` event
infrastructure.** No code anywhere in this codebase publishes a real
Postgres LISTEN/NOTIFY event yet (confirmed by inspection before writing
this). Building that infrastructure was explicitly ruled out of 3E-8's
scope. Instead, this worker itself re-polls `SportsDataIOScheduleAdapter.
fetch_schedule`/`app.persistence.schedule.persist_schedule_entries` --
the exact same adapter and persistence function Master Refresh already
uses, reused rather than duplicated -- scoped to a backward-looking
window (`_RECONCILIATION_LOOKBACK_DAYS`, see below) instead of Master
Refresh's forward-looking one. **This function is structured so a future
real `GameFinished` event handler can call `_ingest_final_stats_for_game`
directly, without redesigning the ingestion pipeline** -- detection and
ingestion are two separate functions in this module specifically so the
detection half (a stand-in today) can be swapped for a real event
subscriber later with zero change to the ingestion half.

**SportsDataIO's live completed-game status value is ASSUMED / DEFERRED
LIVE VERIFICATION, not CONFIRMED.** `_SCHEDULE_STATUS_MAP["Final"]` (added
this phase in `app.adapters.providers.sportsdataio`) has never been
observed live -- see that module's own comment for the full reasoning,
including why the remaining SportsDataIO Free Trial call is deliberately
NOT being spent to verify it now (the 2026 season hadn't started as of the
last live capture, so the call would likely resolve nothing yet).

**Backward-looking candidate window -- a DERIVED scoping decision, not a
Blueprint number.** Every other specialized worker scopes its candidate
games via a *forward*-looking `_CANDIDATE_WINDOW_DAYS = 7` (games not yet
kicked off). This worker needs the opposite: games that have *already*
kicked off, to detect whether they've gone final, plus games already known
final and still inside their bounded reconciliation window. `_RECONCILIATION_
LOOKBACK_DAYS = 4` (Decision 5's `+72h` final checkpoint, plus a one-day
buffer) is the smallest number that guarantees no game still inside its
reconciliation window falls outside this scan -- DERIVED from Decision 5's
own approved schedule, not invented independently of it.

**Bounded reconciliation -- `app.workers.reconciliation`'s approved
schedule, not a number computed here.** This worker only ever calls
`due_checkpoints`/`is_reconciliation_complete`; see that module's own
docstring for why the five offsets are an APPROVED PRODUCT/ARCHITECTURE
DECISION, not a SportsDataIO-confirmed requirement.

**Idempotent, correction-aware persistence, not append-on-every-poll.**
`app.persistence.team_stats`/`app.persistence.player_stats` only insert a
new row when the incoming stats differ from the existing latest row for
that (game, team)/(game, player) pair -- see those modules' own docstrings
for the full reasoning (Volume 3 §6's own text already flags `team_stats`/
`player_stats` as lacking append-only/versioning at the DB level; this
worker's repeated reconciliation checks would otherwise insert up to 6x
duplicate rows per game/team even when nothing corrected).

**`final_score` is derived from `TeamGameStats`, never a separate Scores/
BoxScore endpoint.** Each team's own row in the `TeamStatsAdapter`
response carries its own `Score` and its `HomeOrAway` side (CONFIRMED
present in this project's own captured fixture) -- both sides' scores are
combined into one `{"home": ..., "away": ...}` value, written only once
both are known (never a partial, one-sided score).

**Player identity -- resolved, never fabricated.** `app.persistence.
player_stats.persist_player_stats` only writes rows for players already
present in `player_provider_ids` (Phase 3E-8's fixture-backed backfill,
`app.persistence.player_backfill`) -- an unresolved player is reported via
`unresolved_players`, never guessed by name-matching, never auto-created
here.

**No internal cache/rate-limit on the Schedule re-poll -- cadence is
whatever an external scheduler decides to invoke this worker at (Railway
scheduling remains unconfigured, out of 3E-8's scope, same as every other
worker).** Unlike a per-game gate (`last_polled_at`), there is no
per-item granularity to throttle here -- one bulk Schedule call per
invocation, either it happens or it doesn't. This is DERIVED, not a
Blueprint number, and flagged for Mac's confirmation alongside the
Schedule-repoll mechanism itself.

**Separation of responsibilities, explicit per Mac's instruction.** This
worker fetches and persists final game/stat facts only. Postgame Review
(Phase 5, `postgame_reviews`), bet/result settlement (Phase 5,
`verified_bets`), agent weighting, and recommendation grading are all
explicitly out of scope and untouched by any code in this module.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.base import PlayerStatsAdapter, ScheduleAdapter, TeamStatsAdapter
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, PlayerStatLine, ScheduleEntry, TeamStatLine
from app.adapters.providers.sportsdataio import (
    SportsDataIOPlayerStatsAdapter,
    SportsDataIOScheduleAdapter,
    SportsDataIOTeamStatsAdapter,
)
from app.persistence.game_identity import GameIdentityError
from app.persistence.games import GamesQueryError, list_games_in_window, mark_game_finalized, update_final_score
from app.persistence.player_stats import PersistenceError as PlayerStatsPersistenceError
from app.persistence.player_stats import persist_player_stats
from app.persistence.schedule import PersistenceError as SchedulePersistenceError
from app.persistence.schedule import persist_schedule_entries
from app.persistence.seasons import SeasonResolutionError, fetch_current_season_string
from app.persistence.team_stats import PersistenceError as TeamStatsPersistenceError
from app.persistence.team_stats import persist_team_stats
from app.workers.reconciliation import due_checkpoints, is_reconciliation_complete

_PROVIDER_NAME = "sportsdataio"

#: DERIVED from Decision 5's own +72h final checkpoint, plus a one-day
#: buffer -- see module docstring. Not a Blueprint-stated number.
_RECONCILIATION_LOOKBACK_DAYS = 4
_FUTURE_BUFFER_DAYS = 1


@dataclass
class ReconciliationGameState:
    checks_done: set[str] = field(default_factory=set)


@dataclass
class PostgameWorkerResult:
    status: str  # "success" | "partial" | "failed"
    games_considered: int = 0
    newly_finalized: list[str] = field(default_factory=list)
    games_reconciled: list[str] = field(default_factory=list)
    unresolved_players: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    error: str | None = None


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


async def _reverse_resolve_sportsdataio_ids(
    client: httpx.AsyncClient, headers: dict, *, game_ids: list[str]
) -> dict[str, str]:
    """Maps games.id -> sportsdataio provider_game_id (GameKey). Mirrors
    `app.workers.injury_worker._reverse_resolve_sportsdataio_ids` exactly
    -- same established pattern, not a new one."""
    if not game_ids:
        return {}
    response = await client.get(
        "/rest/v1/game_provider_ids",
        params={
            "provider_name": f"eq.{_PROVIDER_NAME}",
            "game_id": f"in.({','.join(game_ids)})",
            "select": "game_id,provider_game_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GameIdentityError(
            f"failed to reverse-resolve sportsdataio ids: {response.status_code} {response.text}"
        )
    return {row["game_id"]: row["provider_game_id"] for row in response.json()}


async def _detect_newly_final_games(
    supabase_client: httpx.AsyncClient,
    headers: dict,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    *,
    season: str,
    window_start: date,
    window_end: date,
    schedule_adapter: ScheduleAdapter | None = None,
) -> None:
    """Re-polls Schedule (reused adapter/persistence, see module
    docstring) and PATCHes any status transition -- including into
    'final', now that `_SCHEDULE_STATUS_MAP` supports it. Scoped to this
    worker's own backward-looking window before persisting, so this
    worker never creates or updates a game outside its own concern (Master
    Refresh remains the only creator of new `games` rows).

    `schedule_adapter` (dependency-injection seam, not Demo-specific): when
    supplied, used instead of constructing `SportsDataIOScheduleAdapter`.
    `None` (the default) preserves today's real-provider construction and
    behavior unchanged."""
    schedule_adapter = schedule_adapter or SportsDataIOScheduleAdapter(
        client=sportsdataio_client, api_key=sportsdataio_api_key
    )
    response: AdapterResponse[list[ScheduleEntry]] = await schedule_adapter.fetch_schedule(season)
    in_window = [
        entry
        for entry in response.value
        if window_start <= entry.scheduled_start.date() < window_end
    ]
    if not in_window:
        return
    await persist_schedule_entries(AdapterResponse(value=in_window, source=response.source))


async def _ingest_final_stats_for_game(
    supabase_client: httpx.AsyncClient,
    headers: dict,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    game: dict,
    *,
    season: str,
    team_stats_adapter: TeamStatsAdapter | None = None,
    player_stats_adapter: PlayerStatsAdapter | None = None,
) -> tuple[int, list[str]]:
    """Fetches and persists one game's final team/player stats and derived
    final_score. Reuses `SportsDataIOTeamStatsAdapter`/
    `SportsDataIOPlayerStatsAdapter` (built 3C-ii) unchanged -- no second
    stats-fetch pipeline. Structured to be callable identically from a
    future real `GameFinished` event handler (see module docstring).
    Returns (games_touched, unresolved_players).

    `team_stats_adapter`/`player_stats_adapter` (dependency-injection seam,
    not Demo-specific): when supplied, used instead of constructing
    `SportsDataIOTeamStatsAdapter`/`SportsDataIOPlayerStatsAdapter`. `None`
    (the default, for both) preserves today's real-provider construction
    and behavior unchanged.
    """
    game_id = game["id"]
    week = game["week"]
    if week is None:
        return 0, []

    provider_ids = await _reverse_resolve_sportsdataio_ids(supabase_client, headers, game_ids=[game_id])
    game_key = provider_ids.get(game_id)
    if game_key is None:
        return 0, []

    def season_week_for_game(_game_external_id: str) -> tuple[str, int]:
        return season, week

    team_stats_adapter = team_stats_adapter or SportsDataIOTeamStatsAdapter(
        client=sportsdataio_client, api_key=sportsdataio_api_key, season_week_for_game=season_week_for_game,
    )
    player_stats_adapter = player_stats_adapter or SportsDataIOPlayerStatsAdapter(
        client=sportsdataio_client, api_key=sportsdataio_api_key, season_week_for_game=season_week_for_game,
    )

    team_response: AdapterResponse[list[TeamStatLine]] = await team_stats_adapter.fetch_team_stats(game_key)
    team_result = await persist_team_stats(team_response)

    player_response: AdapterResponse[list[PlayerStatLine]] = await player_stats_adapter.fetch_player_stats(game_key)
    player_result = await persist_player_stats(player_response)

    home_score = next(
        (line.stats.get("Score") for line in team_response.value if line.stats.get("HomeOrAway") == "HOME"), None
    )
    away_score = next(
        (line.stats.get("Score") for line in team_response.value if line.stats.get("HomeOrAway") == "AWAY"), None
    )
    if home_score is not None and away_score is not None:
        await update_final_score(
            supabase_client, headers, game_id=game_id, final_score={"home": home_score, "away": away_score}
        )

    touched = team_result.inserted + player_result.inserted
    return touched, player_result.unresolved_players


async def run_postgame_worker(
    *,
    supabase_client: httpx.AsyncClient,
    sportsdataio_client: httpx.AsyncClient,
    sportsdataio_api_key: str,
    now: datetime | None = None,
    reconciliation_state: dict[str, ReconciliationGameState] | None = None,
    schedule_adapter: ScheduleAdapter | None = None,
    team_stats_adapter: TeamStatsAdapter | None = None,
    player_stats_adapter: PlayerStatsAdapter | None = None,
) -> PostgameWorkerResult:
    """Runs one Postgame Worker cycle. Always returns a
    `PostgameWorkerResult`, never raises -- same finite-job shape as every
    other specialized worker. `reconciliation_state` is caller-supplied
    and mutated in place (mirroring every other worker's `last_polled_at`
    convention -- no worker-run-history persistence layer exists yet).

    `schedule_adapter`/`team_stats_adapter`/`player_stats_adapter`
    (dependency-injection seam, not Demo-specific): passed straight through
    to `_detect_newly_final_games`/`_ingest_final_stats_for_game` below.
    `None` (the default, for all three) preserves today's real-provider
    construction and behavior unchanged."""
    headers = _auth_headers()
    now = now or datetime.now(timezone.utc)
    reconciliation_state = reconciliation_state if reconciliation_state is not None else {}

    today: date = now.date()
    window_start = today - timedelta(days=_RECONCILIATION_LOOKBACK_DAYS)
    window_end = today + timedelta(days=_FUTURE_BUFFER_DAYS)

    try:
        season = await fetch_current_season_string(supabase_client, headers, league_code="nfl", today=today)
    except SeasonResolutionError as exc:
        return PostgameWorkerResult(status="failed", error=f"season resolution failed: {exc}")

    try:
        await _detect_newly_final_games(
            supabase_client, headers, sportsdataio_client, sportsdataio_api_key,
            season=season, window_start=window_start, window_end=window_end,
            schedule_adapter=schedule_adapter,
        )
    except (ProviderError, SchedulePersistenceError) as exc:
        return PostgameWorkerResult(status="failed", error=f"Schedule status re-poll failed: {exc}")

    try:
        games = await list_games_in_window(supabase_client, headers, start=window_start, end=window_end)
    except GamesQueryError as exc:
        return PostgameWorkerResult(status="failed", error=f"failed to list candidate games: {exc}")

    if not games:
        return PostgameWorkerResult(status="success", games_considered=0)

    newly_finalized: list[str] = []
    failures: list[str] = []
    for game in games:
        if game["status"] == "final" and game.get("finalized_at") is None:
            try:
                await mark_game_finalized(supabase_client, headers, game_id=game["id"], finalized_at=now)
                game["finalized_at"] = now.isoformat()
                newly_finalized.append(game["id"])
            except GamesQueryError as exc:
                failures.append(f"{game['id']}: failed to stamp finalized_at: {exc}")

    games_reconciled: list[str] = []
    unresolved_players: list[str] = []
    for game in games:
        if game["status"] != "final" or game.get("finalized_at") is None:
            continue
        game_id = game["id"]
        state = reconciliation_state.get(game_id) or ReconciliationGameState()
        checks_done = frozenset(state.checks_done)
        if is_reconciliation_complete(checks_done):
            continue

        finalized_at = _parse_datetime(game["finalized_at"])
        due = due_checkpoints(now=now, finalized_at=finalized_at, checks_done=checks_done)
        if not due:
            continue

        try:
            _, unresolved = await _ingest_final_stats_for_game(
                supabase_client, headers, sportsdataio_client, sportsdataio_api_key, game, season=season,
                team_stats_adapter=team_stats_adapter, player_stats_adapter=player_stats_adapter,
            )
            unresolved_players.extend(unresolved)
            games_reconciled.append(game_id)
        except (ProviderError, TeamStatsPersistenceError, PlayerStatsPersistenceError, GamesQueryError) as exc:
            failures.append(f"{game_id}: ingestion failed: {exc}")
            continue

        state.checks_done |= set(due)
        reconciliation_state[game_id] = state

    status = "partial" if (failures or unresolved_players) else "success"
    return PostgameWorkerResult(
        status=status,
        games_considered=len(games),
        newly_finalized=newly_finalized,
        games_reconciled=games_reconciled,
        unresolved_players=sorted(set(unresolved_players)),
        failures=failures,
    )
