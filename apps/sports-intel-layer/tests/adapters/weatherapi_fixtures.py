"""Loader for tests/fixtures/weatherapi/ -- see that directory's
PROVENANCE.md for what's CONFIRMED/ASSUMED/DEFERRED in each fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "weatherapi"


def load(name: str):
    return json.loads((_FIXTURES_DIR / name).read_text())
