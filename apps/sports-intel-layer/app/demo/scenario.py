"""Demo scenario schema (DEMO-3, docs/blueprint/demo-simulation-environment.md
Section 6). Plain dataclasses over JSON -- no new dependency (no YAML), per
Mac's explicit instruction, and the same "small, explicit, fails early with
a useful error" discipline this codebase already applies to its own
provider-response normalization (see `app.adapters.errors.ProviderDataError`
and every adapter's `_normalize_*` pattern).

A scenario is a static, versioned description of a story: an ordered list
of steps, each advancing a virtual clock and/or invoking one real worker
with scripted Demo-adapter data. Loading a scenario never touches a
worker, an adapter, or Supabase -- it only parses and validates. Running
one is `app.demo.runner.ScenarioRunner`'s job.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

#: The small, fixed action vocabulary DEMO-3 supports (per Mac's explicit
#: "do not build a giant scripting language" instruction). Each name maps
#: to exactly one real worker entrypoint (or a pure clock/checkpoint
#: no-op) in `app.demo.runner.ACTIONS`.
VALID_ACTIONS = frozenset(
    {
        "advance_time",
        "run_master_refresh",
        "run_odds_worker",
        "run_player_props_worker",
        "run_injury_worker",
        "run_weather_worker",
        "run_news_worker",
        "run_pregame_worker",
        "run_postgame_worker",
        "checkpoint",
    }
)


class ScenarioValidationError(ValueError):
    """Raised when a scenario definition is structurally invalid. Always
    fatal -- a malformed scenario must fail at load time, never partway
    through a run."""


@dataclass
class ScenarioStep:
    #: When this step executes, in virtual time. Must be >= every prior
    #: step's virtual_now (steps only ever move forward) -- checked at
    #: load time, not left to fail confusingly mid-run.
    virtual_now: datetime
    action: str
    #: Scripted provider data for this step, keyed by adapter category
    #: ("odds", "player_props", "injury", "weather", "news", "schedule",
    #: "roster", "team_stats", "player_stats"). Shape is category-specific
    #: -- see `app.demo.runner.build_adapter` for exactly what each
    #: category expects. Empty for actions that need no adapter data
    #: (`advance_time`, `checkpoint`, and `run_pregame_worker`/
    #: `run_postgame_worker`, which delegate to already-configured
    #: category workers rather than owning their own fetch).
    provider_data: dict = field(default_factory=dict)
    #: True to make EVERY adapter this step builds raise
    #: `ProviderUnavailableError` (the DEMO-2 `fail=True` mechanism)
    #: instead of returning data -- failure injection, per the approved
    #: scope. For a single-worker step (`run_odds_worker`, etc.) this is
    #: already category-specific, since only one adapter is built at all.
    inject_failure: bool = False
    #: DEMO-5 addition: for a multi-category step (`run_pregame_worker`,
    #: which builds all four of odds/player_props/injury/weather from one
    #: step), `inject_failure` alone can't express "only THIS one
    #: category is down" -- it would fail all four together. Naming a
    #: category here (e.g. `["injury"]`) fails only that adapter,
    #: leaving the others to build and succeed normally. Empty for every
    #: single-worker step; `inject_failure=True` remains the right tool
    #: when the whole step's one category should fail.
    fail_categories: list[str] = field(default_factory=list)
    #: Human-readable narration for an operator watching a scenario run.
    #: Never required, always safe to omit.
    checkpoint_note: str | None = None
    #: Free-form key/value overrides passed straight through to the
    #: dispatched worker call (e.g. `target_game_ids`) -- kept generic on
    #: purpose rather than one field per worker's own kwargs, since the
    #: worker functions themselves already define what's valid; a wrong
    #: key surfaces as a normal `TypeError` from the real function call,
    #: not a silently-ignored scenario field.
    worker_kwargs: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.action not in VALID_ACTIONS:
            raise ScenarioValidationError(
                f"unknown scenario action {self.action!r} -- must be one of {sorted(VALID_ACTIONS)}"
            )


@dataclass
class Scenario:
    scenario_id: str
    title: str
    description: str
    version: str
    #: Real Playbook capabilities this scenario depends on, e.g.
    #: ["phase_3"] -- so a scenario referencing a not-yet-built capability
    #: is mechanically identifiable (Section 6 of the approved design),
    #: never silently run. DEMO-3 only ever produces "phase_3" scenarios.
    phase_requirements: list[str]
    initial_virtual_now: datetime
    #: The synthetic slate this scenario operates over -- game/team/player
    #: identifiers the steps' `provider_data` reference. Not validated
    #: against any schema here (that's Demo Supabase's own job once a step
    #: actually persists); this is just the scenario's own bookkeeping of
    #: what it's about, useful for an operator UI later.
    slate: dict
    steps: list[ScenarioStep]

    def __post_init__(self) -> None:
        if not self.scenario_id:
            raise ScenarioValidationError("scenario_id is required")
        if not self.steps:
            raise ScenarioValidationError(f"scenario {self.scenario_id!r} has no steps")
        if "phase_3" not in self.phase_requirements and self.phase_requirements:
            # Not fatal -- a scenario is allowed to require only phases
            # that exist -- but nothing DEMO-3 builds should ever declare
            # phase_4/phase_5, per the explicit phase-gating instruction.
            for phase in self.phase_requirements:
                if phase not in {"phase_3"}:
                    raise ScenarioValidationError(
                        f"scenario {self.scenario_id!r} declares phase_requirements={self.phase_requirements!r} "
                        "-- DEMO-3 may only build phase_3 scenarios; a future phase's scenario belongs to a "
                        "later DEMO-N step, once that phase actually ships"
                    )
        previous_time = self.initial_virtual_now
        for index, step in enumerate(self.steps):
            if step.virtual_now < previous_time:
                raise ScenarioValidationError(
                    f"scenario {self.scenario_id!r} step {index} has virtual_now={step.virtual_now!r}, "
                    f"earlier than the preceding step's {previous_time!r} -- steps must move forward in time"
                )
            previous_time = step.virtual_now


def load_scenario(data: dict) -> Scenario:
    """Parses and validates a scenario from a plain dict (as loaded from
    JSON) -- raises `ScenarioValidationError` immediately on anything
    malformed, rather than constructing a partially-valid `Scenario`."""
    required_top_level = {
        "scenario_id", "title", "description", "version",
        "phase_requirements", "initial_virtual_now", "slate", "steps",
    }
    missing = required_top_level - data.keys()
    if missing:
        raise ScenarioValidationError(f"scenario definition missing required field(s): {sorted(missing)}")

    try:
        initial_virtual_now = datetime.fromisoformat(data["initial_virtual_now"])
    except (TypeError, ValueError) as exc:
        raise ScenarioValidationError(f"initial_virtual_now is not a valid ISO datetime: {exc}") from exc

    steps: list[ScenarioStep] = []
    for index, raw_step in enumerate(data["steps"]):
        required_step_fields = {"virtual_now", "action"}
        missing_step = required_step_fields - raw_step.keys()
        if missing_step:
            raise ScenarioValidationError(f"step {index} missing required field(s): {sorted(missing_step)}")
        try:
            step_time = datetime.fromisoformat(raw_step["virtual_now"])
        except (TypeError, ValueError) as exc:
            raise ScenarioValidationError(f"step {index} virtual_now is not a valid ISO datetime: {exc}") from exc
        steps.append(
            ScenarioStep(
                virtual_now=step_time,
                action=raw_step["action"],
                provider_data=raw_step.get("provider_data", {}),
                inject_failure=raw_step.get("inject_failure", False),
                checkpoint_note=raw_step.get("checkpoint_note"),
                worker_kwargs=raw_step.get("worker_kwargs", {}),
                fail_categories=raw_step.get("fail_categories", []),
            )
        )

    return Scenario(
        scenario_id=data["scenario_id"],
        title=data["title"],
        description=data["description"],
        version=data["version"],
        phase_requirements=list(data["phase_requirements"]),
        initial_virtual_now=initial_virtual_now,
        slate=data["slate"],
        steps=steps,
    )
