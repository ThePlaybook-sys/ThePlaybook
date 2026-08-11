"""Conformance tests for the weather category, mirroring the pattern
already established for odds/stats (test_odds_adapter_conformance.py,
test_stats_adapter_conformance.py)."""
from datetime import datetime, timezone

import pytest

from tests.adapters.conformance import (
    assert_adapter_identity,
    assert_raises_provider_error,
    assert_returns_envelope,
)
from tests.adapters.fakes import FakeWeatherAdapter

KICKOFF = datetime(2026, 9, 14, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_fake_weather_adapter_conforms_to_interface():
    adapter = FakeWeatherAdapter()
    assert_adapter_identity(adapter)
    response = await assert_returns_envelope(adapter, "fetch_weather", "game-1", KICKOFF)
    assert response.value.game_external_id == "game-1"


@pytest.mark.asyncio
async def test_fake_weather_adapter_raises_provider_error_on_failure():
    adapter = FakeWeatherAdapter(fail=True)
    await assert_raises_provider_error(adapter, "fetch_weather", "game-1", KICKOFF)
