"""Fake adapters used to prove the conformance suite and cache boundary
work correctly, without depending on any real vendor. No Phase 3B/3C
vendor-specific adapter exists yet (Mac's explicit instruction: Phase 3A
is provider-independent) -- these fakes stand in for "some adapter
implementing the interface" until a real one does.
"""
from __future__ import annotations

from app.adapters.base import OddsAdapter
from app.adapters.errors import ProviderUnavailableError
from app.adapters.models import AdapterResponse, OddsLine


class FakeOddsAdapterV1(OddsAdapter):
    provider_name = "fake_provider_v1"

    def __init__(self, *, fail: bool = False):
        self._fail = fail

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
        return AdapterResponse(value=lines, source=self.provider_name)


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
