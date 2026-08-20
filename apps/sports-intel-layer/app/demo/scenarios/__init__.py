"""Bundled DEMO-3 scenario definitions -- static JSON files, loaded and
validated through `app.demo.scenario.load_scenario`. One file so far
(`minimal_pregame_to_postgame.json`, DEMO-3's one approved minimal
scenario); a richer library is DEMO-5's job, not this module's.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.demo.scenario import Scenario, load_scenario

_SCENARIOS_DIR = Path(__file__).parent


def load_bundled_scenario(name: str) -> Scenario:
    """Loads and validates a bundled scenario by filename stem, e.g.
    `load_bundled_scenario("minimal_pregame_to_postgame")`."""
    path = _SCENARIOS_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no bundled scenario named {name!r} (looked for {path})")
    data = json.loads(path.read_text())
    return load_scenario(data)


def list_bundled_scenarios() -> list[dict]:
    """Lists every bundled scenario's identifying metadata (DEMO-4's
    "list available scenarios" control endpoint) without constructing a
    `ScenarioRunner` or touching Supabase -- each file is parsed and
    validated (so a broken bundled file surfaces here, not as a confusing
    404 on load), but never run.
    """
    scenarios = []
    for path in sorted(_SCENARIOS_DIR.glob("*.json")):
        scenario = load_scenario(json.loads(path.read_text()))
        scenarios.append(
            {
                "name": path.stem,
                "scenario_id": scenario.scenario_id,
                "title": scenario.title,
                "description": scenario.description,
                "version": scenario.version,
                "step_count": len(scenario.steps),
            }
        )
    return scenarios
