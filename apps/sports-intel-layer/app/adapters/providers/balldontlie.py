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
from typing import Callable

import httpx

from app.adapters.base import InjuryAdapter
from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.models import AdapterResponse, InjuryReport

_logger = logging.getLogger("sports-intel-layer.adapters.balldontlie")


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
                "/nfl/v1/player_injuries",
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
