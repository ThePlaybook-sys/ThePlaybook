-- Milestone 4.9 (Recommendation Worker), Master Refresh run marker decision
-- (approved 2026-08-24): the durable bridge between "Master Refresh
-- completed" and "the Recommendation Worker may safely process this
-- slate" -- confirmed by direct inspection that no such durable record
-- existed anywhere before this migration (MasterRefreshResult was a
-- pure in-memory dataclass, never persisted).
--
-- status vocabulary mirrors MasterRefreshResult.status exactly (Phase
-- 3E-2/3F), plus 'running' for the row's state between start and
-- completion -- no second, unrelated vocabulary invented.
create table master_refresh_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  status text not null default 'running' check (status in ('running', 'success', 'partial', 'failed')),
  season_string text,
  games_in_slate integer,
  created_at timestamptz not null default now()
);

-- Supports the Recommendation Worker's own discovery query: "the most
-- recent completed-or-partial run", without scanning 'running'/'failed'
-- rows.
create index idx_master_refresh_runs_status_completed
  on master_refresh_runs (status, completed_at desc);
