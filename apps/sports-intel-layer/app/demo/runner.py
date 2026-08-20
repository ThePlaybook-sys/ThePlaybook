"""Demo Scenario Runner (DEMO-3, docs/blueprint/demo-simulation-environment.md
Section 6/7 -- "Scenario Runner -> owns virtual_now -> constructs Demo*Adapters
from scenario-step data -> invokes the EXISTING run_* worker entrypoints ->
... uses the REAL persistence layer -> writes ONLY to the isolated Demo
Supabase project").

This module never re-implements a worker, persistence function, or identity
resolver. It only:
  1. Owns `virtual_now`, moved forward exclusively by explicit scenario
     steps (never the wall clock).
  2. Builds a `Demo*Adapter` (DEMO-2) from the current step's scripted
     `provider_data` and passes it into the matching real worker entrypoint
     through the DEMO-3 adapter-injection seam (`app.workers.*`,
     `app.master_refresh.run`) -- exactly the same optional `*_adapter=`
     parameters those modules already accept for any caller, demo or not.
  3. Keeps its own control state (which scenario, which step, virtual_now,
     status, errors, checkpoints) in memory only, per Mac's explicit
     preference -- never a new Demo-only Supabase table.

`supabase_client` is the one real thing here: every worker call still goes
through the real `app.persistence.*` modules and writes through that same
client, so whatever Supabase project it points to is exactly what receives
the scenario's data. `app.main` (or a test) is responsible for pointing it
at the isolated demo project -- this module has no opinion about that and
performs no isolation check itself (that's `app.environment_safety`'s job
at startup, and `app.demo.reset`'s own independent guard at the
destructive-reset boundary).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from app.adapters.cache import InMemoryCacheBackend
from app.demo.adapters import (
    DemoInjuryAdapter,
    DemoNewsAdapter,
    DemoOddsAdapter,
    DemoPlayerPropsAdapter,
    DemoPlayerStatsAdapter,
    DemoRosterAdapter,
    DemoScheduleAdapter,
    DemoTeamStatsAdapter,
    DemoWeatherAdapter,
)
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
from app.demo.scenario import Scenario, ScenarioStep
from app.master_refresh.run import run_master_refresh
from app.workers.injury_worker import run_injury_worker
from app.workers.news_worker import run_news_worker
from app.workers.odds_worker import run_odds_worker
from app.workers.player_props_worker import run_player_props_worker
from app.workers.postgame_worker import run_postgame_worker
from app.workers.pregame_worker import run_pregame_worker
from app.workers.weather_worker import run_weather_worker

logger = logging.getLogger(__name__)

#: Every worker entrypoint the runner dispatches to still declares a
#: real vendor `*_client`/`*_key` parameter as required (not `| None`),
#: even when a Demo*Adapter is injected and that parameter is never
#: touched (see each worker's own `adapter or RealVendorAdapter(...)`
#: line). Pointing the placeholder client at a host that resolves to
#: nothing, with zero respx/network route ever registered for it, is the
#: same structural proof `tests/test_adapter_injection_seam.py` already
#: established: if a worker ever did fall through to real construction
#: despite an adapter being injected, the very first attempted call would
#: fail loudly (connection error), never silently succeed against a real
#: vendor.
UNREACHABLE_PLACEHOLDER_URL = "https://demo-adapter-injected.invalid"
UNUSED_PLACEHOLDER_KEY = "demo-unused-placeholder-key"

#: The real vendor's own `provider_name` for each category, per DEMO-3's
#: adapter-injection seam -- see app.demo.adapters' module docstring
#: ("provider_name (DEMO-3 addition)") for why this must be the REAL
#: vendor name, not "demo": several real, unmodified persistence modules
#: key `game_provider_ids`/`team_provider_ids` identity-linkage rows by
#: this literal string, and a scenario's odds/props/injury/team-stats/
#: player-stats data is worthless to those lookups unless it's linked
#: under the same name the real adapter would have reported.
_SPORTSDATAIO = "sportsdataio"
_THE_ODDS_API = "the_odds_api"
_WEATHERAPI = "weatherapi"
_NEWSAPI = "newsapi"


class ScenarioRunnerError(RuntimeError):
    """Raised for a runner usage error (no scenario loaded, step index out
    of range, unsupported action reached dispatch despite passing schema
    validation). Never raised for a worker's own business-logic failure --
    those are captured in `StepOutcome.error` instead, matching every real
    worker's own "report partial/failed status, don't raise" convention."""


