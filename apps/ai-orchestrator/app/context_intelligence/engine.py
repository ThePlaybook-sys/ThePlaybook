"""The single public entry point for the Phase 8.1 Contextual
Intelligence Foundation Pass (2026-09-08): `build_contextual_intelligence`.

Composes real, already-fetched data ONCE (mirroring `app.agents.context.
build_agent_context`'s own "download once, reuse everywhere" convention)
and calls each dimension's pure compute function -- four real
(weather/market/news/venue) plus six fixed insufficient-evidence stubs
(player_performance/injuries/roster_role/team_performance/depth_lineup/
game_state_pbp) -- assembling one `ContextualIntelligenceResult` covering
all ten dimensions every time. No writes anywhere in this module: fully
stateless, re-derived from real history on every call, per HQ's explicit
"do NOT create one persisted model row per player" instruction.

**Future integration point into Probability Modeling (NOT wired in this
pass):** `app.agents.probability_modeling.ProbabilityModelingAgent.
build_evidence` currently returns `{"candidate": ..., "upstream_findings":
..., "participation": ...}` (`app/agents/probability_modeling.py`, Milestone
4.6). A later, separately-authorized pass would add one line there:

    "contextual_performance": contextual_intelligence.to_json(),

where `contextual_intelligence` is this module's own
`ContextualIntelligenceResult`, built once per `SequentialDecisionContext.
game_id` before the sequential chain runs (the same point
`AgentContext`/`odds_history`/`line_movement` are already built, per
`app.agents.context.build_agent_context`). Nothing in `probability_modeling.py`,
`sequential_base.py`, or the fan-out committee's agent count/routing/
consensus logic is touched by this pass -- that wiring is explicitly
deferred, per HQ's "Do NOT reopen Phase 4" instruction."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.context_intelligence.market import compute_market_context
from app.context_intelligence.models import ContextualIntelligenceResult
from app.context_intelligence.news import compute_news_context
from app.context_intelligence.unsupported import UNSUPPORTED_DIMENSIONS, insufficient_evidence_result
from app.context_intelligence.venue import compute_venue_context
from app.context_intelligence.weather import compute_weather_context
from app.persistence.context_intelligence_reads import (
    read_all_odds_snapshots,
    read_all_weather_snapshots,
    read_game_venue_context,
    read_games_sharing_venue,
    read_venue,
)
from app.persistence.market_integrity import read_news_article_history_for_teams, resolve_team_ids_by_name
from app.persistence.odds_snapshots import read_odds_snapshots

#: The four dimensions this pass builds real contextual intelligence
#: for -- Phase 8.0.5's own closeout audit's REAL + ACTIVE list, exactly.
SUPPORTED_DIMENSIONS = ("weather", "market", "news", "venue")


async def build_contextual_intelligence(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, now: datetime | None = None
) -> ContextualIntelligenceResult:
    """Builds the complete, all-ten-dimension contextual intelligence
    result for `game_id`. Never raises for missing data anywhere -- a
    game with no real odds/weather/news history yet, or with no
    resolvable team/venue identity, produces honest
    `insufficient_evidence=True` results for those dimensions, never an
    exception. Real read failures (a non-200 Supabase response) still
    raise, matching every persistence module in this package."""
    now = now or datetime.now(timezone.utc)

    game = await read_game_venue_context(client, headers, game_id=game_id)

    target_odds = await read_odds_snapshots(client, headers, game_id=game_id)
    all_odds = await read_all_odds_snapshots(client, headers)
    all_weather = await read_all_weather_snapshots(client, headers)

    team_names = [name for name in ((game or {}).get("home_team"), (game or {}).get("away_team")) if name]
    team_ids_by_name = await resolve_team_ids_by_name(client, headers, team_names=team_names)
    team_ids = list(team_ids_by_name.values())
    news_articles = await read_news_article_history_for_teams(client, headers, team_ids=team_ids)

    weather_for_this_game = [row for row in all_weather if row.get("game_id") == game_id]

    venue_id = (game or {}).get("venue_id")
    venue = await read_venue(client, headers, venue_id=venue_id) if venue_id else None
    other_games_sharing_venue = (
        await read_games_sharing_venue(client, headers, venue_id=venue_id, exclude_game_id=game_id)
        if venue_id
        else []
    )

    dimensions = {
        "weather": compute_weather_context(all_weather, game_id=game_id, now=now),
        "market": compute_market_context(
            game_id=game_id,
            target_snapshots=target_odds,
            all_odds_rows=all_odds,
            weather_snapshots_for_game=weather_for_this_game,
            news_articles_for_teams=news_articles,
            now=now,
        ),
        "news": compute_news_context(
            game_id=game_id,
            news_articles_for_teams=news_articles,
            target_odds_snapshots=target_odds,
            now=now,
        ),
        "venue": compute_venue_context(
            game=game,
            venue=venue,
            other_games_sharing_venue=other_games_sharing_venue,
            now=now,
        ),
    }
    for name in UNSUPPORTED_DIMENSIONS:
        dimensions[name] = insufficient_evidence_result(name)

    return ContextualIntelligenceResult(game_id=game_id, generated_at=now.isoformat(), dimensions=dimensions)


__all__ = ["build_contextual_intelligence", "SUPPORTED_DIMENSIONS"]
