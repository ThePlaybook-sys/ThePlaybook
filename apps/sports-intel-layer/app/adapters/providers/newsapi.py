"""NewsAPI adapter (Volume 2 §8, Phase 3C-i).

Implements `NewsAdapter` against NewsAPI.org's documented `/v2/everything`
contract -- Volume 2 §8's current default vendor for News/sentiment (GNews
is the documented fallback; Mac has explicitly held back any primary/
fallback swap pending a coverage/latency/licensing comparison, so this
targets NewsAPI, not GNews).

Per Mac's explicit 3C scope boundary (2026-08-11): this adapter stops at
the normalized `NewsArticle` / cache boundary. It does **not** write to
Supabase -- there is no persistence target for News in this codebase yet
(Volume 3 §4 lists four append-only snapshot tables mirroring
`odds_snapshots`'s shape; news isn't one of them), and Mac explicitly
deferred deciding that schema question to Milestone F, after the
NewsAPI-vs-GNews and commercial-storage-terms questions are resolved.
`daily_game_intelligence.news` is a working/current-state field, not
history, and this adapter has no opinion about it either.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from app.adapters.base import NewsAdapter
from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.models import AdapterResponse, NewsArticle

#: ASSUMED: NewsAPI error-body `code` values for auth problems. Not
#: independently re-verified via a live fetch this session.
_AUTH_ERROR_CODES = {"apiKeyMissing", "apiKeyInvalid", "apiKeyDisabled", "apiKeyExhausted"}
_RATE_LIMIT_ERROR_CODES = {"rateLimited"}


def _error_code(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict):
        return data.get("code")
    return None


class NewsAPINewsAdapter(NewsAdapter):
    provider_name = "newsapi"

    def __init__(self, *, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def fetch_news(self, team: str | None = None) -> AdapterResponse[list[NewsArticle]]:
        #: ASSUMED query construction -- Volume 2 §8 doesn't specify how a
        #: query narrows to a team; NFL-qualifying the search keeps a bare
        #: team name (e.g. "Eagles") from pulling in unrelated news.
        query = f"{team} NFL" if team else "NFL"

        try:
            response = await self._client.get(
                "/v2/everything",
                params={
                    "apiKey": self._api_key,
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                },
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"transport error calling /v2/everything: {exc}", provider=self.provider_name
            ) from exc

        if response.status_code == 401:
            raise ProviderAuthError("invalid or missing API key", provider=self.provider_name)
        if response.status_code == 429:
            raise ProviderRateLimitError("rate limited", provider=self.provider_name)
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"provider returned {response.status_code}", provider=self.provider_name
            )
        if response.status_code == 400:
            code = _error_code(response)
            if code in _AUTH_ERROR_CODES:
                raise ProviderAuthError("invalid or missing API key", provider=self.provider_name)
            if code in _RATE_LIMIT_ERROR_CODES:
                raise ProviderRateLimitError("rate limited", provider=self.provider_name)
            raise ProviderDataError(f"bad request: {response.text}", provider=self.provider_name)
        if response.status_code != 200:
            raise ProviderDataError(
                f"unexpected status {response.status_code}: {response.text}",
                provider=self.provider_name,
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderDataError("response body was not valid JSON", provider=self.provider_name) from exc
        if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
            raise ProviderDataError("expected an object with an 'articles' array", provider=self.provider_name)

        articles: list[NewsArticle] = []
        latest_published: datetime | None = None
        try:
            for raw in data["articles"]:
                published_at = datetime.fromisoformat(raw["publishedAt"].replace("Z", "+00:00"))
                if latest_published is None or published_at > latest_published:
                    latest_published = published_at
                source = raw.get("source") or {}
                articles.append(
                    NewsArticle(
                        headline=raw["title"],
                        url=raw["url"],
                        source=source.get("name", "unknown"),
                        published_at=published_at,
                        summary=raw.get("description"),
                        related_teams=[team] if team else [],
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderDataError(f"malformed article payload: {exc}", provider=self.provider_name) from exc

        return AdapterResponse(
            value=articles,
            source=self.provider_name,
            provider_reported_at=latest_published,
        )
