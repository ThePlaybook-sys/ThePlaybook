"""Loader for the JSON fixtures under tests/fixtures/the_odds_api/ -- see
that directory's PROVENANCE.md for what's CONFIRMED vs ASSUMED in each one.
"""
from __future__ import annotations

import json
from pathlib import Path

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "the_odds_api"


def load(name: str):
    return json.loads((_FIXTURES_DIR / name).read_text())
