"""The cache integration boundary (Volume 2 §8).

`CacheBackend` is the interface Redis implements (Phase 3D). Nothing in
`CacheBackend`/`CachingAdapter`/`cache_key` depends on Redis -- 3A/3B/3C
were built and tested against `InMemoryCacheBackend`, and 3D's job was one
Redis-backed implementation of this same interface, wired in behind
`CachingAdapter` with zero change to anything that already calls it. That
held: `RedisCacheBackend` below required no change to any of the three.

`CachingAdapter` wraps any concrete `ProviderAdapter` and makes caching
transparent to callers: they call the same interface method whether or not
a value is cached. This is also the boundary that makes the "swap the
vendor behind an adapter" acceptance test possible -- callers only ever
depend on the adapter's abstract interface, so swapping the wrapped
instance is a one-line change with zero ripple effect elsewhere.

**3D scope note (Mac, 2026-08-13):** this phase is the `RedisCacheBackend`
*implementation and test* only -- no Railway Redis instance exists yet,
by explicit decision, deferred until Phase 3E's worker services need to
prove real cross-process cache sharing (an `InMemoryCacheBackend` cannot
be shared between separate Railway services/processes, which is exactly
what Volume 2 §8's "shared across all users" requirement needs). See
`PROGRESS.md` for the full cost/architecture checkpoint this followed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

_logger = logging.getLogger("sports-intel-layer.cache")


class CacheBackend(ABC):
    """Minimal key/value + TTL contract. Redis (Phase 3D) implements this;
    tests and pre-3D development use `InMemoryCacheBackend`.

    **`errors` (Phase 3F acceptance closure, 2026-08-19):** a plain
    instance counter, incremented by a subclass whenever it internally
    catches a backend-specific failure (e.g. `RedisCacheBackend`'s own
    `redis.exceptions.RedisError` handling below) and falls back to its
    existing fail-open behavior (`get` returns `None`, `set` is a no-op --
    both unchanged from before this counter existed). `InMemoryCacheBackend`
    has no failure mode of its own, so it never increments this -- the
    counter stays meaningful only for backends that actually can fail,
    without needing a backend-specific metrics type."""

    errors: int = 0

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
        self.errors = 0

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


class RedisCacheBackend(CacheBackend):
    """`CacheBackend` implemented against a real (or fake-for-testing)
    Redis, via `redis.asyncio.Redis`'s async client interface -- injected
    at construction time, exactly the same dependency-injection pattern
    every provider adapter already uses for its `httpx.AsyncClient`
    (see e.g. `WeatherAPIWeatherAdapter`). Tests inject
    `fakeredis.aioredis.FakeRedis()` (implements the same interface, no
    real Redis server); production would inject a real
    `redis.asyncio.Redis.from_url(...)` client. This class never imports
    `fakeredis` itself -- only test code does -- so `fakeredis` stays a
    test-only dependency, never a production one.

    No new serialization: `CacheBackend.get`/`set` already only deal in
    `str` (`CachingAdapter` does the JSON encode/decode via each
    `AdapterResponse` pydantic model before/after calling this backend).
    Redis natively stores/returns `bytes` for a plain string SET/GET, so
    the only translation this class does is `bytes.decode()` on read --
    not a new serialization format, just honoring the existing str
    contract against a client whose wire format is bytes.

    TTL: `ttl_seconds` is passed straight through to Redis's native `EX`
    expiry on `SET` -- Redis enforces expiry itself, this class does not
    reimplement TTL logic. Because `ttl_seconds` is a per-call argument
    (not a fixed value on this class), different categories already get
    different TTLs simply by whoever constructs a `CachingAdapter` passing
    a different `ttl_seconds` per category -- this class doesn't need
    category awareness itself to support category-appropriate TTLs; it
    already treats every `set()` call's TTL independently, by design of
    the interface it implements. See `CATEGORY_TTL_SECONDS` below for a
    starting-point mapping the eventual production wiring (3E) can use.

    Error/failure behavior (a real decision, not left implicit): a Redis
    connection/timeout/protocol failure on `get` is treated as a cache
    MISS (returns `None`, logged as a warning) rather than raised --
    "fail open," the standard pattern for a cache that's an optimization,
    not a critical dependency. `CachingAdapter.call` already falls
    through to the real adapter on any cache miss, so a struggling Redis
    degrades the system to "as if nothing were cached" rather than taking
    it down. A `set` failure is similarly swallowed (logged, not raised)
    -- the provider fetch that produced the value to cache already
    succeeded by the time `set` is called; a failed cache write must
    never undo or fail that already-successful response. Only
    `redis.exceptions.RedisError` (the library's own base exception) is
    caught this way -- a bug in this class's own code is not silently
    hidden.
    """

    def __init__(self, client: "redis_asyncio.Redis"):
        self._client = client
        self.errors = 0

    async def get(self, key: str) -> str | None:
        import redis.exceptions

        try:
            value = await self._client.get(key)
        except redis.exceptions.RedisError as exc:
            self.errors += 1
            _logger.warning("RedisCacheBackend.get failed, treating as cache miss: %s", exc)
            return None
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        import redis.exceptions

        try:
            await self._client.set(key, value, ex=ttl_seconds)
        except redis.exceptions.RedisError as exc:
            self.errors += 1
            _logger.warning("RedisCacheBackend.set failed, cache write skipped: %s", exc)


#: Starting-point category -> cache TTL mapping (Volume 2 §8), for
#: categories that don't (yet) have a real dynamic TTL wired in.
#:
#: **Superseded for odds/player_props as of Phase 3E-4F (Decision 4):**
#: `app.workers.odds_worker`/`app.workers.player_props_worker` no longer
#: use these two flat numbers -- they construct each `CachingAdapter` with
#: a per-call TTL from `app.workers.windows.ttl_seconds`, derived from the
#: exact same kickoff-proximity classification that drives their polling
#: cadence (one authoritative policy, not two independent ones). The
#: `"odds"`/`"player_props"` entries below are kept only for any other
#: caller still constructing a flat-TTL `CachingAdapter` directly (there
#: is none in-tree today) -- they are dead weight for the two worker
#: modules themselves, not a second, competing TTL source.
#:
#: `injuries` is now superseded for the real worker too (Phase 3E-5,
#: 2026-08-18): `app.workers.injury_worker` constructs its own
#: `CachingAdapter` with `app.workers.windows.injury_ttl_seconds` (the
#: extended, day-of-week-aware policy -- see that module's own docstring),
#: exactly the same "superseded, kept only for a hypothetical other flat-
#: TTL caller" relationship `odds`/`player_props` already have above -- the
#: value below is no longer this category's real TTL source.
#:
#: Rosters/Schedules/TeamStats/PlayerStats have no dedicated cadence row
#: in Volume 2 §8's table at all -- they're covered by the daily Master
#: Refresh (or, for stats, the event-triggered Postgame Ingestion Worker)
#: -- so their TTL here is bounded by a day, not a shorter polling
#: interval that doesn't exist for them.
CATEGORY_TTL_SECONDS: dict[str, int] = {
    "odds": 60,  # superseded for the real worker -- see docstring above
    "player_props": 60,  # superseded for the real worker -- see docstring above
    "injuries": 300,  # superseded for the real worker -- see docstring above
    "weather": 900,  # CONFIRMED FROM VOLUME 2 §8 -- flat 15-minute worker cadence
    "news": 900,  # CONFIRMED FROM VOLUME 2 §8 -- flat 15-minute worker cadence
    "rosters": 86400,  # ASSUMED -- bounded by daily Master Refresh, no dedicated cadence row
    "schedules": 86400,  # ASSUMED, same reasoning as rosters
    "team_stats": 86400,  # ASSUMED -- bounded by Master Refresh / event-triggered Postgame Ingestion
    "player_stats": 86400,  # ASSUMED, same reasoning as team_stats
}


def cache_key(provider_name: str, method_name: str, *args: Any) -> str:
    """Deterministic cache key for an adapter call. Hashes the argument
    tuple so callers don't need to worry about key-safe characters."""
    raw = json.dumps([provider_name, method_name, args], sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"adapter:{provider_name}:{method_name}:{digest}"


@dataclass
class CacheMetrics:
    """Phase 3F acceptance closure (2026-08-19): the measurable primitives
    Volume 2 §8's own acceptance criterion #3 ("cache hit rate is
    measurable") asked for, previously absent entirely -- TTL behavior was
    real and tested, but nothing counted it. Owned per-`CachingAdapter`
    instance, not globally -- since every worker already constructs one
    `CachingAdapter` per category (confirmed by inspection: `odds_worker`,
    `player_props_worker`, `injury_worker`, `weather_worker`,
    `news_worker`, and Master Refresh's own Schedule/Roster callers each
    build their own instance), this gives independent per-category numbers
    for free, without a second category-keyed metrics store.

    **Definitions (exact, not left implicit):**
    - **hit**: `CacheBackend.get` returned a non-`None` value for this
      call's key -- the provider was NOT called.
    - **miss**: `CacheBackend.get` returned `None` -- for any reason: a
      genuinely new key, an expired entry, or a backend read failure that
      fails open (see `CacheBackend.errors` below for the last case's own
      distinct count). The provider IS then called.
    - **set**: `CacheBackend.set` was called once, after a real provider
      fetch on a miss -- an *attempt*, not a confirmed durable write:
      `RedisCacheBackend.set` already swallows a write failure internally
      (existing fail-open behavior, unchanged), so this call has no way to
      observe whether the value actually landed. `errors` (below) is
      where that distinction lives.
    - **error** (`CacheBackend.errors`, not a field here): a backend-level
      read/write failure that was caught and turned into the existing
      fail-open behavior. Tracked on the backend itself, not here, since
      only backends with an actual failure mode (Redis) can produce one --
      `InMemoryCacheBackend.errors` is always 0.

    Deliberately does **not** compute a hit-rate percentage here -- see
    `hit_rate` below for why."""

    hits: int = 0
    misses: int = 0
    sets: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float | None:
        """`hits / total`, or `None` when `total == 0` -- a tiny/empty
        sample must never be presented as a misleadingly precise
        percentage (e.g. "100%" off one lucky hit). `None` is the honest
        "not enough data yet" signal, consistent with this project's
        null-not-neutral convention elsewhere."""
        if self.total == 0:
            return None
        return self.hits / self.total


class CachingAdapter:
    """Wraps calls to any `ProviderAdapter` subclass with a cache-aside
    strategy. Deliberately generic over which adapter method is called,
    rather than category-specific, so it works uniformly for every adapter
    category without needing category-specific caching code."""

    def __init__(self, adapter: Any, backend: CacheBackend, *, ttl_seconds: int):
        self._adapter = adapter
        self._backend = backend
        self._ttl_seconds = ttl_seconds
        self.metrics = CacheMetrics()

    @property
    def errors(self) -> int:
        """Convenience proxy to the wrapped backend's own error counter --
        see `CacheBackend.errors`/`CacheMetrics`'s own docstring for why
        this lives on the backend, not `CacheMetrics`."""
        return self._backend.errors

    async def call(self, method_name: str, *args: Any, response_model: Any) -> Any:
        """Call `method_name` on the wrapped adapter, transparently caching
        the result. `response_model` is the AdapterResponse[...] pydantic
        model to deserialize a cache hit back into -- required because a
        cached value is stored as JSON text, not a live Python object."""
        key = cache_key(self._adapter.provider_name, method_name, *args)
        cached = await self._backend.get(key)
        if cached is not None:
            self.metrics.hits += 1
            response = response_model.model_validate_json(cached)
            response.from_cache = True
            return response
        self.metrics.misses += 1

        method = getattr(self._adapter, method_name)
        response = await method(*args)
        await self._backend.set(key, response.model_dump_json(), self._ttl_seconds)
        self.metrics.sets += 1
        return response
