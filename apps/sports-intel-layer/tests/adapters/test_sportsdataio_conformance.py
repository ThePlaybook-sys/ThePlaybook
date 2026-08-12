"""Conformance tests for the Roster/Schedule/Injury/PlayerStats categories
(Phase 3C-ii), same pattern as test_stats_adapter_conformance.py's
TeamStatsAdapter coverage -- extended here because 3C-ii is the first
milestone to build concrete adapters for these four.
"""
import pytest

from tests.adapters.conformance import (
    assert_adapter_identity,
    assert_raises_provider_error,
    assert_returns_envelope,
)
from tests.adapters.fakes import (
    FakeInjuryAdapter,
    FakePlayerStatsAdapter,
    FakeRosterAdapter,
    FakeScheduleAdapter,
)


@pytest.mark.asyncio
async def test_fake_roster_adapter_conforms_to_interface():
    adapter = FakeRosterAdapter()
    assert_adapter_identity(adapter)
    response = await assert_returns_envelope(adapter, "fetch_roster", "KC")
    assert response.value[0].team == "KC"


@pytest.mark.asyncio
async def test_fake_roster_adapter_raises_provider_error_on_failure():
    adapter = FakeRosterAdapter(fail=True)
    await assert_raises_provider_error(adapter, "fetch_roster", "KC")


@pytest.mark.asyncio
async def test_fake_schedule_adapter_conforms_to_interface():
    adapter = FakeScheduleAdapter()
    assert_adapter_identity(adapter)
    response = await assert_returns_envelope(adapter, "fetch_schedule", "2026REG")
    assert response.value[0].status == "scheduled"


@pytest.mark.asyncio
async def test_fake_schedule_adapter_raises_provider_error_on_failure():
    adapter = FakeScheduleAdapter(fail=True)
    await assert_raises_provider_error(adapter, "fetch_schedule", "2026REG")


@pytest.mark.asyncio
async def test_fake_injury_adapter_conforms_to_interface():
    adapter = FakeInjuryAdapter()
    assert_adapter_identity(adapter)
    response = await assert_returns_envelope(adapter, "fetch_injuries", "KC")
    assert response.value[0].team == "KC"


@pytest.mark.asyncio
async def test_fake_injury_adapter_raises_provider_error_on_failure():
    adapter = FakeInjuryAdapter(fail=True)
    await assert_raises_provider_error(adapter, "fetch_injuries", None)


@pytest.mark.asyncio
async def test_fake_player_stats_adapter_conforms_to_interface():
    adapter = FakePlayerStatsAdapter()
    assert_adapter_identity(adapter)
    response = await assert_returns_envelope(adapter, "fetch_player_stats", "game-1")
    assert response.value[0].game_external_id == "game-1"


@pytest.mark.asyncio
async def test_fake_player_stats_adapter_raises_provider_error_on_failure():
    adapter = FakePlayerStatsAdapter(fail=True)
    await assert_raises_provider_error(adapter, "fetch_player_stats", "game-1")
