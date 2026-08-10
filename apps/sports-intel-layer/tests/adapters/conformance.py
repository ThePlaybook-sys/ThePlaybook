"""Adapter conformance suite (Volume 2 §8's testing requirement: "Adapter
interface conformance tests -- every adapter implements the full shared
interface, verified automatically, not by code review alone").

Every concrete adapter, for every category, should be checked against
these assertions before it's considered done -- vendor-specific adapters
built in Phase 3B/3C reuse this module rather than re-deriving these
checks per vendor.
"""
from __future__ import annotations

import inspect

from app.adapters.base import ProviderAdapter
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse


def assert_adapter_identity(adapter: ProviderAdapter) -> None:
    assert isinstance(adapter.provider_name, str) and adapter.provider_name, (
        "adapter.provider_name must be a non-empty string"
    )
    assert adapter.category is not None, "adapter.category must be set"


async def assert_returns_envelope(adapter, method_name: str, *args):
    method = getattr(adapter, method_name)
    assert inspect.iscoroutinefunction(method), f"{method_name} must be async"
    response = await method(*args)
    assert isinstance(response, AdapterResponse), (
        f"{method_name} must return AdapterResponse, got {type(response)}"
    )
    assert response.source == adapter.provider_name, (
        "AdapterResponse.source must identify the adapter, not leak a raw vendor string"
    )
    return response


async def assert_raises_provider_error(adapter, method_name: str, *args) -> None:
    """A failing adapter call must raise from the ProviderError hierarchy,
    never a raw vendor/HTTP exception -- this is the actual enforcement of
    "no external service needs to know which vendor sits behind an
    adapter," extended to error handling, not just data shape."""
    method = getattr(adapter, method_name)
    raised = None
    try:
        await method(*args)
    except ProviderError as exc:
        raised = exc
    except Exception as exc:  # noqa: BLE001 -- this branch IS the failure condition
        raise AssertionError(
            f"{method_name} raised {type(exc).__name__}, not a ProviderError subclass"
        ) from exc
    assert raised is not None, f"{method_name} was expected to raise but didn't"
