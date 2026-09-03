"""MANSA News Provider Validation -- GNews Essential (2026-09-03).

TEMPORARY, DIAGNOSTIC-ONLY module, same shape and same "temporary probe,
then revert" discipline as `app.diagnostics.nfl_bakeoff`/`msf_bakeoff`
(the two prior NFL data-provider bake-offs) -- not a `ProviderAdapter`,
never wired into any permanent route, never imported by
`app.workers.news_worker` or `app.adapters.providers.newsapi`. Invoked
once, at process startup, from a dev-only, flag-gated hook (see
`app.main`), because this workspace's own egress policy blocks direct
HTTPS to `gnews.io`/`docs.gnews.io` (confirmed the same way as every
other vendor domain in the prior bake-offs) and to this service's own
public Railway domain -- so results are retrieved via `logger.warning`
lines in Railway's deploy logs, never an HTTP response.

Endpoint shape, params, and response schema below are CONFIRMED FROM
PUBLIC SOURCES (direct docs.gnews.io/gnews.io fetches are blocked, same
constraint as every prior bake-off): the official `gnews-io/gnews-io-js`
TypeScript client's README (base URL, `q`/`lang`/`country`/`max`/`from`/
`to` params, the `articles: [{id, title, description, content, url,
image, publishedAt, lang, source: {id, name, url, country}}]` response
shape) and multiple independent WebSearch-indexed sources for the
`apikey` query-param name, the Essential plan's real limits (1,000
req/day, 10 req/sec, 25 articles/request max), and the `expand=content`
paid-only full-content parameter. NOT copied from the unrelated
`gnews` PyPI package (a Google-News RSS scraper by a different author,
unaffiliated with gnews.io) -- that package was found during research
and deliberately NOT used as a schema source, since it is a different
product with a similarly-named but unrelated API.

Base URL: https://gnews.io/api/v4
Auth: `apikey` query parameter (never a header, never logged by name
here -- `GNEWS_API_KEY` is read exactly once, by
`build_gnews_validation_client()` in
`app.master_refresh.production_clients`, matching the isolation
convention every other provider credential in this project follows).

Call budget: 9 calls total, directly targeting HQ's 11 named evaluation
criteria plus the two comparison questions (query precision, structured
metadata, URL/source stability, full-content value, likely volume under
MANSA's shared/cached architecture). Paced 1.5s apart -- comfortably
inside the Essential plan's confirmed 10 req/sec limit, and the whole
run is a small fraction of its 1,000 req/day budget.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx

_BASE_PATH = "/api/v4/search"


def _cap_list_fields(body: Any, *, max_items: int = 6) -> Any:
    """Same safety net as every prior bake-off's own `_cap_list_fields` --
    caps top-level lists so one oversized response can't blow past a
    single Railway log line's practical size limit. Applied only to the
    LOGGED copy, never to the body the analysis pass below uses."""
    if isinstance(body, list):
        if len(body) > max_items:
            return {"_capped_list": body[:max_items], "_total_count": len(body), "_truncated_for_log": True}
        return body
    if not isinstance(body, dict):
        return body
    capped = dict(body)
    for key, value in body.items():
        if isinstance(value, list) and len(value) > max_items:
            capped[key] = value[:max_items]
            capped[f"_{key}_total_count"] = len(value)
            capped[f"_{key}_truncated_for_log"] = True
    return capped


def _analyze(body: Any, *, now: datetime) -> dict[str, Any]:
    """Precomputed signals answering HQ's cross-cutting evaluation
    questions directly, so the report doesn't have to re-derive them from
    raw log dumps by hand: duplicate URLs, source diversity, freshness
    relative to wall-clock time, and structured-metadata completeness."""
    if not isinstance(body, dict) or not isinstance(body.get("articles"), list):
        return {"analyzable": False}
    articles = body["articles"]
    urls = [a.get("url") for a in articles if isinstance(a, dict)]
    sources = [
        (a.get("source") or {}).get("name") for a in articles if isinstance(a, dict)
    ]
    has_image = sum(1 for a in articles if isinstance(a, dict) and a.get("image"))
    has_content = sum(1 for a in articles if isinstance(a, dict) and a.get("content"))
    content_lengths = [
        len(a["content"]) for a in articles if isinstance(a, dict) and isinstance(a.get("content"), str)
    ]
    published_ats: list[datetime] = []
    for a in articles:
        if not isinstance(a, dict):
            continue
        raw = a.get("publishedAt")
        if not isinstance(raw, str):
            continue
        try:
            published_ats.append(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError:
            continue
    most_recent = max(published_ats) if published_ats else None
    return {
        "analyzable": True,
        "total_articles_reported": body.get("totalArticles"),
        "articles_returned": len(articles),
        "unique_urls": len(set(u for u in urls if u)),
        "duplicate_url_count": len(urls) - len(set(u for u in urls if u)),
        "unique_sources": len(set(s for s in sources if s)),
        "articles_with_image": has_image,
        "articles_with_content_field": has_content,
        "content_field_lengths": content_lengths,
        "most_recent_published_at": most_recent.isoformat() if most_recent else None,
        "most_recent_age_minutes": (
            round((now - most_recent).total_seconds() / 60, 1) if most_recent else None
        ),
        "has_source_id": any(
            isinstance(a, dict) and isinstance(a.get("source"), dict) and a["source"].get("id")
            for a in articles
        ),
    }


async def _call(
    client: httpx.AsyncClient, *, api_key: str, params: dict[str, Any]
) -> dict[str, Any]:
    started = time.monotonic()
    request_params = dict(params)
    request_params["apikey"] = api_key
    try:
        response = await client.get(_BASE_PATH, params=request_params)
    except httpx.HTTPError as exc:
        return {
            "params": {k: v for k, v in params.items()},
            "http_status": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}",
            "response_headers": {},
            "raw_body": None,
        }
    latency_ms = round((time.monotonic() - started) * 1000, 1)
    interesting_headers = {
        k: v
        for k, v in response.headers.items()
        if any(term in k.lower() for term in ("ratelimit", "retry-after", "cache", "quota"))
    }
    try:
        body = response.json() if response.content else None
    except ValueError:
        body = {"_non_json_body_preview": response.text[:300]}
    return {
        # `apikey` never included -- params here are always the caller-supplied
        # query terms, never the auth credential.
        "params": {k: v for k, v in params.items()},
        "http_status": response.status_code,
        "latency_ms": latency_ms,
        "error": None,
        "response_headers": interesting_headers,
        "raw_body": body,
    }


async def run_gnews_validation(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    """Runs the 9-call GNews Essential validation sample. Returns a dict
    with `calls` (one entry per call, `raw_body` capped for logging) and
    `note` (a short closing summary). Never raises -- diagnostic-only,
    same finite-job shape as every other bake-off runner."""
    now = datetime.now(timezone.utc)
    calls: list[dict[str, Any]] = []

    async def step(category: str, params: dict[str, Any]) -> dict[str, Any]:
        result = await _call(client, api_key=api_key, params=params)
        result["category"] = category
        result["analysis"] = _analyze(result["raw_body"], now=now)
        logged = dict(result)
        logged["raw_body"] = _cap_list_fields(result["raw_body"])
        calls.append(logged)
        await asyncio.sleep(1.5)
        return result

    # 1-2: team-scoped queries, mirroring NewsAPINewsAdapter.fetch_news's
    # exact query construction (f"{team} NFL") for direct comparability --
    # two different teams to cross-check source diversity/duplication.
    await step("team_query_chiefs", {"q": "Kansas City Chiefs NFL", "lang": "en", "max": 10, "sortby": "publishedAt"})
    await step("team_query_eagles", {"q": "Philadelphia Eagles NFL", "lang": "en", "max": 10, "sortby": "publishedAt"})

    # 3-7: the six named evaluation categories HQ asked for, each as its
    # own NFL-qualified query (never a bare unscoped term).
    await step("injury_news", {"q": "NFL injury report", "lang": "en", "max": 10, "sortby": "publishedAt"})
    await step("trade_news", {"q": "NFL trade", "lang": "en", "max": 10, "sortby": "publishedAt"})
    await step("suspension_news", {"q": "NFL suspension", "lang": "en", "max": 10, "sortby": "publishedAt"})
    await step("roster_lineup_news", {"q": "NFL depth chart", "lang": "en", "max": 10, "sortby": "publishedAt"})
    await step("coaching_news", {"q": "NFL head coach", "lang": "en", "max": 10, "sortby": "publishedAt"})

    # 8: full-content test -- `expand=content` is documented (via public
    # sources, docs.gnews.io itself unreachable) as a paid-only param that
    # returns un-truncated article bodies. Small `max` since this is a
    # feature-presence check, not another coverage sample.
    await step(
        "full_content_expand_test",
        {"q": "Kansas City Chiefs NFL", "lang": "en", "max": 3, "sortby": "publishedAt", "expand": "content"},
    )

    # 9: pagination behavior on the Essential tier -- observed status/
    # behavior is itself the finding, whether or not `page` is honored.
    await step("pagination_test", {"q": "NFL", "lang": "en", "max": 10, "page": 2})

    return {"calls": calls, "note": "9-call GNews Essential validation sample, 2026-09-03"}
