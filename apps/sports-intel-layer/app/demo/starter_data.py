"""DEMO-2 deterministic starter dataset (docs/blueprint/demo-simulation-environment.md
Section 8: "a fixed, clearly-fake roster... equally-fake but presentable names").

Small on purpose -- two synthetic games, four synthetic teams, a handful of
synthetic players. This exists only to prove every `Demo*Adapter` returns
the real normalized models Phase 3 already supports; it is not a scenario,
a storyline, or a simulated NFL week (that belongs to DEMO-3/DEMO-4). Every
identifier is deliberately non-NFL-shaped ("Demo Hawks", not a real team
name) so nothing here could be mistaken for real sports data even before
the Operator Dashboard's own visual labeling exists.

Each `default_*` function returns a fresh copy of its data so tests (and,
later, a scenario runner) can freely mutate what they get back without one
caller's changes leaking into another's.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.adapters.models import (
    InjuryReport,
    NewsArticle,
    OddsLine,
    PlayerProp,
    PlayerStatLine,
    RosterEntry,
    ScheduleEntry,
    TeamStatLine,
    WeatherConditions,
)

GAME_1 = "demo-game-1"
GAME_2 = "demo-game-2"

KICKOFF_1 = datetime(2026, 9, 6, 17, 0, tzinfo=timezone.utc)
KICKOFF_2 = datetime(2026, 9, 6, 20, 25, tzinfo=timezone.utc)

HAWKS = "Demo Hawks"
WOLVES = "Demo Wolves"
COMETS = "Demo Comets"
SHARKS = "Demo Sharks"


def default_odds_by_game() -> dict[str, list[OddsLine]]:
    return {
        GAME_1: [
            OddsLine(
                game_external_id=GAME_1, home_team=HAWKS, away_team=WOLVES,
                commence_time=KICKOFF_1, sportsbook="DemoBook", market_type="moneyline",
                line_data={"home": -120, "away": 100},
            ),
            OddsLine(
                game_external_id=GAME_1, home_team=HAWKS, away_team=WOLVES,
                commence_time=KICKOFF_1, sportsbook="DemoBook", market_type="spread",
                line_data={"home": -2.5, "away": 2.5, "home_price": -110, "away_price": -110},
            ),
        ],
        GAME_2: [
            OddsLine(
                game_external_id=GAME_2, home_team=COMETS, away_team=SHARKS,
                commence_time=KICKOFF_2, sportsbook="DemoBook", market_type="moneyline",
                line_data={"home": -150, "away": 130},
            ),
        ],
    }


def default_player_props_by_game() -> dict[str, list[PlayerProp]]:
    return {
        GAME_1: [
            PlayerProp(
                game_external_id=GAME_1, home_team=HAWKS, away_team=WOLVES,
                commence_time=KICKOFF_1, sportsbook="DemoBook",
                player_external_id="demo-player-1", player_name="Alex Fixture",
                prop_type="player_pass_tds", line=1.5, over_odds=-115, under_odds=-105,
            ),
        ],
    }


def default_injuries() -> list[InjuryReport]:
    return [
        InjuryReport(
            game_external_id=GAME_1, player_external_id="demo-player-2",
            player_name="Riley Sample", team=HAWKS, status="questionable",
            description="ankle",
        ),
    ]


def default_weather_by_game() -> dict[str, WeatherConditions]:
    return {
        GAME_1: WeatherConditions(
            game_external_id=GAME_1, temperature_f=68.0, wind_mph=6.0,
            precipitation_pct=0.0, conditions="clear",
        ),
        GAME_2: WeatherConditions(
            game_external_id=GAME_2, temperature_f=55.0, wind_mph=12.0,
            precipitation_pct=20.0, conditions="overcast",
        ),
    }


def default_roster_by_team() -> dict[str, list[RosterEntry]]:
    return {
        HAWKS: [
            RosterEntry(team=HAWKS, player_external_id="demo-player-1", player_name="Alex Fixture", position="QB", depth_chart_rank=1),
            RosterEntry(team=HAWKS, player_external_id="demo-player-2", player_name="Riley Sample", position="WR", depth_chart_rank=1),
        ],
        WOLVES: [
            RosterEntry(team=WOLVES, player_external_id="demo-player-3", player_name="Jordan Placeholder", position="QB", depth_chart_rank=1),
            RosterEntry(team=WOLVES, player_external_id="demo-player-4", player_name="Casey Mockford", position="RB", depth_chart_rank=1),
        ],
        COMETS: [
            RosterEntry(team=COMETS, player_external_id="demo-player-5", player_name="Taylor Scenario", position="QB", depth_chart_rank=1),
        ],
        SHARKS: [
            RosterEntry(team=SHARKS, player_external_id="demo-player-6", player_name="Morgan Synthetic", position="QB", depth_chart_rank=1),
        ],
    }


def default_schedule() -> list[ScheduleEntry]:
    return [
        ScheduleEntry(
            game_external_id=GAME_1, home_team=HAWKS, away_team=WOLVES,
            scheduled_start=KICKOFF_1, stadium="Demo Field", status="scheduled",
            season_type="regular", week=1,
        ),
        ScheduleEntry(
            game_external_id=GAME_2, home_team=COMETS, away_team=SHARKS,
            scheduled_start=KICKOFF_2, stadium="Demo Park", status="scheduled",
            season_type="regular", week=1,
        ),
    ]


def default_news() -> list[NewsArticle]:
    return [
        NewsArticle(
            headline="Demo Hawks Sign Practice-Squad Fixture",
            url="https://example.com/demo/hawks-fixture",
            source="DemoWire", published_at=KICKOFF_1, related_teams=[HAWKS],
        ),
        NewsArticle(
            headline="Demo Wolves Injury Update: Mockford Limited",
            url="https://example.com/demo/wolves-mockford",
            source="DemoWire", published_at=KICKOFF_1, related_teams=[WOLVES],
        ),
    ]


def default_team_stats_by_game() -> dict[str, list[TeamStatLine]]:
    #: Illustrative only -- proves the model/adapter shape, not a claim that
    #: demo-game-1 has gone final (its schedule entry above is still
    #: "scheduled"). Real state transitions belong to DEMO-3/4's scenario
    #: engine, not this static starter set.
    return {
        GAME_1: [
            TeamStatLine(game_external_id=GAME_1, team=HAWKS, stats={"points": 24, "total_yards": 350}),
            TeamStatLine(game_external_id=GAME_1, team=WOLVES, stats={"points": 17, "total_yards": 290}),
        ],
    }


def default_player_stats_by_game() -> dict[str, list[PlayerStatLine]]:
    return {
        GAME_1: [
            PlayerStatLine(
                game_external_id=GAME_1, player_external_id="demo-player-1",
                player_name="Alex Fixture", team=HAWKS,
                stats={"passing_yards": 240, "passing_tds": 2},
            ),
            PlayerStatLine(
                game_external_id=GAME_1, player_external_id="demo-player-3",
                player_name="Jordan Placeholder", team=WOLVES,
                stats={"passing_yards": 210, "passing_tds": 1},
            ),
        ],
    }
