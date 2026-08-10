"""Conformance tests for the stats categories (Volume 3's player_stats/
team_stats tables), added because reviewing the SportsDataIO cadence
question surfaced that Phase 3A's original adapter set never covered
these two categories at all -- only odds, props, injuries, weather,
rosters, schedules, and news. Same pattern as the odds conformance suite.
"""
import pytest

from tests.adapters.conformance import (
    assert_adapter_identity,
    assert_raises_provider_error,
    assert_returns_envelope,
)
from tests.adapters.fakes import FakeTeamStatsAdapter


@pytest.mark.asyncio
async def test_fake_team_stats_adapter_conforms_to_interface():
    adapter = FakeTeamStatsAdapter()
    assert_adapter_identity(adapter)
    response = await assert_returns_envelope(adapter, "fetch_team_stats", "game-1")
    assert len(response.value) == 2
    assert {line.team for line in response.value} == {"home", "away"}


@pytest.mark.asyncio
async def test_fake_team_stats_adapter_raises_provider_error_on_failure():
    adapter = FakeTeamStatsAdapter(fail=True)
    await assert_raises_provider_error(adapter, "fetch_team_stats", "game-1")
