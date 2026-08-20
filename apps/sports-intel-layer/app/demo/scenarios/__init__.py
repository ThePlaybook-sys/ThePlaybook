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
    data = json.loads(path.read_text())
    return load_scenario(data)
