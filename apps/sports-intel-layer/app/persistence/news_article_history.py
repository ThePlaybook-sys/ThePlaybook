"""Insert-once-per-article persistence for news_article_history
(Volume 3 §4.4) -- 2026 Data Preservation Readiness Plan, pre-9/9
minimum implementation.

**Preserves `ingested_at` -- the one fact nothing in this codebase
records today.** `daily_game_intelligence.news` (Phase 3E-7) is
current-state-only and stays completely untouched by this module; this
is new, additive history written alongside it, never instead of it.

**Insert-once, not "every poll is a new row."** Unlike
`odds_snapshots`/`injury_reports`/`weather_snapshots` (where a changed
value each poll is a meaningful new row), a news article's own content
is typically immutable once published -- writing the same still-current
article again on every 15-minute News Worker cycle would produce pure
duplicate rows, not real history. This module upserts against the
`(provider_name, article_url)` unique index with
`Prefer: resolution=ignore-duplicates`, so a re-sighted article is a
silent no-op: the original row's `ingested_at` (the true "when MANSA
first learned this" moment) is never touched or overwritten.

Deliberately does NOT make a GNews-vs-NewsAPI provider decision and does
NOT change `app.workers.news_worker`'s fetch/cadence logic -- this module
is provider-neutral (`response.source` names whichever provider actually
produced the response) and is called as an additional write alongside
the worker's existing `write_news` call, never a replacement for it.

`related_player_ids` is always `None` here -- `NewsArticle` (Phase 3C-i)
carries no player-level field at all, a real gap Volume 3 §4.4 already
names as a future addition once an adapter/model actually produces one.
`provider_article_id` is always `None` for the same reason: neither
`NewsAPINewsAdapter`'s parsing nor the `NewsArticle` model captures a
provider-native article id today.

Licensing/redistribution caution (Volume 3 §4.4, unchanged, not enforced
here): only `headline`/`summary`/`source_name` are written -- never a
full article body -- until each provider's commercial redistribution
terms are independently confirmed.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from app.adapters.models import AdapterResponse, NewsArticle


class PersistenceError(Exception):
    """Raised when a normalized response can't be written to Supabase --
    same distinction from a provider-side error as every sibling
    snapshot-persistence module's identical class."""


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def write_news_article_history(
    response: AdapterResponse[list[NewsArticle]],
    *,
    team_id: str | None = None,
) -> int:
    """Writes every `NewsArticle` in `response` as a first-sighting row,
    scoped to `team_id` if this fetch was team-scoped (matching
    `news_worker.py`'s own per-team fetch shape) -- `related_team_ids` is
    `[team_id]` when given, `None` for an unscoped fetch. Returns the
    number of rows genuinely newly inserted (an article already seen
    under the same `(provider_name, article_url)` pair contributes 0, not
    an error and not a second row)."""
    articles = response.value
    if not articles:
        return 0

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    rows = [
        {
            "provider_name": response.source,
            "provider_article_id": None,
            "article_url": article.url,
            "published_at": article.published_at.astimezone(timezone.utc).isoformat()
            if isinstance(article.published_at, datetime)
            else article.published_at,
            "headline": article.headline,
            "summary": article.summary,
            "source_name": article.source,
            "related_team_ids": [team_id] if team_id else None,
            "related_player_ids": None,
        }
        for article in articles
    ]

    async with httpx.AsyncClient(base_url=supabase_url, timeout=10.0) as client:
        insert_response = await client.post(
            "/rest/v1/news_article_history",
            params={"on_conflict": "provider_name,article_url"},
            json=rows,
            headers={**headers, "Prefer": "resolution=ignore-duplicates,return=representation"},
        )
        if insert_response.status_code not in (200, 201):
            raise PersistenceError(
                f"failed to insert news_article_history: {insert_response.status_code} {insert_response.text}"
            )
        return len(insert_response.json())
