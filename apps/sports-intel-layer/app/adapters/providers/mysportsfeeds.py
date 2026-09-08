"""MySportsFeeds adapters (Phase 8.2 Player/Roster/Depth Activation,
2026-09-08).

Implements `RosterAdapter` against MySportsFeeds' real `/nfl/players.json`
endpoint -- the provider-neutral path the Phase 8.2 audit
(`docs/ops/phase-8.2-player-identity-roster-depth-audit-2026-09-08.md`)
designed and the two Phase 8.2 diagnostics (`docs/ops/phase-8.2-
mysportsfeeds-players-diagnostic-2026-09-08.md`, `docs/ops/phase-8.2-
mysportsfeeds-players-diagnostic-2-2026-09-08.md`) confirmed live. Matches
the existing `ProviderAdapter` pattern exactly: nothing outside
`app.adapters` needs to know this is MySportsFeeds rather than
SportsDataIO behind `RosterAdapter`'s interface.

Provenance, since Mac's explicit instruction is to never present an
assumption as vendor fact:

- Base URL (`https://api.mysportsfeeds.com/v2.1/pull`), HTTP Basic auth
  (`username=api_key`, `password="MYSPORTSFEEDS"` literal), and the
  `players.json` feed's URL shape (`season: false`, no path segment --
  confirmed from the official `mysportsfeeds-node` npm package's own
  `API_v2_0.js`) are CONFIRMED from the same provenance tier already
  used for `TheOddsApiOddsAdapter`/`BallDontLieInjuryAdapter` -- this
  workspace's own egress policy blocks `api.mysportsfeeds.com` directly.
- The real response shape (`{"lastUpdatedOn", "players": [{"player":
  {...}, "teamAsOfDate": {...}}], "references"}`) is CONFIRMED from a
  real, live DEV call (Phase 8.2 diagnostic #2, 2026-09-08): HTTP 200,
  2,322 real players, every field this adapter reads below observed
  directly in that response, not guessed from SDK models.

**This feed returns the entire league, unfiltered -- no server-side
team parameter is documented in the vendored SDK's own feed definition,
and no undocumented filter was tested (Phase 8.2 HQ guardrail: "Do not
test undocumented filters").** `fetch_roster(team)` therefore fetches
the whole-league payload and filters to the requested team's
abbreviation client-side, in Python -- not a second live call, not a
server-side filter this adapter assumes exists.

**No depth/lineup data of any kind exists in this feed** (confirmed
absent from every real player entry observed across both diagnostics).
Every `RosterEntry.depth_chart_rank` this adapter produces is `None` --
never invented, never backfilled from a different feed. Depth/lineup
role is a separate MySportsFeeds feed (`lineup.json`, already
live-confirmed real in the 2026-09-03 gap test) and a separate,
not-yet-built persistence path -- this adapter does not attempt it,
matching Phase 8.2's own "keep player identity / roster membership /
depth-lineup role / game participation separate" architecture rule.
"""
from __future__ import annotations

import base64
import logging

import httpx

from app.adapters.base import RosterAdapter
from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.models import AdapterResponse, RosterEntry
from app.persistence.player_season_stats import PlayerSeasonStatLine

_logger = logging.getLogger("sports-intel-layer.adapters.mysportsfeeds")

#: CONFIRMED literal, not a real password -- the official `mysportsfeeds-node`
#: SDK's own `authenticate()` usage example, same provenance as the two
#: reverted Phase 8.2 diagnostic probes that already validated this scheme
#: live.
_MSF_PASSWORD = "MYSPORTSFEEDS"

_PLAYERS_PATH = "/nfl/players.json"