@dataclass
class StepOutcome:
    step_index: int
    action: str
    virtual_now: datetime
    #: Whatever the dispatched worker's own Result object was (e.g.
    #: `MasterRefreshResult`, `OddsWorkerResult`) -- `None` for
    #: `advance_time`/`checkpoint`, which invoke no worker.
    result: Any = None
    checkpoint_note: str | None = None
    error: str | None = None


class ScenarioRunner:
    """Drives one loaded `Scenario` against the real worker entrypoints,
    in memory, one step at a time. One instance = one scenario run; create
    a fresh instance (or call `load` again) to start another.

    Each dispatched worker call gets its own brand-new `InMemoryCacheBackend`,
    never one shared across steps (discovered necessary, not designed in
    up front: `app.adapters.cache.CachingAdapter`'s TTL expiry is real
    wall-clock time, oblivious to `virtual_now` -- two scenario steps
    scripted hours apart in virtual time can execute mere milliseconds
    apart in real time, so a shared cache would silently serve step 2 a
    stale cached response from step 1's adapter instead of ever calling
    step 2's freshly-injected one. A scenario step's whole point is
    "this is the data as of this moment"; caching across steps would
    undermine that guarantee for exactly the categories -- odds, in
    particular -- DEMO-3's own event-injection requirement needs to prove
    changed).
    """

    def __init__(self, *, supabase_client: httpx.AsyncClient):
        self.supabase_client = supabase_client
        self._placeholder_client = httpx.AsyncClient(base_url=UNREACHABLE_PLACEHOLDER_URL)

        self.scenario: Scenario | None = None
        self.virtual_now: datetime | None = None
        self.step_index: int = 0
        #: idle -> loaded -> running -> completed | failed
        self.status: str = "idle"
        self.outcomes: list[StepOutcome] = []
        self.checkpoints: list[str] = []
        self.errors: list[str] = []

    async def aclose(self) -> None:
        await self._placeholder_client.aclose()

    def load(self, scenario: Scenario) -> None:
        """Resets all control state to the start of `scenario`. Does not
        touch Supabase -- loading is pure in-memory bookkeeping, exactly
        like `load_scenario` itself."""
        self.scenario = scenario
        self.virtual_now = scenario.initial_virtual_now
        self.step_index = 0
        self.status = "loaded"
        self.outcomes = []
        self.checkpoints = []
        self.errors = []

    @property
    def is_finished(self) -> bool:
        return self.scenario is not None and self.step_index >= len(self.scenario.steps)

    async def run_next_step(self) -> StepOutcome:
        if self.scenario is None:
            raise ScenarioRunnerError("no scenario loaded -- call load() first")
        if self.is_finished:
            raise ScenarioRunnerError(f"scenario {self.scenario.scenario_id!r} has no more steps")

        step = self.scenario.steps[self.step_index]
        self.virtual_now = step.virtual_now
        self.status = "running"

        try:
            result = await self._dispatch(step)
            outcome = StepOutcome(
                step_index=self.step_index, action=step.action, virtual_now=step.virtual_now,
                result=result, checkpoint_note=step.checkpoint_note,
            )
        except Exception as exc:  # noqa: BLE001 -- captured, not swallowed: see StepOutcome.error
            message = f"step {self.step_index} ({step.action}) raised {exc.__class__.__name__}: {exc}"
            logger.error(message)
            self.errors.append(message)
            outcome = StepOutcome(
                step_index=self.step_index, action=step.action, virtual_now=step.virtual_now,
                checkpoint_note=step.checkpoint_note, error=message,
            )
            self.status = "failed"
            self.outcomes.append(outcome)
            self.step_index += 1
            return outcome

        if step.checkpoint_note:
            self.checkpoints.append(step.checkpoint_note)
        self.outcomes.append(outcome)
        self.step_index += 1
        if self.is_finished and self.status != "failed":
            self.status = "completed"
        return outcome

    async def run_to_completion(self) -> list[StepOutcome]:
        while not self.is_finished:
            await self.run_next_step()
        return self.outcomes

    async def run_until_checkpoint(self) -> list[StepOutcome]:
        """Runs steps starting from the current position until (and
        including) the next step whose `checkpoint_note` is set, or until
        the scenario completes or a step errors -- whichever comes first
        (DEMO-4's "run to defined checkpoint where supported" control
        endpoint). Returns just the outcomes produced by this call, not
        the full run-so-far (unlike `run_to_completion`, callers of this
        one are stepping through a scenario incrementally and only want
        to know what just happened)."""
        outcomes: list[StepOutcome] = []
        while not self.is_finished:
            outcome = await self.run_next_step()
            outcomes.append(outcome)
            if outcome.checkpoint_note or outcome.error:
                break
        return outcomes

    async def _dispatch(self, step: ScenarioStep) -> Any:
        if step.action == "advance_time":
            return None
        if step.action == "checkpoint":
            return None
        if step.action == "run_master_refresh":
            return await run_master_refresh(
                supabase_client=self.supabase_client,
                sportsdataio_client=self._placeholder_client,
                sportsdataio_api_key=UNUSED_PLACEHOLDER_KEY,
                cache_backend=InMemoryCacheBackend(),
                today=self.virtual_now.date(),
                schedule_adapter=self._build_schedule_adapter(step),
                roster_adapter=self._build_roster_adapter(step),
                **step.worker_kwargs,
            )
        if step.action == "run_odds_worker":
            return await run_odds_worker(
                supabase_client=self.supabase_client,
                the_odds_api_client=self._placeholder_client,
                the_odds_api_key=UNUSED_PLACEHOLDER_KEY,
                cache_backend=InMemoryCacheBackend(),
                now=self.virtual_now,
                odds_adapter=self._build_odds_adapter(step),
                **step.worker_kwargs,
            )
        if step.action == "run_player_props_worker":
            return await run_player_props_worker(
                supabase_client=self.supabase_client,
                the_odds_api_client=self._placeholder_client,
                the_odds_api_key=UNUSED_PLACEHOLDER_KEY,
                cache_backend=InMemoryCacheBackend(),
                now=self.virtual_now,
                player_props_adapter=self._build_player_props_adapter(step),
                **step.worker_kwargs,
            )
        if step.action == "run_injury_worker":
            return await run_injury_worker(
                supabase_client=self.supabase_client,
                sportsdataio_client=self._placeholder_client,
                sportsdataio_api_key=UNUSED_PLACEHOLDER_KEY,
                cache_backend=InMemoryCacheBackend(),
                now=self.virtual_now,
                injury_adapter=self._build_injury_adapter(step),
                **step.worker_kwargs,
            )
        if step.action == "run_weather_worker":
            return await run_weather_worker(
                supabase_client=self.supabase_client,
                weatherapi_client=self._placeholder_client,
                weatherapi_key=UNUSED_PLACEHOLDER_KEY,
                cache_backend=InMemoryCacheBackend(),
                now=self.virtual_now,
                weather_adapter=await self._build_weather_adapter(step),
                **step.worker_kwargs,
            )
        if step.action == "run_news_worker":
            return await run_news_worker(
                supabase_client=self.supabase_client,
                newsapi_client=self._placeholder_client,
                newsapi_key=UNUSED_PLACEHOLDER_KEY,
                cache_backend=InMemoryCacheBackend(),
                now=self.virtual_now,
                news_adapter=self._build_news_adapter(step),
                **step.worker_kwargs,
            )
        if step.action == "run_pregame_worker":
            return await run_pregame_worker(
                supabase_client=self.supabase_client,
                the_odds_api_client=self._placeholder_client,
                the_odds_api_key=UNUSED_PLACEHOLDER_KEY,
                sportsdataio_client=self._placeholder_client,
                sportsdataio_api_key=UNUSED_PLACEHOLDER_KEY,
                weatherapi_client=self._placeholder_client,
                weatherapi_key=UNUSED_PLACEHOLDER_KEY,
                cache_backend=InMemoryCacheBackend(),
                now=self.virtual_now,
                odds_adapter=self._build_odds_adapter(step),
                player_props_adapter=self._build_player_props_adapter(step),
                injury_adapter=self._build_injury_adapter(step),
                weather_adapter=await self._build_weather_adapter(step),
                **step.worker_kwargs,
            )
        if step.action == "run_postgame_worker":
            return await run_postgame_worker(
                supabase_client=self.supabase_client,
                sportsdataio_client=self._placeholder_client,
                sportsdataio_api_key=UNUSED_PLACEHOLDER_KEY,
                now=self.virtual_now,
                schedule_adapter=self._build_schedule_adapter(step),
                team_stats_adapter=self._build_team_stats_adapter(step),
                player_stats_adapter=self._build_player_stats_adapter(step),
                **step.worker_kwargs,
            )
        raise ScenarioRunnerError(
            f"action {step.action!r} passed scenario-schema validation but has no dispatch handler -- "
            "app.demo.scenario.VALID_ACTIONS and this module's _dispatch have drifted apart"
        )

    # -- Demo*Adapter construction from a step's scripted provider_data --
    #
    # Each helper builds exactly the category the corresponding worker
    # needs, defaulting to an *empty* Demo*Adapter (not DEMO-2's starter
    # data) when a step's provider_data omits that category -- a scenario
    # step's data is meant to be exhaustive for what it drives, not
    # silently topped up with DEMO-2's unrelated fixture content.

    @staticmethod
    def _should_fail(step: ScenarioStep, category: str) -> bool:
        """`inject_failure=True` fails every adapter a step builds -- the
        right tool for a single-worker step, where only one adapter is
        ever built anyway. `fail_categories` (DEMO-5) fails only the
        named category, the tool a multi-category step
        (`run_pregame_worker`) needs to fail exactly one of its four
        adapters while the other three build and succeed normally."""
        return step.inject_failure or category in step.fail_categories

    def _build_odds_adapter(self, step: ScenarioStep) -> DemoOddsAdapter:
        raw = step.provider_data.get("odds", {})
        odds_by_game = {game_id: [OddsLine(**line) for line in lines] for game_id, lines in raw.items()}
        return DemoOddsAdapter(
            odds_by_game=odds_by_game, fail=self._should_fail(step, "odds"), provider_name=_THE_ODDS_API
        )

    def _build_player_props_adapter(self, step: ScenarioStep) -> DemoPlayerPropsAdapter:
        raw = step.provider_data.get("player_props", {})
        props_by_game = {game_id: [PlayerProp(**prop) for prop in props] for game_id, props in raw.items()}
        return DemoPlayerPropsAdapter(
            props_by_game=props_by_game, fail=self._should_fail(step, "player_props"), provider_name=_THE_ODDS_API
        )

    def _build_injury_adapter(self, step: ScenarioStep) -> DemoInjuryAdapter:
        raw = step.provider_data.get("injury", [])
        injuries = [InjuryReport(**report) for report in raw]
        return DemoInjuryAdapter(
            injuries=injuries, fail=self._should_fail(step, "injury"), provider_name=_SPORTSDATAIO
        )

    async def _resolve_internal_game_id(self, sportsdataio_provider_game_id: str) -> str | None:
        """Weather is the one category (`app.workers.weather_worker`'s own
        documented "no `game_provider_ids` hop" design) keyed by this
        project's own internal `games.id`, never a provider id -- which a
        scenario step, authored before that id is generated, has no way
        to know statically. This is a Demo-only gap, not a production
        one: real callers never need this lookup because they already
        have the internal id in hand from whatever query found the game
        in the first place. Resolves the same way any other reverse
        lookup in this codebase already does (`game_provider_ids`,
        `provider_name=sportsdataio`) -- no new query shape, no
        production code touched.
        """
        headers = {
            "Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_ROLE_KEY']}",
            "apikey": os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        }
        response = await self.supabase_client.get(
            "/rest/v1/game_provider_ids",
            params={
                "provider_name": "eq.sportsdataio",
                "provider_game_id": f"eq.{sportsdataio_provider_game_id}",
                "select": "game_id",
            },
            headers=headers,
        )
        if response.status_code != 200:
            return None
        rows = response.json()
        return rows[0]["game_id"] if rows else None

    async def _build_weather_adapter(self, step: ScenarioStep) -> DemoWeatherAdapter:
        raw = step.provider_data.get("weather", {})
        weather_by_game: dict[str, WeatherConditions] = {}
        for sportsdataio_provider_game_id, conditions in raw.items():
            internal_game_id = await self._resolve_internal_game_id(sportsdataio_provider_game_id)
            if internal_game_id is not None:
                weather_by_game[internal_game_id] = WeatherConditions(game_external_id=internal_game_id, **conditions)
        return DemoWeatherAdapter(
            weather_by_game=weather_by_game, fail=self._should_fail(step, "weather"), provider_name=_WEATHERAPI
        )

    def _build_roster_adapter(self, step: ScenarioStep) -> DemoRosterAdapter:
        raw = step.provider_data.get("roster", {})
        roster_by_team = {team: [RosterEntry(**entry) for entry in entries] for team, entries in raw.items()}
        return DemoRosterAdapter(
            roster_by_team=roster_by_team, fail=self._should_fail(step, "roster"), provider_name=_SPORTSDATAIO
        )

    def _build_schedule_adapter(self, step: ScenarioStep) -> DemoScheduleAdapter:
        raw = step.provider_data.get("schedule", [])
        schedule = [ScheduleEntry(**entry) for entry in raw]
        return DemoScheduleAdapter(
            schedule=schedule, fail=self._should_fail(step, "schedule"), provider_name=_SPORTSDATAIO
        )

    def _build_news_adapter(self, step: ScenarioStep) -> DemoNewsAdapter:
        raw = step.provider_data.get("news", [])
        articles = [NewsArticle(**article) for article in raw]
        return DemoNewsAdapter(
            articles=articles, fail=self._should_fail(step, "news"), provider_name=_NEWSAPI
        )

    def _build_team_stats_adapter(self, step: ScenarioStep) -> DemoTeamStatsAdapter:
        raw = step.provider_data.get("team_stats", {})
        stats_by_game = {game_id: [TeamStatLine(**line) for line in lines] for game_id, lines in raw.items()}
        return DemoTeamStatsAdapter(
            stats_by_game=stats_by_game, fail=self._should_fail(step, "team_stats"), provider_name=_SPORTSDATAIO
        )

    def _build_player_stats_adapter(self, step: ScenarioStep) -> DemoPlayerStatsAdapter:
        raw = step.provider_data.get("player_stats", {})
        stats_by_game = {game_id: [PlayerStatLine(**line) for line in lines] for game_id, lines in raw.items()}
        return DemoPlayerStatsAdapter(
            stats_by_game=stats_by_game, fail=self._should_fail(step, "player_stats"), provider_name=_SPORTSDATAIO
        )
