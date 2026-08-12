"""SportsDataIO adapters (Volume 2 §8, Phase 3C-ii).

Implements `RosterAdapter`, `ScheduleAdapter`, `InjuryAdapter`,
`TeamStatsAdapter`, and `PlayerStatsAdapter` against SportsDataIO's NFL v3
REST contract. Unlike Phase 3B/3C-i (fixture-first, no live key), this
vendor was live-validated during Phase 3C-ii's investigation (Mac's
authenticated SportsDataIO Free Trial account, 10 of a 12-call budget
spent across two rounds -- see PROGRESS.md for the full session history).
Every endpoint path, the auth header, and the response *structure* below is
CONFIRMED FROM LIVE FREE TRIAL, not assumed -- but the trial's data is
deliberately scrambled/perturbed for several fields (documented per-field
below), so *content* fidelity is still DEFERRED PRODUCTION VERIFICATION.

Endpoint paths (CONFIRMED FROM LIVE FREE TRIAL, corrected once already
during this project against SportsDataIO's own documentation -- the
original assumed paths were wrong on two independent axes: category
segment and endpoint name):
    Players       GET /v3/nfl/scores/json/Players/{team}
    DepthCharts   GET /v3/nfl/scores/json/DepthCharts
    Schedules     GET /v3/nfl/scores/json/Schedules/{season}
    Injuries      GET /v3/nfl/stats/json/Injuries/{season}/{week}
    TeamGameStats GET /v3/nfl/scores/json/TeamGameStats/{season}/{week}
    PlayerGameStatsByWeek
                  GET /v3/nfl/stats/json/PlayerGameStatsByWeek/{season}/{week}

Auth: CONFIRMED -- `Ocp-Apim-Subscription-Key` request header (never a URL
query parameter), proven working against all six categories.

Source-of-truth boundaries (Mac's explicit decision, 2026-08-12): the
Injuries and DepthCharts endpoints are authoritative for injury status and
depth-chart position respectively -- NOT the overlapping (and, in Free
Trial data, scrambled) injury/depth fields embedded in the Players and
PlayerGameStatsByWeek responses. Those overlapping fields are read from
their bulk payloads incidentally but never promoted into a normalized
model here.

**Game-focused contract, vendor-shape kept out of it (Mac's explicit
architecture decision, 2026-08-12):** SportsDataIO's TeamGameStats and
PlayerGameStatsByWeek are week-scoped bulk endpoints, but 3A's
`TeamStatsAdapter.fetch_team_stats(game_external_id)` /
`PlayerStatsAdapter.fetch_player_stats(game_external_id)` stay per-game --
verified compatible with the existing 3A contract and 3B/3C-i's
`CacheBackend`/`cache_key` cache architecture before writing any of this
(no conflict found, so no interface change was needed): both adapters
fetch the whole week's bulk payload once, cache it via the *same* generic
`CacheBackend` primitive 3B/3C-i already established (not a new caching
subsystem), and filter the cached week to the requested `GameKey` on every
call. A second game from the same week reuses the cached bulk response
instead of triggering a second SportsDataIO call. This is a second,
adapter-internal cache layer -- distinct from the outer per-call
`CachingAdapter` any caller wraps this with -- so a provider swap to a
naturally per-game vendor simply wouldn't need this layer at all.

**Roster + Depth Chart merge, not two separate contracts (Mac's explicit
instruction):** 3A has no `DataCategory.DEPTH_CHARTS` / no dedicated ABC --
`RosterAdapter.fetch_roster`'s own docstring says it returns "a team's
current roster and depth chart." `SportsDataIORosterAdapter` therefore
calls *both* `/Players/{team}` and `/DepthCharts` (the latter cached
league-wide, bulk, same pattern as the week-scoped stats above) and merges
`DepthOrder` by `PlayerID` into `RosterEntry.depth_chart_rank`. If the
DepthCharts call fails, the whole `fetch_roster` call raises -- there is no
established "return partial/degraded data" pattern anywhere in this
codebase (every adapter method here either fully succeeds or raises a
`ProviderError`), so silently falling back to the Players endpoint's own
unreliable depth fields would be inventing a new, undocumented behavior,
not reusing an existing one.

**`InjuryReport.game_external_id` is derived, not provided.** The Injuries
response has no `GameKey`/game identifier at all -- only `Season`/`Week`/
`Team`/`Opponent`. Consistent with the exact resolver-injection pattern
already established for `WeatherAPIWeatherAdapter.location_for_game` (3C-i),
this adapter takes an injected `game_key_for(team, opponent, season, week)
-> str | None` resolver, meant in production to look up an already-fetched
Schedule. A `None` result (e.g. a bye-week team with no game that week) is
treated as a legitimate, expected case -- that record is skipped, not
raised as malformed data. No persistence is introduced to solve this
lookup here, per Mac's explicit instruction. `fetch_injuries`'s own 3A
signature carries no season/week parameter, so a second injected resolver,
`current_season_week() -> tuple[str, int]`, supplies it -- production
wiring for both resolvers is a later-milestone concern, not built here.

**`InjuryReport.description` is deliberately left unmapped (`None`) for
now -- an open decision, not an oversight.** Checked before assuming
anything: `models.py` and `base.py` carry no comment on this field's
intended semantics, and no blueprint volume defines it at the field level
either. The captured Injuries response's three text-shaped candidates
(`BodyPart`, `Practice`, `PracticeDescription`) are all `"Scrambled"` in
every one of the 294 captured rows, so content can't disambiguate which
one (if any) the model's free-text `description` is meant to hold. Per
Mac's explicit instruction ("if it remains genuinely ambiguous, stop on
that specific decision and report the alternatives rather than inventing
one"), this stays `None` until he picks one -- reported as an open
question, not resolved by guessing here.

**Schedule status: only what's actually been observed.** All 304 games
captured in the live Schedules response were `"Scheduled"` or `null`
(2026REG hasn't started). `_SCHEDULE_STATUS_MAP` therefore has exactly one
entry. Any other value -- including `null` -- raises `ProviderDataError`
rather than being silently mapped to a guess, per Mac's explicit
instruction not to invent the rest of the vocabulary from assumption.

**Trial numeric values are structurally real but semantically untrusted.**
Cross-checked, not just asserted: in the live `team_stats` capture, `Score`
never equalled the sum of `ScoreQuarter1-4`+`ScoreOvertime` in any of the 32
rows, and `CompletionPercentage` didn't match `PassingCompletions`/
`PassingAttempts` in 29 of 32. `player_stats` counting fields (e.g.
`PassingAttempts: 53.6`) are visibly fractional. Both `TeamStatLine.stats`
and `PlayerStatLine.stats` pass these fields through as an untyped dict
without validating their arithmetic -- that's expected, not a bug to fix;
tests must not assert the scrambled numbers reconcile.
"""
from __future__ import annotations

