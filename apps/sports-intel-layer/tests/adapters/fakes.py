"""Fake adapters used to prove the conformance suite and cache boundary
work correctly, without depending on any real vendor. No Phase 3B/3C
vendor-specific adapter exists yet (Mac's explicit instruction: Phase 3A
is provider-independent) -- these fakes stand in for "some adapter
implementing the interface" until a real one does.
"""
from __future__ import annotations

from datetime import datetime

from app.adapters.base import OddsAdapter, TeamStatsAdapter
from app.adapters.errors import ProviderUnavailableError
from app.adapters.models import AdapterResponse, OddsLine, TeamStatLine


class FakeOddsAdapterV1(OddsAdapter):
    provider_name = "fake_provider_v1"

    def __init__(self, *, fail: bool = False, provider_reported_at: datetime | None = None):
        self._fail = fail
        # Optional, mirroring the real-world case: some vendors expose a
        # "line last moved at" timestamp, some don't. Defaults to None so
        # tests exercise both the supplied and not-supplied cases explicitly
        # rather than only ever the happy path.
        self._provider_reported_at = provider_reported_at

    async def fetch_odds(self, game_external_ids: list[str]) -> AdapterResponse[list[OddsLine]]:
        if self._fail:
            raise ProviderUnavailableError("simulated outage", provider=self.provider_name)
        lines = [
            OddsLine(
                game_external_id=game_id,
                sportsbook="fakebook",
                market_type="moneyline",
                line_data={"home": -110, "away": -110},
            )
            for game_id in game_external_ids
        ]
        return AdapterResponse(
            value=lines,
            source=self.provider_name,
            provider_reported_at=self._provider_reported_at,
        )


class FakeOddsAdapterV2(OddsAdapter):
    """A second, independently-implemented fake -- used specifically to
    prove a vendor swap requires zero change outside the adapter itself
    (Phase 3's actual acceptance criterion for the pattern, not just an
    assertion about it)."""

    provider_name = "fake_provider_v2"

    async def fetch_odds(self, game_external_ids: list[str]) -> AdapterResponse[list[OddsLine]]:
        lines = [
            OddsLine(
                game_external_id=game_id,
                sportsbook="anotherbook",
                market_type="moneyline",
                line_data={"home": -105, "away": -115},
            )
            for game_id in game_external_ids
        ]
        return AdapterResponse(value=lines, source=self.provider_name)


class FakeTeamStatsAdapter(TeamStatsAdapter):
    provider_name = "fake_stats_provider"

    def __init__(self, *, fail: bool = False):
        self._fail = fail

    async def fetch_team_stats(self, game_external_id: str) -> AdapterResponse[list[TeamStatLine]]:
        if self._fail:
            raise ProviderUnavailableError("simulated outage", provider=self.provider_name)
        lines = [
            TeamStatLine(
                game_external_id=game_external_id,
                team="home",
                stats={"points": 24, "total_yards": 350},
            ),
            TeamStatLine(
                game_external_id=game_external_id,
                team="away",
                stats={"points": 17, "total_yards": 290},
            ),
        ]
        return AdapterResponse(value=lines, source=self.provider_name)
