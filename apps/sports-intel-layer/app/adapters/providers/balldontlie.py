"""BALLDONTLIE adapters (Phase 8.0.5, Data Activation Pass 1, 2026-09-07).

Implements `InjuryAdapter` against BALLDONTLIE's real `nfl/v1/player_injuries`
endpoint -- the provider-neutral path the Phase 8.0.5 audit
(`docs/ops/phase-8.0.5-data-activation-audit-2026-09-07.md` §6) designed,
built now under HQ's explicit "do not spend the reserved SportsDataIO
call" instruction. Matches the existing `ProviderAdapter` pattern exactly:
nothing outside `app.adapters` needs to know this is BALLDONTLIE rather
than SportsDataIO behind `InjuryAdapter`'s interface.

Provenance, since Mac's explicit instruction is to never present an
assumption as vendor fact:

- Base URL (`https://api.balldontlie.io`), auth header (`Authorization:
  <key>`, not `Bearer`), and `/nfl/v1/player_injuries` endpoint shape
  (`team_ids`/`player_ids`/`cursor`/`per_page` params, sent as `key[]`
  for list params; response `{"data": [{"player": {...}, "status",
  "comment", "date"}], "meta": {...}}`) are CONFIRMED from the official
  `balldontlie` PyPI package's own source (`nfl/api.py`/`nfl/models.py`,
  unrestricted PyPI egress -- this workspace's own egress policy blocks
  `api.balldontlie.io` directly, same constraint as every other vendor in
  this project), the same provenance tier already used for
  `TheOddsApiOddsAdapter`.
- The real numeric team/game ids this adapter is driven by (via its
  injected resolvers, see below) were CONFIRMED from a real, live
  `nfl/v1/games` call made this same session (Phase 7's BALLDONTLIE
  schedule-discovery probe) -- not guessed or derived from public NFL
  knowledge.

**No game reference exists on a BALLDONTLIE injury row at all** (confirmed
from `NFLPlayerInjury`'s own field list: `player`, `status`, `comment`,
`date` -- no game/week field). This adapter therefore cannot resolve
`InjuryReport.game_external_id` from the raw response alone the way
`SportsDataIOInjuryAdapter` resolves it from an injected `game_key_for`
callable keyed by (team, opponent, season, week) -- there is no
opponent/week on the BALLDONTLIE row to look either up by. Instead, this
adapter takes a simpler injected resolver, `game_external_id_for_team_id:
Callable[[int], str | None]`, keyed only by BALLDONTLIE's own numeric
team id (the one real identity a BALLDONTLIE injury row does carry, via
`player.team.id`) -- the caller (a worker, not this adapter) is
responsible for knowing which of this week's real games a given real
team is playing in, exactly the same "worker resolves identity, adapter
stays a thin translation layer" boundary every other adapter in this
package already respects.

A player whose team resolves to no known game this cycle (bye week, or a
team this worker wasn't asked to cover) is dropped, not guessed --
counted by the caller via the returned `AdapterResponse`, never silently
fabricated.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

import httpx

from app.adapters.base import InjuryAdapter
from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.models import AdapterResponse, FinalScoreLine, InjuryReport

_logger = logging.getLogger("sports-intel-layer.adapters.balldontlie")

#: Multi-sport readiness (Phase 8.0.5 Data Activation Pass 2, 2026-09-07,
#: HQ's locked sport-agnostic architecture rule): named, not inlined, so
#: the one NFL-specific choice this adapter makes is a single visible
#: edit point, matching `app.adapters.providers.the_odds_api._SPORT_KEY`'s
#: own existing precedent. BALLDONTLIE's own URL structure ties sport
#: into the path itself (`nfl/v1/...` vs. a hypothetical `nba/v1/...`) --
#: real per-sport support would need this adapter to accept a sport
#: parameter and thread it through the caller, which is real NBA-support
#: work, explicitly not authorized or begun this pass.
_SPORT_PATH = "nfl"


class BallDontLieInjuryAdapter(InjuryAdapter):
    provider_name = "balldontlie"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        team_ids: list[int],
        game_external_id_for_team_id: Callable[[int], str | None],
    ):
        self._client = client
        self._api_key = api_key
        self._team_ids = team_ids
        self._game_external_id_for_team_id = game_external_id_for_team_id

    async def fetch_injuries(self, team: str | None = None) -> AdapterResponse[list[InjuryReport]]:
        """`team` (the ABC's own per-team filter parameter) is unused here,
        matching `SportsDataIOInjuryAdapter`'s own precedent -- this
        adapter is constructor-scoped to the caller's real `team_ids`
        list instead, since that's the shape BALLDONTLIE's own endpoint
        actually supports (a bulk, multi-team list filter, not a single-
        team-per-call contract)."""
        try:
            response = await self._client.get(
                f"/{_SPORT_PATH}/v1/player_injuries",
                params={"team_ids[]": [str(team_id) for team_id in self._team_ids], "per_page": "100"},
                headers={"Authorization": self._api_key},
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"transport error calling /nfl/v1/player_injuries: {exc}", provider=self.provider_name
            ) from exc

        if response.status_code == 401:
            raise ProviderAuthError("invalid or missing API key", provider=self.provider_name)
        if response.status_code == 429:
            # CONFIRMED: BALLDONTLIE's own 5 requests/minute limit (2026-09-03
            # NFL provider bake-off, via its own x-ratelimit-limit header).
            raise ProviderRateLimitError("rate limited", provider=self.provider_name)
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"provider returned {response.status_code}", provider=self.provider_name
            )
        if response.status_code != 200:
            raise ProviderDataError(
                f"unexpected status {response.status_code}: {response.text}", provider=self.provider_name
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderDataError("response body was not valid JSON", provider=self.provider_name) from exc
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise ProviderDataError("expected an object with a 'data' array", provider=self.provider_name)

        reports: list[InjuryReport] = []
        for row in data["data"]:
            try:
                player = row["player"]
                player_team = player.get("team") or {}
                balldontlie_team_id = player_team.get("id")
                game_external_id = (
                    self._game_external_id_for_team_id(balldontlie_team_id)
                    if balldontlie_team_id is not None
                    else None
                )
                if game_external_id is None:
                    # No real game this cycle involves this player's team --
                    # a bye week, or a team outside this worker's real
                    # in-scope list. Dropped, never guessed.
                    continue
                reports.append(
                    InjuryReport(
                        game_external_id=game_external_id,
                        player_external_id=str(player["id"]),
                        player_name=f"{player['first_name']} {player['last_name']}",
                        team=player_team.get("abbreviation", "unknown"),
                        status=row["status"],
                        description=row.get("comment"),
                    )
                )
            except (KeyError, TypeError) as exc:
                _logger.warning(
                    "skipping malformed balldontlie injury row (player_id=%r): %s",
                    row.get("player", {}).get("id") if isinstance(row.get("player"), dict) else None,
                    exc,
                )
                continue

        # No response-level freshness signal exists on this endpoint (no
        # bulk "last updated" header/field, unlike The Odds API's
        # x-requests-* headers) -- never fabricated.
        return AdapterResponse(value=reports, source=self.provider_name, provider_reported_at=None)


__all__ = ["BallDontLieInjuryAdapter"]


#: The machine-readable completion value on `nfl/v1/games`. CONFIRMED FROM A
#: REAL 2026 RESPONSE, not documentation: the 2026-09-11 Week 1 recovery
#: capture (persisted in `game_events`, provider `balldontlie`) carries all
#: three lifecycle values in one payload -- `final` (NE @ SEA, 10-13),
#: `in_progress` (SF @ LAR, 3-0 at 1:31 of the 1st) and `scheduled` (null
#: scores). That single capture is why this constant is a fact rather than an
#: assumption, and why the adapter branches on `status_state` rather than on
#: the sibling `status` field, which is a display string ("9/13 - 1:00 PM EDT").
_STATUS_STATE_FINAL = "final"


class BallDontLieFinalScoreAdapter:
    """Reads completed-game final scores from BALLDONTLIE's `nfl/v1/games`.

    **Bulk by (season, week), deliberately.** One request returns every game
    in a week -- 16 in the real 2026 Week 1 capture, against a `per_page` of
    25 -- so a whole Sunday's finalization costs ONE provider call, not
    sixteen. HQ's directive is explicit that a bulk capability must not be
    converted into one call per game, and this provider's 5 requests/minute
    limit (CONFIRMED from its own `x-ratelimit-limit` header in that same
    capture) makes per-game fetching not merely wasteful but genuinely
    rate-limited at NFL Sunday scale.

    This adapter deliberately does NOT implement `ScheduleAdapter`. A
    `ScheduleEntry` has no score fields, and widening it to carry them would
    push scores into the daily schedule-refresh path, which must never write
    them -- `app.persistence.schedule` keeps `final_score`/`finalized_at` out
    of its writable set on purpose. A separate, narrow return type keeps that
    boundary intact.
    """

    provider_name = "balldontlie"

    def __init__(self, *, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def fetch_week_final_scores(
        self, *, season: int, week: int, per_page: int = 100
    ) -> AdapterResponse[list[FinalScoreLine]]:
        """Fetches every game in (season, week) and returns one
        `FinalScoreLine` per row, final or not -- the caller decides what to
        do with a non-final game, because "this game is not over yet" is real
        information rather than an error, and dropping it here would make a
        still-running game indistinguishable from one the provider does not
        know about.

        `per_page` defaults to 100 rather than the provider's own 25 so a
        16-game NFL week can never be split across pages. Pagination is
        handled honestly rather than assumed away: if the provider still
        reports a `next_cursor`, that is surfaced as a `ProviderDataError`
        instead of silently returning a partial week that a caller would read
        as "these are all the games".
        """
        try:
            response = await self._client.get(
                f"/{_SPORT_PATH}/v1/games",
                params={
                    "seasons[]": [str(season)],
                    "weeks[]": [str(week)],
                    "per_page": str(per_page),
                },
                headers={"Authorization": self._api_key},
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"transport error calling /nfl/v1/games: {exc}", provider=self.provider_name
            ) from exc

        if response.status_code == 401:
            raise ProviderAuthError("invalid or missing API key", provider=self.provider_name)
        if response.status_code == 429:
            raise ProviderRateLimitError("rate limited", provider=self.provider_name)
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"provider returned {response.status_code}", provider=self.provider_name
            )
        if response.status_code != 200:
            raise ProviderDataError(
                f"unexpected status {response.status_code}: {response.text}",
                provider=self.provider_name,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderDataError(
                "response body was not valid JSON", provider=self.provider_name
            ) from exc
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise ProviderDataError(
                "expected an object with a 'data' array", provider=self.provider_name
            )

        meta = body.get("meta") or {}
        if meta.get("next_cursor"):
            raise ProviderDataError(
                f"week {season}/{week} paginated unexpectedly (next_cursor present at "
                f"per_page={per_page}); refusing to return a partial week",
                provider=self.provider_name,
            )

        lines: list[FinalScoreLine] = []
        for row in body["data"]:
            try:
                home = row["home_team"]
                away = row["visitor_team"]
                status_state = row.get("status_state")
                lines.append(
                    FinalScoreLine(
                        provider_game_id=str(row["id"]),
                        home_team=home["abbreviation"],
                        away_team=away["abbreviation"],
                        scheduled_start=_parse_utc(row["date"]),
                        # Copied whole-game fields. Never the quarter splits,
                        # and never a sum of them -- see FinalScoreLine.
                        home_score=row.get("home_team_score"),
                        away_score=row.get("visitor_team_score"),
                        provider_status=row.get("status"),
                        is_final=status_state == _STATUS_STATE_FINAL,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                # Row isolation, same discipline as the SportsDataIO schedule
                # adapter: one malformed row must not lose the other fifteen
                # games in the week.
                _logger.warning(
                    "skipping malformed balldontlie game row (id=%r): %s", row.get("id"), exc
                )
                continue

        return AdapterResponse(value=lines, source=self.provider_name, provider_reported_at=None)


def _parse_utc(value: str) -> datetime:
    """BALLDONTLIE ships ISO-8601 with a `Z` suffix (`2026-09-10T00:20:00.000Z`,
    confirmed from the real capture). `fromisoformat` rejects `Z` before
    Python 3.11, so it is normalized rather than assumed."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