import json
from typing import Callable

import httpx

from app.adapters.base import (
    InjuryAdapter,
    PlayerStatsAdapter,
    RosterAdapter,
    ScheduleAdapter,
    TeamStatsAdapter,
)
from app.adapters.cache import CacheBackend, cache_key
from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.models import (
    AdapterResponse,
    InjuryReport,
    PlayerStatLine,
    RosterEntry,
    ScheduleEntry,
    TeamStatLine,
)

#: CONFIRMED FROM LIVE FREE TRIAL -- the only schedule status value ever
#: observed (all 304 captured 2026REG games; season hadn't started). Any
#: other value, including a JSON null, raises rather than being guessed.
_SCHEDULE_STATUS_MAP = {"Scheduled": "scheduled"}

#: CONFIRMED FROM PROVIDER DOCUMENTATION (Mac, 2026-08-12): SportsDataIO's
#: own docs state a 5-minute call interval for these categories -- used as
#: the default bulk-payload cache TTL so repeated per-game/per-team calls
#: within that window reuse one provider fetch.
_DEFAULT_BULK_CACHE_TTL_SECONDS = 300


async def _get(
    client: httpx.AsyncClient,
    path: str,
    *,
    api_key: str,
    provider_name: str,
    params: dict | None = None,
) -> httpx.Response:
    """Shared HTTP call + error translation for every adapter below.
    CONFIRMED: auth is the `Ocp-Apim-Subscription-Key` header, never a URL
    query parameter -- proven against all six categories during live
    validation."""
    try:
        response = await client.get(
            path, params=params, headers={"Ocp-Apim-Subscription-Key": api_key}
        )
    except httpx.HTTPError as exc:
        raise ProviderUnavailableError(
            f"transport error calling {path}: {exc}", provider=provider_name
        ) from exc

    if response.status_code in (401, 403):
        raise ProviderAuthError("invalid or missing API key", provider=provider_name)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        raise ProviderRateLimitError(
            "rate limited",
            provider=provider_name,
            retry_after_seconds=float(retry_after) if retry_after else None,
        )
    if response.status_code == 404:
        # CONFIRMED real behavior, not a guess: this is exactly the status
        # this project observed for a wrong endpoint path and, separately,
        # for a season/week that hasn't been played yet -- a data-
        # availability condition, not an outage.
        raise ProviderDataError(f"endpoint/data not found (404): {path}", provider=provider_name)
    if response.status_code >= 500:
        raise ProviderUnavailableError(
            f"provider returned {response.status_code}", provider=provider_name
        )
    if response.status_code != 200:
        raise ProviderDataError(
            f"unexpected status {response.status_code}: {response.text}", provider=provider_name
        )
    return response