def _auth_header(api_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{api_key}:{_MSF_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


class MySportsFeedsRosterAdapter(RosterAdapter):
    provider_name = "mysportsfeeds"

    def __init__(self, *, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def fetch_roster(self, team: str) -> AdapterResponse[list[RosterEntry]]:
        """Fetches the whole-league `players.json` payload, then filters
        to `team` (matched against each player's real `currentTeam.
        abbreviation`) client-side. `depth_chart_rank` is always `None`
        on every returned entry -- this feed carries no depth data,
        never inferred here."""
        try:
            response = await self._client.get(
                _PLAYERS_PATH,
                params={"force": "false"},
                headers=_auth_header(self._api_key),
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"transport error calling {_PLAYERS_PATH}: {exc}", provider=self.provider_name
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
                f"unexpected status {response.status_code}: {response.text}", provider=self.provider_name
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderDataError("response body was not valid JSON", provider=self.provider_name) from exc
        if not isinstance(data, dict) or not isinstance(data.get("players"), list):
            raise ProviderDataError(
                "expected an object with a 'players' array", provider=self.provider_name
            )

        entries: list[RosterEntry] = []
        for row in data["players"]:
            try:
                player = row["player"]
                current_team = player.get("currentTeam") or {}
                if current_team.get("abbreviation") != team:
                    continue
                first_name = player["firstName"]
                last_name = player["lastName"]
                entries.append(
                    RosterEntry(
                        team=team,
                        player_external_id=str(player["id"]),
                        player_name=f"{first_name} {last_name}".strip(),
                        position=player["primaryPosition"],
                        depth_chart_rank=None,
                    )
                )
            except (KeyError, TypeError) as exc:
                _logger.warning(
                    "skipping malformed mysportsfeeds player row (id=%r): %s",
                    row.get("player", {}).get("id") if isinstance(row.get("player"), dict) else None,
                    exc,
                )
                continue

        last_updated_on = data.get("lastUpdatedOn")
        provider_reported_at = None
        if isinstance(last_updated_on, str):
            try:
                from datetime import datetime

                provider_reported_at = datetime.fromisoformat(last_updated_on.replace("Z", "+00:00"))
            except ValueError:
                # Never fabricated -- an unparseable timestamp stays None
                # rather than guessing a format.
                provider_reported_at = None

        return AdapterResponse(
            value=entries, source=self.provider_name, provider_reported_at=provider_reported_at
        )


_PLAYER_STATS_TOTALS_PATH_TEMPLATE = "/nfl/{season}/player_stats_totals.json"


class MySportsFeedsPlayerSeasonStatsAdapter:
    """MySportsFeeds `seasonal_player_stats` (`player_stats_totals.json`)
    adapter -- Phase 8.3D (2026-09-08), built against the real payload
    shape the Phase 8.3C diagnostic confirmed live (HTTP 200, team=NE,
    season=2025-2026-regular, 43 real player entries recovered; see
    `docs/ops/phase-8.3c-player-stats-diagnostic-retry-2026-09-08.md`
    and the committed fixture `docs/ops/fixtures/phase-8.3c-msf-player-
    stats-totals-ne-2025-2026-partial-2026-09-08.json`). Season-scoped,
    not game-scoped -- deliberately not a `PlayerStatsAdapter` subclass
    (that ABC's `fetch_player_stats(game_external_id)` contract is
    explicitly game-scoped, per its own docstring), matching how
    `MySportsFeedsTeamSeasonStatsAdapter`-equivalent parsing in Phase
    8.3A was also kept outside the game-scoped `TeamStatsAdapter` ABC.

    **This class is the only place in the codebase that knows
    MySportsFeeds' real response shape for this feed** -- everything
    downstream (persistence, tests) only ever sees provider-neutral
    `PlayerSeasonStatLine` objects. A future NBA or other-provider
    season-stats source would get its own adapter class producing the
    same `PlayerSeasonStatLine` shape; nothing in `app.persistence.
    player_season_stats` would need to change.

    **`team` query param provenance and honesty, carried forward from
    Phase 8.3C's own disclosure**: sourced from the vendored SDK
    README's documented usage example for the ancestor v1.x feed in the
    same player-stats-totals family, not a v2.x-confirmed example when
    first used -- but Phase 8.3C's real live call CONFIRMED it is
    honored server-side (a 166,159-byte response consistent with one
    team's roster, not the whole league). No longer merely inferred.

    **`gamesStarted` is real provider data, not MANSA-verified
    participation evidence -- explicitly flagged, not silently trusted.**
    Phase 8.3C's real capture showed `stats.miscellaneous.gamesStarted`
    returning `0` for all 43 real players sampled, including obvious
    starters (e.g. Stefon Diggs, 85 receptions across 14 games played,
    still shows `gamesStarted: 0`). This adapter does not special-case,
    correct, or drop that field -- the entire `stats` dict passes through
    verbatim, unfiltered, matching every other stats adapter in this
    codebase -- but no code in this project may treat `gamesStarted` as a
    trustworthy signal of who actually started a game until this is
    independently reconciled against a real, confirmed-working
    participation source (`lineup.json`'s own "expected" lineup is
    pre-game projection, not confirmed participation either -- see the
    2026-09-08 Player/Team Performance Data Audit's own §2)."""

    provider_name = "mysportsfeeds"

    def __init__(self, *, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def fetch_player_season_stats(
        self, *, team: str, season: str
    ) -> AdapterResponse[list[PlayerSeasonStatLine]]:
        """Fetches `player_stats_totals.json` for one team/season and
        parses it into provider-neutral `PlayerSeasonStatLine` objects.
        `PlayerSeasonStatLine.stats` is the real per-player `stats` dict
        exactly as MySportsFeeds returns it (passing/rushing/receiving/
        tackles/interceptions/fumbles/kickoffReturns/puntReturns/
        fieldGoals/punting/kickoffs/extraPointAttempts/twoPointAttempts/
        miscellaneous/snapCounts/gamesPlayed, per Phase 8.3C's real
        confirmed capture) -- not reshaped, not filtered field-by-field."""
        path = _PLAYER_STATS_TOTALS_PATH_TEMPLATE.format(season=season)
        try:
            response = await self._client.get(
                path,
                params={"team": team, "force": "false"},
                headers=_auth_header(self._api_key),
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"transport error calling {path}: {exc}", provider=self.provider_name
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
                f"unexpected status {response.status_code}: {response.text}", provider=self.provider_name
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderDataError("response body was not valid JSON", provider=self.provider_name) from exc
        if not isinstance(data, dict) or not isinstance(data.get("playerStatsTotals"), list):
            raise ProviderDataError(
                "expected an object with a 'playerStatsTotals' array", provider=self.provider_name
            )

        lines: list[PlayerSeasonStatLine] = []
        for row in data["playerStatsTotals"]:
            try:
                player_id = row["player"]["id"]
                stats = row["stats"]
                if not isinstance(stats, dict):
                    raise TypeError("stats was not an object")
                lines.append(PlayerSeasonStatLine(player=str(player_id), stats=stats))
            except (KeyError, TypeError) as exc:
                _logger.warning(
                    "skipping malformed mysportsfeeds player_stats_totals row (id=%r): %s",
                    row.get("player", {}).get("id") if isinstance(row.get("player"), dict) else None,
                    exc,
                )
                continue

        last_updated_on = data.get("lastUpdatedOn")
        provider_reported_at = None
        if isinstance(last_updated_on, str):
            try:
                from datetime import datetime

                provider_reported_at = datetime.fromisoformat(last_updated_on.replace("Z", "+00:00"))
            except ValueError:
                # Never fabricated -- an unparseable timestamp stays None
                # rather than guessing a format.
                provider_reported_at = None

        return AdapterResponse(
            value=lines, source=self.provider_name, provider_reported_at=provider_reported_at
        )


__all__ = ["MySportsFeedsRosterAdapter", "MySportsFeedsPlayerSeasonStatsAdapter"]
