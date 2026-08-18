"""News Worker orchestration (Phase 3E-7).

**Provider decision status -- BLOCKER, not silently resolved.** Volume 2
§8 names NewsAPI as default vendor and GNews as fallback, but Mac
explicitly held back any primary/fallback comparison on 2026-08-11 and
never revisited it (`PROGRESS.md`). No GNews code exists anywhere in this
repository. This worker is built provider-neutrally against the existing
`NewsAdapter`/`NewsArticle` interface (exactly like every other worker is
built against its category's abstract adapter, never a concrete vendor
type) -- `NewsAPINewsAdapter` is wired in below only because it is the
only adapter that currently exists, not because the vendor question is
settled. Swapping it for a future `GNewsNewsAdapter` requires zero change
here, by the same adapter-pattern guarantee every other category relies
on.

**Persistence -- Option A, Mac's approved smallest additive move
(2026-08-18).** No new table. `daily_game_intelligence.news` (Volume 3
§4.1) remains the only place News lives -- see
`app.persistence.daily_game_intelligence`'s module docstring for the full
reasoning, and `write_news` there for the actual write path this worker
calls. Option B (an append-only `news_snapshots`/`news_reports` table) was
presented and explicitly deferred, not silently ruled out: nothing in
Phase 3's acceptance criteria requires News history, and a
team-keyed-not-game-keyed snapshot shape would be a genuine schema
departure from Odds/Injuries/Weather's game-keyed convention, inheriting
the same vendor-ToS/commercial-storage-terms question the original
Milestone F deferral was about. Remains available future work, gated on
the same provider decision above.

**Cadence -- CONFIRMED FROM VOLUME 2 §8: "Every 15 minutes." No ramp
tiers** (`_POLL_INTERVAL_SECONDS = 900`, matching
`app.adapters.cache.CATEGORY_TTL_SECONDS["news"]` exactly, verified before
reuse -- same discipline as `weather_worker.py`).

**A deliberate DEPARTURE from Weather's stop-at-kickoff convention, not a
missed reuse.** Weather/Odds/Player Props all stop polling a specific game
at its own kickoff, because pregame conditions/markets are structurally
meaningless once the game starts. News about a team has no equivalent
boundary -- a team's news relevance doesn't end at its own kickoff
(injury updates, postgame reactions, next-week previews are all still
"news about that team"), and `classify_window`'s `Window.STOPPED`
therefore has no correct answer to give here. This worker never imports
`app.workers.windows` at all. The only DERIVED scoping boundary reused
from existing convention is the 7-day candidate window itself (the same
`_CANDIDATE_WINDOW_DAYS` every other specialized worker independently
adopted) -- a team naturally stops being polled once none of its games
remain inside that rolling window, which is a sufcient, already-established
boundary without needing a second, game-specific stop condition layered on
top.

**Polling unit is a team, not a game -- the entity `last_polled_at` tracks.**
Every other per-entity worker tracks its own natural fetch granularity
(Weather/Odds/Player Props: per game, since their provider calls are
per-game; Injury: a single worker-level timestamp, since SportsDataIO's
Injuries endpoint is one bulk call). `NewsAdapter.fetch_news(team=...)` is
team-scoped, so this worker's natural unit -- and its cache key, and its
`last_polled_at` key -- is a resolved internal `teams.id`, not a game.

**Identity -- resolved by the worker itself, never guessed from provider
data.** `games.home_team`/`.away_team` hold SportsDataIO abbreviations
(games are only ever created by Master Refresh from a SportsDataIO
Schedule fetch). This worker resolves each distinct abbreviation to a
`teams.id` via `app.persistence.team_identity.resolve_team_ids`
(`provider_name="sportsdataio"`, now 32/32-confirmed per Volume 3 v4.8 --
see `docs/blueprint/volume-3-database-architecture.md`), then to the
canonical `teams.name` via the new `app.persistence.teams.list_teams_by_id`
-- `NewsAdapter.fetch_news`'s `team` parameter takes a human-readable name
("Kansas City Chiefs"), not an abbreviation or an internal id. An
abbreviation with no `team_provider_ids` mapping is `teams_unresolved`,
never guessed or fuzzy-matched, and simply excluded from that cycle's
fetch -- see `_should_poll`/`run_news_worker` below.

Because this worker only ever calls `fetch_news(team=<resolved canonical
name>)` -- never the bare, unscoped `fetch_news(team=None)` "NFL" query
NewsAPI also supports -- it never produces or has to handle a truly
league-wide/unassigned article at all. That query shape is deliberately
never used: an unscoped query's results have no trustworthy team
relationship (see `NewsArticle.related_teams`, which is `[]` for an
unscoped call), and forcing those into any specific game's `news` field
would be exactly the fuzzy/guessed relevance the Blueprint prohibits.
True league-wide news (a rules change, a national broadcast note) is
therefore out of scope for this worker's game-keyed persistence target --
a real model/table-shape mismatch, flagged here rather than papered over,
and unaffected by which provider eventually wins the vendor decision.

**Defensive identity validation on the response side, not just the
request side.** Every article `fetch_news(team=name)` returns is checked
that `name` is actually present in that article's own `related_teams`
before being attributed to that team -- `NewsAPINewsAdapter` already
guarantees this (it sets `related_teams=[team]` unconditionally), but this
worker does not trust that guarantee blindly, since a future/different
`NewsAdapter` implementation is not obligated to preserve it. An article
failing this check is dropped and counted under `articles_dropped_unresolved`,
never force-attached.

**Player-level news -- not supported by the model, not fabricated.**
`NewsArticle` has no player field at all (only `related_teams: list[str]`)
-- there is no player-level relevance to compute here, by the existing
model's own shape, not a gap this worker tries to paper over.

**One game, two teams, one `news` column.** A game's `home_team`/
`away_team` are usually two different teams; `write_news` writes one
combined, de-duplicated (by `url`) article list per game, drawn from
whichever of that game's two teams were successfully fetched this cycle.
If only one side was due/resolved/successful this cycle, that side's
articles alone are written (never blocked waiting on the other side); if
neither side produced a result this cycle, the game is skipped entirely
this cycle -- see failure/stale-data handling below.

**Failure/stale-data handling -- never erase previously-usable news.** A
team whose fetch fails this cycle (`ProviderError`) is left out of that
cycle's results entirely; any game depending only on that team's news for
this cycle is skipped -- `write_news` is simply not called for it, so
whatever `daily_game_intelligence.news` already held (from a prior
successful cycle) is left completely untouched, never overwritten with an
empty/neutral value. A team whose fetch *succeeds* with zero articles
(NewsAPI's own `articles_empty.json` fixture scenario) is a real,
positive result -- "provider checked, there truly is no relevant news
right now" -- and **is** written, as an empty `value: []` with fresh
`last_updated`/`status`, which is exactly what distinguishes it from the
failure case above at read time: a stale/absent write means "not
re-checked," a fresh empty write means "checked, genuinely nothing."

**Malformed-article-response isolation -- a known asymmetry with Injury
Worker's Decision 3, not silently matched.** `NewsAPINewsAdapter.
fetch_news` (built 3C-i, unchanged here) wraps its whole article-parsing
loop in one try/except -- a single malformed article invalidates that
entire team's fetch for the cycle, unlike Injury Worker's per-row
isolation (3E-5, Mac's explicit Decision 3 for that worker specifically).
This worker does not change that adapter behavior -- doing so would be a
real design decision affecting already-shipped 3C-i code, not something
3E-7's scope authorizes unilaterally. A malformed response for one team is
therefore treated exactly like any other `ProviderError`: that team's
cycle is skipped, `write_news` isn't called for games depending only on
it, nothing existing is erased. Flagged here as available future work,
not done.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.cache import CacheBackend, CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, NewsArticle
from app.adapters.providers.newsapi import NewsAPINewsAdapter
from app.persistence.daily_game_intelligence import DailyGameIntelligenceError, write_news
from app.persistence.games import GamesQueryError, list_games_in_window
from app.persistence.team_identity import TeamIdentityError, resolve_team_ids
from app.persistence.teams import TeamsQueryError, list_teams_by_id

#: Same candidate-window convention as every other specialized worker --
#: the only boundary reused from existing convention (see module
#: docstring's "deliberate DEPARTURE" section for why stop-at-kickoff is
#: NOT also reused).
_CANDIDATE_WINDOW_DAYS = 7

#: CONFIRMED FROM VOLUME 2 §8 -- flat 15-minute cadence. Matches
#: CATEGORY_TTL_SECONDS["news"] exactly (verified, not assumed).
_POLL_INTERVAL_SECONDS = 900

_PROVIDER_NAME = "sportsdataio"  # games.home_team/.away_team's own namespace


@dataclass
class NewsWorkerResult:
    status: str  # "success" | "partial" | "failed"
    games_considered: int = 0
    teams_considered: int = 0
    teams_due: int = 0
    teams_skipped_not_due: int = 0
    teams_unresolved: list[str] = field(default_factory=list)  # abbreviations, no team_provider_ids mapping
    teams_fetched: int = 0
    articles_dropped_unresolved: int = 0
    games_updated: int = 0
    games_skipped_no_data: int = 0
    failures: list[str] = field(default_factory=list)
    error: str | None = None


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


def _should_poll(*, now: datetime, last_polled_at: datetime | None) -> bool:
    """Flat 15-minute interval, no kickoff/window dependency at all -- see
    module docstring's "deliberate DEPARTURE" section."""
    if last_polled_at is None:
        return True
    elapsed = now.astimezone(timezone.utc) - last_polled_at.astimezone(timezone.utc)
    return elapsed >= timedelta(seconds=_POLL_INTERVAL_SECONDS)


