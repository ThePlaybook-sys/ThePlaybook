"""GNews adapter (Phase 8.0.5, Data Activation Pass 1, 2026-09-07).

Implements `NewsAdapter` against GNews's real `/api/v4/search` endpoint --
built under HQ's explicit instruction to use GNews (not NewsAPI) for this
DEV activation pass. `NEWSAPI_API_KEY` is not configured anywhere in this
environment (confirmed by a live Railway variable check this same
session); `GNEWS_API_KEY` is. `app.workers.news_worker`'s own hardcoded
default (`NewsAPINewsAdapter`) is deliberately left completely
UNCHANGED by this file -- Volume 2 §8's NewsAPI-vs-GNews vendor decision
remains genuinely undecided (Mac's 2026-08-11 hold, still open per
`docs/ops/news-provider-decision-record.md`), so this adapter is used by
explicit injection via `run_news_worker`'s existing `news_adapter`
dependency-injection seam, never by changing that worker's own default
construction. This is "add the smallest invocation path needed," not "pick
a vendor."

Provenance: endpoint shape, params, and response schema (`articles:
[{id, title, description, content, url, image, publishedAt, lang,
source: {id, name, url, country}}]`) are CONFIRMED FROM PUBLIC SOURCES,
carried forward verbatim from the 2026-09-03 News Provider Validation's
own temporary diagnostic (`docs/ops/news-provider-validation-gnews-2026-09-03.md`)
-- the official `gnews-io/gnews-io-js` client's documented base URL/params
and multiple independent WebSearch-indexed sources for the `apikey`
query-param name and plan limits. That validation ran against GNews's
Free plan, not the committed Essential subscription (HQ's own correction,
2026-09-04) -- this adapter makes no assumption about which tier is
currently active; whichever tier `GNEWS_API_KEY` is provisioned on is
whatever this adapter actually gets.

**A real, disclosed finding from that same validation, not re-derived
here:** GNews's `source.country` field is present on every article but
this adapter does not filter on it -- the validation found 5 of 6 results
for one query were a low-relevance foreign-country source, an actionable
future improvement (`country=us` or a source allowlist), not implemented
in this pass to keep this adapter the smallest change that makes GNews
usable at all.
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

#: Multi-sport readiness (Phase 8.0.5 Data Activation Pass 2, 2026-09-07,
#: HQ's locked sport-agnostic architecture rule): named, not inlined, so
#: this adapter's one NFL-specific choice is a single visible edit point
#: -- matching `app.adapters.providers.the_odds_api._SPORT_KEY`'s own
#: precedent. Real per-sport query qualification would need this adapter
#: (and `NewsAPINewsAdapter`, unchanged this pass) to accept a sport
#: parameter threaded from the caller -- real NBA-support work, not
#: authorized or begun this pass.
_SPORT_QUALIFIER = "NFL"


class GNewsNewsAdapter(NewsAdapter):
    provider_name = "gnews"

    def __init__(self, *, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def fetch_news(self, team: str | None = None) -> AdapterResponse[list[NewsArticle]]:
        #: Same query-construction convention as NewsAPINewsAdapter (ASSUMED --
        #: Volume 2 §8 doesn't specify how a query narrows to a team; sport-
        #: qualifying a bare team name keeps it from pulling unrelated news).
        query = f"{team} {_SPORT_QUALIFIER}" if team else _SPORT_QUALIFIER

        try:
            response = await self._client.get(
                "/api/v4/search",
                params={"apikey": self._api_key, "q": query, "lang": "en", "sortby": "publishedAt"},
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"transport error calling /api/v4/search: {exc}", provider=self.provider_name
            ) from exc

        if response.status_code == 401 or response.status_code == 403:
            raise ProviderAuthError("invalid or missing API key", provider=self.provider_name)
        if response.status_code == 429:
            raise ProviderRateLimitError("rate limited", provider=self.provider_name)
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"provider returned {response.status_code}", provider=self.provider_name
            )
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


__all__ = ["GNewsNewsAdapter"]
