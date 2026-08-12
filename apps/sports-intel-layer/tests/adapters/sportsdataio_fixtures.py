"""Loader for tests/fixtures/sportsdataio/ -- see that directory's
PROVENANCE.md for what's CONFIRMED FROM LIVE FREE TRIAL / CONFIRMED FROM
PROVIDER DOCUMENTATION / ASSUMED / DEFERRED PRODUCTION VERIFICATION in each
fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sportsdataio"


def load(name: str):
    return json.loads((_FIXTURES_DIR / name).read_text())
