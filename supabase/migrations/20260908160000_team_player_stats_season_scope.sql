-- Phase 8.3A (2026-09-08, MANSA HQ-authorized) -- season-scoped team/player
-- statistics support + duplicate-provider-execution idempotency guard.
--
-- CONTEXT (2026-09-08 Player/Team Performance Data Audit, accepted as
-- evidence baseline): the one confirmed-real MySportsFeeds stats source
-- (team_stats_totals / standings) is SEASON-AGGREGATE, not per-game.
-- Canonical team_stats/player_stats currently require game_id not null
-- (Phase 3E-8, 20260807211421_sports_data_tables.sql), so there is no
-- honest way to persist a season-aggregate row without either fabricating
-- a game_id (explicitly forbidden by HQ) or widening the schema. This is
-- the minimal widening HQ's Phase 8.3 audit proposed and this pass
-- authorizes: make game_id nullable, add a nullable season_id reusing the
-- existing seasons entity (matches games.season_id's own existing
-- nullable-FK precedent, same migration), and require at least one of the
-- two on every row so a row can never be scopeless.
--
-- BACKWARD COMPATIBILITY: strictly widening. Every existing team_stats/
-- player_stats row already has a non-null game_id, so the new check
-- constraint is satisfied by 100% of existing data with no backfill.
-- The only real consumers of these two tables anywhere in this codebase
-- are app.persistence.team_stats/player_stats (Postgame Ingestion Worker,
-- Phase 3E-8) -- confirmed by direct grep before writing this migration --
-- and both always pass a real, non-null game_id at every existing call
-- site, so their `_latest_team_stats_row`/`_latest_player_stats_row`
-- lookups (keyed on game_id) are unaffected. Phase 8.1's unsupported.py
-- only names these tables in a text string, not a live query. No other
-- Phase 4/5.6/7.2/7.3/Probability Modeling code path touches either table.
alter table team_stats
  alter column game_id drop not null,
  add column season_id uuid references seasons(id),
  add constraint team_stats_game_or_season_scope
    check (game_id is not null or season_id is not null);

alter table player_stats
  alter column game_id drop not null,
  add column season_id uuid references seasons(id),
  add constraint player_stats_game_or_season_scope
    check (game_id is not null or season_id is not null);

-- Supporting index for the new season-scoped "latest row" read pattern
-- (order by created_at desc limit 1, keyed on (team_id/player_id,
-- season_id) instead of game_id) -- same partial-index-on-the-new-scope
-- shape already used by this project's other season/date-scoped lookups.
-- Existing game-scoped queries are untouched; game_id keeps its existing
-- implicit index coverage via the FK.
create index idx_team_stats_season_lookup
  on team_stats (team_id, season_id, created_at desc)
  where season_id is not null;

create index idx_player_stats_season_lookup
  on player_stats (player_id, season_id, created_at desc)
  where season_id is not null;

-- Execution-safety guard (HQ Locked Finding 6): the disclosed duplicate
-- MySportsFeeds provider execution and duplicate depth_chart_snapshots
-- write pair (Phase 8.2 diagnostics, both caused by an overlapping
-- Railway deployment race, both disclosed rather than silently corrected)
-- are a real infrastructure concern. Existing idempotency/run-tracking
-- precedents in this codebase (master_refresh_runs, recommendations.
-- correlation_id, odds_api_credit_ledger, news_provider_daily_quota /
-- news_worker_poll_state -- all inspected before writing this) each solve
-- a different, narrower problem (slate-wide run completion, a single
-- column's uniqueness, quota accounting, per-entity due/not-due polling)
-- and none of them already cover "prevent one temporary activation pass
-- from firing its one-shot write twice." This is the smallest new
-- mechanism that does: a hook writes exactly one row per pass using a
-- pass-specific run_key before doing any real work; a duplicate run_key
-- (a second, overlapping container boot) hits the unique constraint and
-- PostgREST returns 409, which the caller catches and treats as "already
-- run this pass, skip" -- no explicit ON CONFLICT clause needed for that
-- behavior, the plain unique constraint is sufficient.
create table activation_run_markers (
  id uuid primary key default gen_random_uuid(),
  run_key text not null unique,
  completed_at timestamptz not null default now()
);

-- Internal accounting table, not user data -- same "RLS enabled, no
-- policy" convention already established for odds_api_credit_ledger/
-- display_id_counters/recommendation_agent_outputs/consensus_snapshots
-- (service-role access only, via the service key's RLS bypass).
alter table activation_run_markers enable row level security;