def _validate_articles(team_name: str, articles: list[NewsArticle]) -> tuple[list[NewsArticle], int]:
    """Defensive check, not a blind trust of the adapter: only articles
    whose own `related_teams` actually contains `team_name` are attributed
    to it. `NewsAPINewsAdapter` already guarantees this (it always sets
    `related_teams=[team]` for a team-scoped call), but a future/different
    `NewsAdapter` implementation is not obligated to preserve that -- see
    module docstring's "Defensive identity validation" section. Returns
    (validated articles, count dropped)."""
    validated = [article for article in articles if team_name in article.related_teams]
    dropped = len(articles) - len(validated)
    return validated, dropped


def _dedupe_by_url(articles: list[NewsArticle]) -> list[NewsArticle]:
    seen: set[str] = set()
    result: list[NewsArticle] = []
    for article in articles:
        if article.url in seen:
            continue
        seen.add(article.url)
        result.append(article)
    return result


async def run_news_worker(
    *,
    supabase_client: httpx.AsyncClient,
    newsapi_client: httpx.AsyncClient,
    newsapi_key: str,
    cache_backend: CacheBackend | None = None,
    now: datetime | None = None,
    last_polled_at: dict[str, datetime] | None = None,
) -> NewsWorkerResult:
    """Runs one News Worker cycle. Always returns a `NewsWorkerResult`,
    never raises -- same finite-job shape as every other specialized
    worker. `last_polled_at` is keyed by resolved `teams.id` (the entity
    this worker actually polls -- see module docstring)."""
    headers = _auth_headers()
    cache_backend = cache_backend or InMemoryCacheBackend()
    now = now or datetime.now(timezone.utc)
    last_polled_at = last_polled_at or {}

    today: date = now.date()
    try:
        games = await list_games_in_window(
            supabase_client, headers, start=today, end=today + timedelta(days=_CANDIDATE_WINDOW_DAYS)
        )
    except GamesQueryError as exc:
        return NewsWorkerResult(status="failed", error=f"failed to list candidate games: {exc}")

    if not games:
        return NewsWorkerResult(status="success", games_considered=0)

    abbrevs = sorted({game["home_team"] for game in games} | {game["away_team"] for game in games})

    try:
        abbrev_to_team_id = await resolve_team_ids(
            supabase_client, headers, provider_name=_PROVIDER_NAME, provider_team_ids=abbrevs
        )
    except TeamIdentityError as exc:
        return NewsWorkerResult(status="failed", games_considered=len(games), error=f"failed to resolve team ids: {exc}")

    teams_unresolved = [abbrev for abbrev in abbrevs if abbrev not in abbrev_to_team_id]

    try:
        team_id_to_name = await list_teams_by_id(
            supabase_client, headers, team_ids=list(set(abbrev_to_team_id.values()))
        )
    except TeamsQueryError as exc:
        return NewsWorkerResult(status="failed", games_considered=len(games), error=f"failed to list team names: {exc}")

    # Resolved abbreviation but no name row (should not happen given
    # referential integrity, but never assumed) -- also unresolved.
    resolvable_team_ids = {
        team_id for team_id in abbrev_to_team_id.values() if team_id in team_id_to_name
    }

    due_team_ids: list[str] = []
    skipped_not_due = 0
    for team_id in sorted(resolvable_team_ids):
        if _should_poll(now=now, last_polled_at=last_polled_at.get(team_id)):
            due_team_ids.append(team_id)
        else:
            skipped_not_due += 1

    news_adapter = NewsAPINewsAdapter(client=newsapi_client, api_key=newsapi_key)
    caching = CachingAdapter(news_adapter, cache_backend, ttl_seconds=_POLL_INTERVAL_SECONDS)

    team_articles: dict[str, list[NewsArticle]] = {}
    provider_source = "newsapi"
    failures: list[str] = []
    articles_dropped_unresolved = 0

    for team_id in due_team_ids:
        team_name = team_id_to_name[team_id]
        try:
            response: AdapterResponse[list[NewsArticle]] = await caching.call(
                "fetch_news", team_name, response_model=AdapterResponse[list[NewsArticle]]
            )
        except ProviderError as exc:
            failures.append(f"{team_name}: news fetch failed: {exc}")
            continue
        provider_source = response.source
        validated, dropped = _validate_articles(team_name, response.value)
        articles_dropped_unresolved += dropped
        team_articles[team_id] = validated

    games_updated = 0
    games_skipped_no_data = 0
    for game in games:
        home_team_id = abbrev_to_team_id.get(game["home_team"])
        away_team_id = abbrev_to_team_id.get(game["away_team"])
        contributions: list[NewsArticle] = []
        for team_id in (home_team_id, away_team_id):
            if team_id is not None and team_id in team_articles:
                contributions.extend(team_articles[team_id])

        relevant_team_ids = {tid for tid in (home_team_id, away_team_id) if tid is not None}
        if not relevant_team_ids & team_articles.keys():
            games_skipped_no_data += 1
            continue

        combined = _dedupe_by_url(contributions)
        try:
            await write_news(
                supabase_client,
                headers,
                game_id=game["id"],
                articles=[article.model_dump(mode="json") for article in combined],
                source=provider_source,
                now=now,
            )
            games_updated += 1
        except DailyGameIntelligenceError as exc:
            failures.append(f"{game['id']}: failed to write news: {exc}")

    status = "partial" if failures else "success"
    return NewsWorkerResult(
        status=status,
        games_considered=len(games),
        teams_considered=len(resolvable_team_ids),
        teams_due=len(due_team_ids),
        teams_skipped_not_due=skipped_not_due,
        teams_unresolved=teams_unresolved,
        teams_fetched=len(team_articles),
        articles_dropped_unresolved=articles_dropped_unresolved,
        games_updated=games_updated,
        games_skipped_no_data=games_skipped_no_data,
        failures=failures,
    )
