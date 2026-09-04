"""Milestone 7.1 orchestration -- ties `app.features.market`'s existing
deterministic `LineMovementFeatures` computation to the new
`app.features.market_integrity` classification/explanatory-evidence
logic and persists qualifying (WATCH/ELEVATED/SEVERE) assessments to
`market_monitoring_events` (Volume 3 §7), this milestone's own first
real writer for that table.

**Backend only, no consumers (Milestone 7.0/7.1 scope, explicit).**
Nothing calls this module automatically -- it is not wired into the
Recommendation Worker cycle, any cron dispatch target, or any internal
HTTP endpoint. Milestone 7.0's own service-ownership decision names the
Recommendation Worker cycle as this capability's eventual home; wiring
it there, and reusing the resulting signal to withdraw/suppress a
recommendation, is explicitly Milestone 7.2's scope (Strategy Engine
Integration & SEVERE Suppression) -- not this one's. This module is
reachable today only by direct import (this milestone's own tests) and
by a future milestone's explicit wiring.

**Never persists a NORMAL or INSUFFICIENT_HISTORY assessment** -- only
a classification that actually qualifies as a detected movement (WATCH/
ELEVATED/SEVERE) is a "qualifying event" worth a `market_monitoring_
events` row; a classification that found nothing anomalous is not an
event to log. `action_taken` is always `'none'` (no Strategy Engine
consumer exists yet to act on it)."""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.features.market import compute_line_movement
from app.features.market_integrity import MarketIntegrityAssessment, assess_market_integrity, movement_windows
from app.persistence.games import get_game_for_grading
from app.persistence.market_integrity import (
    read_depth_chart_snapshots,
    read_injury_reports,
    read_news_article_history_for_teams,
    read_weather_snapshots,
    resolve_team_ids_by_name,
    write_market_monitoring_event,
)
from app.persistence.odds_snapshots import read_odds_snapshots

_QUALIFYING_CLASSIFICATIONS = ("WATCH", "ELEVATED", "SEVERE")


@dataclass
class GameMarketIntegrityResult:
    game_id: str
    status: str  # "assessed" | "game_not_found" | "no_odds_history"
    assessments: list[MarketIntegrityAssessment] = field(default_factory=list)
    written_event_ids: list[str] = field(default_factory=list)


def _event_data(assessment: MarketIntegrityAssessment) -> dict:
    classification = assessment.classification
    explanatory = assessment.explanatory
    return {
        "signal": assessment.signal,
        "classification": classification.classification,
        "threshold_version": classification.threshold_version,
        "sportsbook": classification.sportsbook,
        "market_type": classification.market_type,
        "side": classification.side,
        "magnitude": classification.magnitude,
        "magnitude_basis": classification.magnitude_basis,
        "direction": classification.direction,
        "sample_count": classification.sample_count,
        "price_movement": classification.price_movement,
        "point_movement": classification.point_movement,
        "explained": explanatory.explained if explanatory is not None else None,
        "explanatory_evidence": [
            {"category": m.category, "observed_at": m.observed_at.isoformat(), "reference": m.reference}
            for m in (explanatory.matches if explanatory is not None else ())
        ],
    }


async def assess_game_market_integrity(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> GameMarketIntegrityResult:
    """Assesses every `(sportsbook, market_type, side)` line-movement
    group for `game_id` and persists a `market_monitoring_events` row
    for each qualifying (WATCH/ELEVATED/SEVERE) result. Never raises for
    a missing game or a game with no odds history -- both are legitimate,
    named outcomes (`game_not_found`/`no_odds_history`), not errors."""
    game = await get_game_for_grading(client, headers, game_id=game_id)
    if game is None:
        return GameMarketIntegrityResult(game_id=game_id, status="game_not_found")

    snapshots = await read_odds_snapshots(client, headers, game_id=game_id)
    if not snapshots:
        return GameMarketIntegrityResult(game_id=game_id, status="no_odds_history")

    features = compute_line_movement(snapshots)
    windows = movement_windows(snapshots)

    injury_reports = await read_injury_reports(client, headers, game_id=game_id)
    weather_snapshots = await read_weather_snapshots(client, headers, game_id=game_id)
    team_ids_by_name = await resolve_team_ids_by_name(client, headers, team_names=[game["home_team"], game["away_team"]])
    team_ids = list(team_ids_by_name.values())
    depth_chart_snapshots = await read_depth_chart_snapshots(client, headers, team_ids=team_ids)
    news_articles = await read_news_article_history_for_teams(client, headers, team_ids=team_ids)

    assessments: list[MarketIntegrityAssessment] = []
    written_event_ids: list[str] = []
    for feature in features:
        window = windows.get((feature.sportsbook, feature.market_type))
        assessment = assess_market_integrity(
            feature,
            window=window,
            injury_reports=injury_reports,
            weather_snapshots=weather_snapshots,
            depth_chart_snapshots=depth_chart_snapshots,
            news_articles=news_articles,
        )
        assessments.append(assessment)
        if assessment.classification.classification in _QUALIFYING_CLASSIFICATIONS:
            event_id = await write_market_monitoring_event(
                client, headers, game_id=game_id, event_type="line_movement", event_data=_event_data(assessment)
            )
            written_event_ids.append(event_id)

    return GameMarketIntegrityResult(game_id=game_id, status="assessed", assessments=assessments, written_event_ids=written_event_ids)
