-- Pre-9/9 Data Preservation Readiness: game_events (Volume 3 §4.3 addition)
--
-- HQ-authorized minimum pre-season implementation, following the same
-- architecture-reservation-then-build pattern this project already uses
-- (Volume 4 §8.5/§8.6). `raw_payload jsonb not null` is the actual
-- preservation mechanism -- every typed column below is a best-effort
-- normalization that is expected to be null until validated against a
-- real MySportsFeeds (or any other provider's) live-game payload, per
-- the 2026-09-09/10 opener validation gate
-- (docs/ops/nfl-provider-decision-record.md). No MySportsFeeds-specific
-- field name is assumed anywhere in this migration.
--
-- Append-only from creation, reusing block_snapshot_updates() verbatim --
-- the same function odds_snapshots/injury_reports/weather_snapshots/
-- depth_chart_snapshots/referee_assignments/roster_memberships already
-- use. No uniqueness constraint on provider_event_id: deliberately
-- deferred until a real payload confirms one exists and is stable
-- (Volume 3 §4.3's own explicit reasoning) -- a premature constraint here
-- risks either rejecting legitimate re-captures or silently deduplicating
-- genuinely distinct events.

create table game_events (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  provider_name text not null,
  provider_event_id text,
  sequence_number integer,
  period text,
  clock text,
  event_type text,
  description text,
  score_home integer,
  score_away integer,
  involved_team_id uuid references teams(id),
  involved_player_ids jsonb,
  raw_payload jsonb not null,
  captured_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index idx_game_events_game_seq on game_events(game_id, sequence_number);
create index idx_game_events_game_time on game_events(game_id, captured_at desc);

alter table game_events enable row level security;
create policy "public_read" on game_events for select using (true);

create trigger trg_block_game_events_update
  before update on game_events
  for each row execute function block_snapshot_updates();
