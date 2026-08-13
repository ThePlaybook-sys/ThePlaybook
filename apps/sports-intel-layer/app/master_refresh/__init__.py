"""Master Refresh (Volume 2 §8, Phase 3E-2) -- the daily job that
establishes each day's game identities and assembles whatever Phase 3
intelligence is currently available into `daily_game_intelligence`.

Decision 1 (Mac, 2026-08-13): Master Refresh owns Schedule refresh, game
creation/update, season/week context, the roster/depth-chart morning
refresh, travel/rest derivation, and `daily_game_intelligence` assembly.
It does NOT fetch odds, player props, injuries, weather, or news --
those remain owned by their own specialized workers (not yet built); this
package only ever reads whatever those workers have already persisted.

This package deliberately has no dependency on how it gets invoked (no
Railway/cron code here) -- `run_master_refresh` is a plain async function,
callable directly from a script, a test, or (later) a thin Railway Cron
Job entry point, per Decision 6's "finite job: start -> execute -> exit"
shape.
"""
from __future__ import annotations

from app.master_refresh.run import MasterRefreshResult, run_master_refresh

__all__ = ["MasterRefreshResult", "run_master_refresh"]
