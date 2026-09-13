"""Wiring tests for the TEMPORARY SF@LAR Live Proof startup hook
(2026-09-13, MANSA HQ-authorized "SF@LAR LIVE PROOF"). Mirrors
`test_msf_game_boxscore_diagnostic.py`'s own flag-off/flag-on wiring
tests exactly -- proves only that the hook registers/doesn't register
correctly; the underlying behavior it calls
(`app.workers.msf_postgame_worker.run_msf_postgame_capture`) is already
thoroughly tested directly. This hook and this test file are both
reverted once the one authorized live call has been made and verified.
"""
from __future__ import annotations

import os


def test_hook_is_not_registered_when_flag_is_unset(monkeypatch):
    import importlib

    import app.main as main_module

    try:
        monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "dev")
        monkeypatch.delenv("RUN_MSF_POSTGAME_SF_LAR_LIVE_PROOF", raising=False)
        importlib.reload(main_module)
        names = [getattr(h, "__name__", "") for h in main_module.app.router.on_startup]
        assert "_run_sf_lar_live_proof_once" not in names
    finally:
        importlib.reload(main_module)


def test_hook_is_registered_when_flag_is_set(monkeypatch):
    import importlib

    import app.main as main_module

    try:
        monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "dev")
        monkeypatch.setenv("RUN_MSF_POSTGAME_SF_LAR_LIVE_PROOF", "1")
        importlib.reload(main_module)
        names = [getattr(h, "__name__", "") for h in main_module.app.router.on_startup]
        assert "_run_sf_lar_live_proof_once" in names
    finally:
        monkeypatch.delenv("RUN_MSF_POSTGAME_SF_LAR_LIVE_PROOF", raising=False)
        importlib.reload(main_module)
