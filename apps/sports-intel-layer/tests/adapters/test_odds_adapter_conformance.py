import pytest

from tests.adapters.conformance import (
    assert_adapter_identity,
    assert_raises_provider_error,
    assert_returns_envelope,
)
from tests.adapters.fakes import FakeOddsAdapterV1


@pytest.mark.asyncio
async def test_fake_odds_adapter_conforms_to_interface():
    adapter = FakeOddsAdapterV1()
    assert_adapter_identity(adapter)
    response = await assert_returns_envelope(adapter, "fetch_odds", ["game-1", "game-2"])
    assert len(response.value) == 2
    assert {line.game_external_id for line in response.value} == {"game-1", "game-2"}


@pytest.mark.asyncio
async def test_fake_odds_adapter_raises_provider_error_on_failure():
    adapter = FakeOddsAdapterV1(fail=True)
    await assert_raises_provider_error(adapter, "fetch_odds", ["game-1"])
