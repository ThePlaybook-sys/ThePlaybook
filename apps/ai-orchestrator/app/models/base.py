"""The provider-neutral model adapter interface (Milestone 4.3).

`Agent -> Model Router -> ModelAdapter -> [OpenAI / Anthropic / Fake]` --
the approved architecture. Every concrete adapter implements exactly this
one method; the rest of the orchestrator (router, retry engine, and
eventually agents) depends only on this abstract contract, never on a
concrete adapter class or a raw vendor SDK/HTTP response object -- the
identical discipline Volume 2 Section 8 already established for sports
data provider adapters, applied here to model providers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.types import ModelRequest, ModelResponse


class ModelAdapter(ABC):
    """One provider, one model family, one implementation of `complete`.
    A single call is exactly one attempt against exactly one model --
    retry/fallback across attempts or across models is the retry engine's
    job (`app.models.retry_policy`), never an individual adapter's."""

    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Makes exactly one attempt. Returns a `ModelResponse` on
        success. On failure, raises exclusively from
        `app.models.errors` -- never a raw vendor SDK/HTTP exception,
        never `asyncio.TimeoutError` directly (wrap it as
        `ModelTimeoutError`)."""
        raise NotImplementedError
