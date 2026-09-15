"""The single public entry point for Contextual Intelligence
(`build_contextual_intelligence`), originally the Phase 8.1 Foundation
Pass (2026-09-08), extended by the Player Performance Engine Integration
pass (2026-09-15, HQ-authorized "MANSA -- PHASE 8 PLAYER PERFORMANCE
ENGINE INTEGRATION").

Composes real, already-fetched data ONCE (mirroring `app.agents.context.
build_agent_context`'s own "download once, reuse everywhere" convention)
and calls each dimension's pure compute function -- five real
(weather/market/news/venue/player_performance) plus five fixed
insufficient-evidence stubs (injuries/roster_role/team_performance/
depth_lineup/game_state_pbp) -- assembling one `ContextualIntelligenceResult`
covering all ten dimensions every time. No writes anywhere in this
module: fully stateless, re-derived from real history on every call, per
HQ's explicit "do NOT create one persisted model row per player"
instruction.

**`player_performance` (new, 2026-09-15)** is the first dimension in this
module scoped to something other than `game_id` alone -- it answers "what
do we know about `player_id`'s own real historical performance," which
requires an explicit `player_id` this function did not previously accept.
`player_id` is optional (`None` by default, matching every existing
caller's own call shape unchanged): when omitted, `player_performance`
resolves to `player_performance.no_player_requested_result()` (a real,
honest `insufficient_evidence=True`/`data_completeness="unavailable"`
result, never an exception, never a guess) and **none of the new reads
below fire at all** -- a caller that never asks about a player pays zero
extra cost. When provided, this module fetches that player's own real
`player_stats` rows, the real `games` rows they reference, that player's
own real identity (`players.name`/`position`/`team_id`), and real
opponent-identity data (`resolve_team_identity_for_games` -- see that
function's own docstring for the full real, provider-identity-based
resolution chain, replacing the prior pass's `games.home_team`/`away_team`
text-matching, which the JSN proof showed fails on real rows).
`player_performance`'s own `target_event_timestamp` is this function's
`now` (not `game_id`'s own kickoff) -- the natural "what do we currently,
actually know about this player" framing; for a genuinely upcoming
`game_id` this makes no practical difference (no `player_stats` row can
exist yet for an unplayed game either way), and for a `game_id` that has
already happened (as in the JSN/SEA@NE proof) it correctly includes that
real, already-completed game as valid historical evidence.

**Future integration point into Probability Modeling (still NOT wired in
this pass):** `app.agents.probability_modeling.ProbabilityModelingAgent.
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
deferred, per HQ's "Do NOT reopen Phase 4" instruction, reconfirmed by
this pass's own explicit boundary."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.context_intelligence.market import compute_market_context
from app.context_intelligence.models import ContextualIntelligenceResult
from app.context_intelligence.news import compute_news_context
from app.context_intelligence.player_performance import compute_player_performance_context, no_player_requested_result
from app.context_intelligence.unsupported import UNSUPPORTED_DIMENSIONS, insufficient_evidence_result
from app.context_intelligence.venue import compute_venue_context
from app.context_intelligence.weather import compute_weather_context
from app.persistence.context_intelligence_reads import (
    read_all_odds_snapshots,
    read_all_weather_snapshots,
    read_game_venue_context,
    read_games_by_ids,
    read_games_sharing_venue,
    read_player_identity,
    read_player_stats_for_player,
    read_venue,
    resolve_team_identity_for_games,
)
from app.persistence.market_integrity import read_news_article_history_for_teams, resolve_team_ids_by_name
from app.persistence.odds_snapshots import read_odds_snapshots

#: The real dimensions this module builds real contextual intelligence
#: for. `player_performance` added 2026-09-15 (Player Performance Engine
#: Integration pass) -- see module docstring for its distinct, player_id-
#: scoped calling contract.
SUPPORTED_DIMENSIONS = ("weather", "market", "news", "venue", "player_performance")


async def build_contextual_intelligence(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    player_id: str | None = None,
    now: datetime | None = None,
) -> ContextualIntelligenceResult:
    """Builds the complete, all-ten-dimension contextual intelligence
    result for `game_id` (and, when `player_id` is given, that player's
    own real historical performance -- see module docstring). Never
    raises for missing data anywhere -- a game with no real odds/weather/
    news history yet, no resolvable team/venue identity, or no player_id
    given at all, produces honest `insufficient_evidence=True` results
    for those dimensions, never an exception. Real read failures (a
    non-200 Supabase response) still raise, matching every persistence
    module in this package."""
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

    if player_id is None:
        dimensions["player_performance"] = no_player_requested_result()
    else:
        player_row = await read_player_identity(client, headers, player_id=player_id)
        player_stats_rows = await read_player_stats_for_player(client, headers, player_id=player_id)
        referenced_game_ids = sorted({row["game_id"] for row in player_stats_rows})
        player_games_by_id = await read_games_by_ids(client, headers, game_ids=referenced_game_ids)
        team_identity_by_game = await resolve_team_identity_for_games(client, headers, game_ids=referenced_game_ids)
        dimensions["player_performance"] = compute_player_performance_context(
            player_stats_rows,
            player_games_by_id,
            player_id=player_id,
            target_event_timestamp=now,
            player_name=(player_row or {}).get("name"),
            position=(player_row or {}).get("position"),
            player_team_id=(player_row or {}).get("team_id"),
            team_identity_by_game=team_identity_by_game,
            now=now,
        )

    return ContextualIntelligenceResult(game_id=game_id, generated_at=now.isoformat(), dimensions=dimensions)


__all__ = ["build_contextual_intelligence", "SUPPORTED_DIMENSIONS"]
