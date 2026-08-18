-- Phase 3F-3: DB-level append-only hardening for team_stats/player_stats
-- (Volume 3 §4.0/§6 addition)
--
-- Application-layer correction-aware persistence (Phase 3E-8,
-- app.persistence.team_stats/player_stats) already gives the correct
-- behavior: an unchanged incoming line inserts nothing, a genuine
-- correction inserts a new row, the previous row is never touched. Volume
-- 3 §6 has flagged since 3E-8 that this discipline was application
-- convention only, not enforced at the database level -- unlike
-- odds_snapshots/injury_reports/weather_snapshots/depth_chart_snapshots/
-- referee_assignments, which have all carried the block_snapshot_updates()
-- trigger since the original 2026-08-07 migration.
--
-- This closes that gap the same way, reusing the already-existing
-- block_snapshot_updates() function verbatim -- no new function, no
-- schema/column change. Deliberately NOT a uniqueness constraint: a
-- uniqueness constraint on (game_id, team_id)/(game_id, player_id) would
-- block the correction-history INSERTs this application logic depends on
-- (a corrected row is a second, later row for the same pair, by design).
-- INSERTs remain completely unrestricted; only UPDATE is blocked.

create trigger trg_block_team_stats_update
  before update on team_stats
  for each row execute function block_snapshot_updates();

create trigger trg_block_player_stats_update
  before update on player_stats
  for each row execute function block_snapshot_updates();