def _parse_json_array(response: httpx.Response, *, provider_name: str) -> list[dict]:
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderDataError("response body was not valid JSON", provider=provider_name) from exc
    if not isinstance(data, list):
        raise ProviderDataError("expected a JSON array", provider=provider_name)
    return data


def _parse_timestamp_utc(value: str):
    from datetime import datetime, timezone

    # CONFIRMED: DateTimeUTC carries no offset marker in the captured
    # payload despite being UTC by name/convention -- attach tzinfo
    # explicitly rather than trust a naive-datetime comparison later.
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


class _WeeklyBulkCacheMixin:
    """Shared cache-aside helper for any bulk, non-per-game SportsDataIO
    endpoint (a season+week payload, or a whole-league payload with no
    scoping at all). Reuses `app.adapters.cache`'s existing `CacheBackend`/
    `cache_key` primitives directly -- deliberately not a new caching
    subsystem, per Mac's explicit instruction to reuse established
    patterns. `cache_backend=None` (the default) disables this layer
    entirely, matching every other adapter in this codebase, which has no
    caching of its own and relies on being wrapped in `CachingAdapter`."""

    _client: httpx.AsyncClient
    _api_key: str
    _cache: CacheBackend | None
    _cache_ttl_seconds: int
    provider_name: str

    async def _get_bulk_array(self, path: str, *cache_key_parts: object) -> list[dict]:
        key = None
        if self._cache is not None:
            key = cache_key(self.provider_name, *cache_key_parts)
            cached = await self._cache.get(key)
            if cached is not None:
                return json.loads(cached)

        response = await _get(self._client, path, api_key=self._api_key, provider_name=self.provider_name)
        data = _parse_json_array(response, provider_name=self.provider_name)

        if self._cache is not None:
            await self._cache.set(key, json.dumps(data), self._cache_ttl_seconds)
        return data


class SportsDataIORosterAdapter(RosterAdapter, _WeeklyBulkCacheMixin):
    provider_name = "sportsdataio"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        cache_backend: CacheBackend | None = None,
        cache_ttl_seconds: int = _DEFAULT_BULK_CACHE_TTL_SECONDS,
    ):
        self._client = client
        self._api_key = api_key
        self._cache = cache_backend
        self._cache_ttl_seconds = cache_ttl_seconds

    async def fetch_roster(self, team: str) -> AdapterResponse[list[RosterEntry]]:
        response = await _get(
            self._client, f"/v3/nfl/scores/json/Players/{team}",
            api_key=self._api_key, provider_name=self.provider_name,
        )
        players = _parse_json_array(response, provider_name=self.provider_name)

        # CONFIRMED source-of-truth decision: depth rank comes from
        # DepthCharts, never from Players' own (scrambled, in trial data)
        # depth fields. A DepthCharts failure propagates -- see module
        # docstring for why no silent fallback exists.
        depth_by_player_id = await self._get_depth_chart_lookup()

        entries: list[RosterEntry] = []
        try:
            for p in players:
                player_id = p["PlayerID"]
                entries.append(
                    RosterEntry(
                        team=p["Team"],
                        player_external_id=str(player_id),
                        player_name=p["Name"],
                        position=p["Position"],
                        depth_chart_rank=depth_by_player_id.get(player_id),
                    )
                )
        except (KeyError, TypeError) as exc:
            raise ProviderDataError(f"malformed roster payload: {exc}", provider=self.provider_name) from exc

        return AdapterResponse(value=entries, source=self.provider_name)

    async def _get_depth_chart_lookup(self) -> dict[int, int | None]:
        teams = await self._get_bulk_array(
            "/v3/nfl/scores/json/DepthCharts", "depth_charts_bulk"
        )
        lookup: dict[int, int | None] = {}
        try:
            for team_entry in teams:
                for group in ("Offense", "Defense", "SpecialTeams"):
                    for entry in team_entry.get(group) or []:
                        lookup[entry["PlayerID"]] = entry.get("DepthOrder")
        except (KeyError, TypeError) as exc:
            raise ProviderDataError(f"malformed depth chart payload: {exc}", provider=self.provider_name) from exc
        return lookup


