-- Phase 3F-1: roster/player-team-membership history + depth-chart persistence
-- redesign (Volume 3 §4.0 addition + correction)
--
-- Decision 1 (Mac, 2026-08-18, 3F reconciliation, Option B): players.team_id
-- remains the fast/current team reference; roster_memberships is a new,
-- separate historical record of team membership over time. Mirrors the
-- insert-on-change/latest-row convention team_stats/player_stats (3E-8)
-- already established, applied to a new entity -- a membership row is
-- inserted only when the observed team differs from the latest known
-- membership for that player (first observation, a team change, and a
-- rejoin are all the same case at the persistence layer: "observed team !=
-- latest known team"). Unlike team_stats/player_stats, this table gets the
-- append-only DB trigger from creation (not retrofitted later, that's
-- Decision 4/3F-3's job for team_stats/player_stats) since it is being
-- built fresh in this phase and a membership row's whole purpose is to
-- never be modified once observed.
--
-- Explicitly NOT representable with current provider data: release/
-- free-agent state. RosterAdapter.fetch_roster only ever returns players
-- currently on a team's roster -- it never returns an explicit "released"
-- event, and this pipeline does not infer release from a player's absence
-- in a later fetch (that would require full-roster-diffing logic this
-- phase does not build, and risks false positives from provider quirks or
-- injured/inactive-but-still-rostered players). A release is therefore
-- simply never recorded; only positive team observations are.

create table roster_memberships (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references players(id) on delete cascade,
  team_id uuid not null references teams(id),
  observed_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index idx_roster_memberships_player_time on roster_memberships(player_id, observed_at desc);

alter table roster_memberships enable row level security;
create policy "public_read" on roster_memberships for select using (true);

create trigger trg_block_roster_memberships_update
  before update on roster_memberships
  for each row execute function block_snapshot_updates();

-- Decision 2 (Mac, 2026-08-18, 3F reconciliation, Option A): depth_chart_snapshots
-- was created 2026-08-07 as game_id-keyed, mirroring odds_snapshots' shape
-- generically per Volume 3's one-line description (line 326). Confirmed by
-- direct fixture read (tests/fixtures/sportsdataio/depth_charts_normal.json)
-- that SportsDataIO's real DepthCharts payload is genuinely team-scoped
-- ({"TeamID": ..., "Offense": [...], "Defense": [...]}) with zero game
-- reference anywhere -- the original shape was a mismatch never exercised
-- by any code (confirmed zero writers, zero rows, before this migration).
-- Corrected here to team_id-keyed, the smallest shape matching the actual
-- provider payload. A future "depth chart as of game X" need should be
-- derived from the latest team snapshot at/before that game's kickoff, not
-- a second, competing game-keyed history table (Mac's explicit instruction).
--
-- Unlike roster_memberships, this table keeps the original odds_snapshots/
-- injury_reports/weather_snapshots convention: one snapshot per capture,
-- written unconditionally (no latest-row/insert-on-change comparison) --
-- it already carried the append-only trigger under the old shape, so this
-- recreation preserves the same "strict append-only, every poll writes a
-- new row" philosophy those three sibling tables use, not team_stats/
-- player_stats' different insert-on-change one.
--
-- Safe to drop and recreate rather than ALTER: confirmed zero rows and
-- zero writers anywhere in the codebase before this migration (no code
-- ever wrote to the old game_id-keyed shape).

drop trigger if exists trg_block_depth_chart_snapshots_update on depth_chart_snapshots;
drop table if exists depth_chart_snapshots;

create table depth_chart_snapshots (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references teams(id) on delete cascade,
  depth_chart_data jsonb not null,
  captured_at timestamptz not null default now()
);
create index idx_depth_chart_snapshots_team_time on depth_chart_snapshots(team_id, captured_at desc);

alter table depth_chart_snapshots enable row level security;
create policy "public_read" on depth_chart_snapshots for select using (true);

create trigger trg_block_depth_chart_snapshots_update
  before update on depth_chart_snapshots
  for each row execute function block_snapshot_updates();
