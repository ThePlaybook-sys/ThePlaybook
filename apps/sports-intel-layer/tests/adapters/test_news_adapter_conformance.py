"""Conformance tests for the news category, mirroring the pattern already
established for odds/stats/weather."""
import pytest

from tests.adapters.conformance import (
    assert_adapter_identity,
    assert_raises_provider_error,
    assert_returns_envelope,
)
from tests.adapters.fakes import FakeNewsAdapter


@pytest.mark.asyncio
async def test_fake_news_adapter_conforms_to_interface():
    adapter = FakeNewsAdapter()
    assert_adapter_identity(adapter)
    response = await assert_returns_envelope(adapter, "fetch_news", "Chiefs")
    assert response.value[0].related_teams == ["Chiefs"]


@pytest.mark.asyncio
async def test_fake_news_adapter_raises_provider_error_on_failure():
    adapter = FakeNewsAdapter(fail=True)
    await assert_raises_provider_error(adapter, "fetch_news", "Chiefs")