class SportsDataIOScheduleAdapter(ScheduleAdapter):
    provider_name = "sportsdataio"

    def __init__(self, *, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def fetch_schedule(self, season_external_id: str) -> AdapterResponse[list[ScheduleEntry]]:
        response = await _get(
            self._client, f"/v3/nfl/scores/json/Schedules/{season_external_id}",
            api_key=self._api_key, provider_name=self.provider_name,
        )
        games = _parse_json_array(response, provider_name=self.provider_name)

        entries: list[ScheduleEntry] = []
        try:
            for g in games:
                status = self._normalize_status(g.get("Status"))
                stadium_details = g.get("StadiumDetails") or {}
                entries.append(
                    ScheduleEntry(
                        game_external_id=g["GameKey"],
                        home_team=g["HomeTeam"],
                        away_team=g["AwayTeam"],
                        scheduled_start=_parse_timestamp_utc(g["DateTimeUTC"]),
                        stadium=stadium_details.get("Name"),
                        status=status,
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderDataError(f"malformed schedule payload: {exc}", provider=self.provider_name) from exc

        return AdapterResponse(value=entries, source=self.provider_name)

    def _normalize_status(self, raw_status: object) -> str:
        if raw_status not in _SCHEDULE_STATUS_MAP:
            raise ProviderDataError(
                f"unrecognized schedule status {raw_status!r} -- only "
                f"{sorted(_SCHEDULE_STATUS_MAP)} are CONFIRMED from live data, "
                "not silently mapped",
                provider=self.provider_name,
            )
        return _SCHEDULE_STATUS_MAP[raw_status]


class SportsDataIOTeamStatsAdapter(TeamStatsAdapter, _WeeklyBulkCacheMixin):
    provider_name = "sportsdataio"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        season_week_for_game: Callable[[str], tuple[str, int]],
        cache_backend: CacheBackend | None = None,
        cache_ttl_seconds: int = _DEFAULT_BULK_CACHE_TTL_SECONDS,
    ):
        self._client = client
        self._api_key = api_key
        self._season_week_for_game = season_week_for_game
        self._cache = cache_backend
        self._cache_ttl_seconds = cache_ttl_seconds

    async def fetch_team_stats(self, game_external_id: str) -> AdapterResponse[list[TeamStatLine]]:
        season, week = self._season_week_for_game(game_external_id)
        rows = await self._get_bulk_array(
            f"/v3/nfl/scores/json/TeamGameStats/{season}/{week}",
            "team_stats_week_bulk", season, week,
        )

        lines: list[TeamStatLine] = []
        try:
            # `row["GameKey"]`, not `.get()` -- a row missing GameKey
            # entirely is a malformed payload, not just "a different game"
            # that should be silently filtered out.
            matching = [row for row in rows if row["GameKey"] == game_external_id]
            for row in matching:
                remaining = dict(row)
                game_key = remaining.pop("GameKey")
                team = remaining.pop("Team")
                lines.append(TeamStatLine(game_external_id=game_key, team=team, stats=remaining))
        except (KeyError, TypeError) as exc:
            raise ProviderDataError(f"malformed team stats payload: {exc}", provider=self.provider_name) from exc

        return AdapterResponse(value=lines, source=self.provider_name)


class SportsDataIOPlayerStatsAdapter(PlayerStatsAdapter, _WeeklyBulkCacheMixin):
    provider_name = "sportsdataio"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        season_week_for_game: Callable[[str], tuple[str, int]],
        cache_backend: CacheBackend | None = None,
        cache_ttl_seconds: int = _DEFAULT_BULK_CACHE_TTL_SECONDS,
    ):
        self._client = client
        self._api_key = api_key
        self._season_week_for_game = season_week_for_game
        self._cache = cache_backend
        self._cache_ttl_seconds = cache_ttl_seconds

    async def fetch_player_stats(self, game_external_id: str) -> AdapterResponse[list[PlayerStatLine]]:
        season, week = self._season_week_for_game(game_external_id)
        rows = await self._get_bulk_array(
            f"/v3/nfl/stats/json/PlayerGameStatsByWeek/{season}/{week}",
            "player_stats_week_bulk", season, week,
        )

        lines: list[PlayerStatLine] = []
        try:
            # `row["GameKey"]`, not `.get()` -- see fetch_team_stats' same
            # fix: a row missing GameKey is malformed, not a non-match.
            matching = [row for row in rows if row["GameKey"] == game_external_id]
            for row in matching:
                remaining = dict(row)
                game_key = remaining.pop("GameKey")
                player_id = remaining.pop("PlayerID")
                name = remaining.pop("Name")
                team = remaining.pop("Team")
                # ScoringDetails (a genuinely new nested sub-structure, per
                # SportsDataIO's own documented "Included data tables:
                # PlayerGame, ScoringDetail") stays inside `stats` --
                # `stats: dict` absorbs a nested list without issue.
                lines.append(
                    PlayerStatLine(
                        game_external_id=game_key,
                        player_external_id=str(player_id),
                        player_name=name,
                        team=team,
                        stats=remaining,
                    )
                )
        except (KeyError, TypeError) as exc:
            raise ProviderDataError(f"malformed player stats payload: {exc}", provider=self.provider_name) from exc

        return AdapterResponse(value=lines, source=self.provider_name)


class SportsDataIOInjuryAdapter(InjuryAdapter):
    provider_name = "sportsdataio"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        current_season_week: Callable[[], tuple[str, int]],
        game_key_for: Callable[[str, str, str, int], str | None],
    ):
        self._client = client
        self._api_key = api_key
        self._current_season_week = current_season_week
        self._game_key_for = game_key_for

    async def fetch_injuries(self, team: str | None = None) -> AdapterResponse[list[InjuryReport]]:
        season, week = self._current_season_week()
        response = await _get(
            self._client, f"/v3/nfl/stats/json/Injuries/{season}/{week}",
            api_key=self._api_key, provider_name=self.provider_name,
        )
        rows = _parse_json_array(response, provider_name=self.provider_name)

        reports: list[InjuryReport] = []
        try:
            for row in rows:
                if team is not None and row["Team"] != team:
                    continue
                game_external_id = self._game_key_for(row["Team"], row["Opponent"], season, week)
                if game_external_id is None:
                    # Expected, not malformed: e.g. a bye-week team with no
                    # game this week. Skip this record rather than raise.
                    continue
                reports.append(
                    InjuryReport(
                        game_external_id=game_external_id,
                        player_external_id=str(row["PlayerID"]),
                        player_name=row["Name"],
                        team=row["Team"],
                        status=row["Status"],
                        # Deliberately unmapped -- see module docstring's
                        # "InjuryReport.description" section. Not BodyPart,
                        # not Practice, not PracticeDescription, until Mac
                        # resolves which one (if any) is intended.
                        description=None,
                    )
                )
        except (KeyError, TypeError) as exc:
            raise ProviderDataError(f"malformed injuries payload: {exc}", provider=self.provider_name) from exc

        return AdapterResponse(value=reports, source=self.provider_name)


__all__ = [
    "SportsDataIORosterAdapter",
    "SportsDataIOScheduleAdapter",
    "SportsDataIOInjuryAdapter",
    "SportsDataIOTeamStatsAdapter",
    "SportsDataIOPlayerStatsAdapter",
]
