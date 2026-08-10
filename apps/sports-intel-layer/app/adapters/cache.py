"""The cache integration boundary (Volume 2 §8).

`CacheBackend` is the interface Redis will implement in Phase 3D. Nothing
here depends on Redis -- 3A/3B/3C can be built and tested against
`InMemoryCacheBackend`, and 3D's only job is one Redis-backed implementation
of this same interface, wired in behind `CachingAdapter` with zero change to
anything that already calls it.

`CachingAdapter` wraps any concrete `ProviderAdapter` and makes caching
transparent to callers: they call the same interface method whether or not
a value is cached. This is also the boundary that makes the "swap the
vendor behind an adapter" acceptance test possible -- callers only ever
depend on the adapter's abstract interface, so swapping the wrapped
instance is a one-line change with zero ripple effect elsewhere.
"""
from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from typing import Any, Callable


class CacheBackend(ABC):
    """Minimal key/value + TTL contract. Redis (Phase 3D) implements this;
    tests and pre-3D development use `InMemoryCacheBackend`."""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Return the cached value, or None on a miss (including expiry)."""

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store `value` under `key`, expiring after `ttl_seconds`."""


class InMemoryCacheBackend(CacheBackend):
    """A trivial in-process cache backend with no external dependency --
    used for tests, and for any Phase 3 development before Redis (3D) is
    wired in. Never used in staging/production; TTL correctness there is
    Redis's responsibility, not this class's."""

    def __init__(self, *, clock: Callable[[], float] | None = None):
        self._store: dict[str, tuple[str, float]] = {}
        self._clock = clock or time.monotonic

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if self._clock() >= expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._store[key] = (value, self._clock() + ttl_seconds)


def cache_key(provider_name: str, method_name: str, *args: Any) -> str:
    """Deterministic cache key for an adapter call. Hashes the argument
    tuple so callers don't need to worry about key-safe characters."""
    raw = json.dumps([provider_name, method_name, args], sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"adapter:{provider_name}:{method_name}:{digest}"


class CachingAdapter:
    """Wraps calls to any `ProviderAdapter` subclass with a cache-aside
    strategy. Deliberately generic over which adapter method is called,
    rather than category-specific, so it works uniformly for every adapter
    category without needing category-specific caching code."""

    def __init__(self, adapter: Any, backend: CacheBackend, *, ttl_seconds: int):
        self._adapter = adapter
        self._backend = backend
        self._ttl_seconds = ttl_seconds

    async def call(self, method_name: str, *args: Any, response_model: Any) -> Any:
        """Call `method_name` on the wrapped adapter, transparently caching
        the result. `response_model` is the AdapterResponse[...] pydantic
        model to deserialize a cache hit back into -- required because a
        cached value is stored as JSON text, not a live Python object."""
        key = cache_key(self._adapter.provider_name, method_name, *args)
        cached = await self._backend.get(key)
        if cached is not None:
            response = response_model.model_validate_json(cached)
            response.from_cache = True
            return response

        method = getattr(self._adapter, method_name)
        response = await method(*args)
        await self._backend.set(key, response.model_dump_json(), self._ttl_seconds)
        return response
