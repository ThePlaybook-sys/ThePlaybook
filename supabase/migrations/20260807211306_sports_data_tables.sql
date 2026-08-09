-- Phase 1, Milestone 2: sports data tables (Volume 3 §4, including §4.0-§4.2 v3.0/v4.0 additions)
-- Normalized multi-sport core, games, append-only market/context snapshots,
-- daily_game_intelligence working table, and the 13 derived intelligence score tables.
--
-- RLS: per the 2026-08-07 clarification added to Volume 3 §10, every table below gets RLS
-- enabled with a permissive public-read policy (none of this data is user-specific, but the
-- frontend reads some of it directly via Supabase Realtime, not only through the API Gateway).
-- Writes are service-role-only — no insert/update/delete policy is granted to anon/authenticated.
--
-- Append-only enforcement: odds_snapshots, injury_reports, weather_snapshots,
-- depth_chart_snapshots, and referee_assignments are all described in §4 as "append-only by
-- design." §11 only specifies a DB-level trigger for recommendation_agent_outputs (§5,
-- Milestone 3), but per Mac's 2026-08-07 decision the same enforcement is extended to these
-- five tables now, for the same reason that trigger exists in the first place.

-- ============================================================================
-- 4.0 Normalized Multi-Sport Core
-- ============================================================================

create table sports (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null
);

create table leagues (
  id uuid primary key default gen_random_uuid(),
  sport_id uuid not null references sports(id),
  code text not null,
  name text not null
);

create table seasons (
  id uuid primary key default gen_random_uuid(),
  league_id uuid not null references leagues(id),
  year integer not null,
  start_date date,
  end_date date
);

create table teams (
  id uuid primary key default gen_random_uuid(),
  league_id uuid not null references leagues(id),
  name text not null,
  external_provider_id text
);

create table players (
  id uuid primary key default gen_random_uuid(),
  team_id uuid references teams(id),
  name text not null,
  position text,
  external_provider_id text
);

-- ============================================================================
-- games (v4.0 — backward-compatible transition; legacy `sport` kept alongside `sport_id`)
-- ============================================================================

create table games (
  id uuid primary key default gen_random_uuid(),
  external_provider_id text not null,
  sport_id uuid references sports(id),
  league_id uuid references leagues(id),
  season_id uuid references seasons(id),
  sport text not null default 'nfl',
  home_team text not null,
  away_team text not null,
  scheduled_start timestamptz not null,
  stadium text,
  status text check (status in ('scheduled','live','final','postponed','canceled')),
  final_score jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index idx_games_scheduled on games(scheduled_start);
create index idx_games_status on games(status) where status in ('scheduled','live');
create index idx_games_sport on games(sport_id);

create trigger trg_games_updated
  before update on games
  for each row execute function set_updated_at();

create table player_stats (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references players(id),
  game_id uuid not null references games(id),
  stats jsonb not null,
  created_at timestamptz default now()
);

create table team_stats (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references teams(id),
  game_id uuid not null references games(id),
  stats jsonb not null,
  created_at timestamptz default now()
);

-- Sport-specific extension pattern (NFL only at launch)
create table player_stats_nfl (
  player_stat_id uuid primary key references player_stats(id) on delete cascade,
  passing_yards integer,
  receiving_yards integer,
  rushing_yards integer,
  interceptions integer,
  sacks integer
);

-- ============================================================================
-- Append-only market/context snapshot tables
-- ============================================================================

create table odds_snapshots (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  sportsbook text not null,
  market_type text not null,
  line_data jsonb not null,
  captured_at timestamptz not null default now()
);
create index idx_odds_game_time on odds_snapshots(game_id, captured_at desc);

-- injury_reports, weather_snapshots, depth_chart_snapshots, referee_assignments: §4 specifies
-- these mirror odds_snapshots' shape (keyed to game_id, with captured_at) without naming exact
-- payload columns. Following odds_snapshots' own pattern (a single normalized jsonb payload
-- from the provider adapter) rather than inventing sport-specific columns here.
create table injury_reports (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  report_data jsonb not null,
  captured_at timestamptz not null default now()
);
create index idx_injury_reports_game_time on injury_reports(game_id, captured_at desc);

create table weather_snapshots (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  weather_data jsonb not null,
  captured_at timestamptz not null default now()
);
create index idx_weather_snapshots_game_time on weather_snapshots(game_id, captured_at desc);

create table depth_chart_snapshots (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  depth_chart_data jsonb not null,
  captured_at timestamptz not null default now()
);
create index idx_depth_chart_snapshots_game_time on depth_chart_snapshots(game_id, captured_at desc);

create table referee_assignments (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  assignment_data jsonb not null,
  captured_at timestamptz not null default now()
);
create index idx_referee_assignments_game_time on referee_assignments(game_id, captured_at desc);

create or replace function block_snapshot_updates()
returns trigger as $$
begin
  raise exception '% is append-only and cannot be modified', TG_TABLE_NAME;
end;
$$ language plpgsql;

create trigger trg_block_odds_snapshots_update
  before update on odds_snapshots
  for each row execute function block_snapshot_updates();
create trigger trg_block_injury_reports_update
  before update on injury_reports
  for each row execute function block_snapshot_updates();
create trigger trg_block_weather_snapshots_update
  before update on weather_snapshots
  for each row execute function block_snapshot_updates();
create trigger trg_block_depth_chart_snapshots_update
  before update on depth_chart_snapshots
  for each row execute function block_snapshot_updates();
create trigger trg_block_referee_assignments_update
  before update on referee_assignments
  for each row execute function block_snapshot_updates();

-- ============================================================================
-- 4.1 daily_game_intelligence — master working table (v3.0)
-- No append-only / soft-delete treatment: continuously overwritten by the Master Refresh
-- worker, not a source of historical truth (recommendation_snapshots owns that, §5).
-- ============================================================================

create table daily_game_intelligence (
  game_id uuid primary key references games(id) on delete cascade,
  teams jsonb,
  players jsonb,
  odds jsonb,
  props jsonb,
  weather jsonb,
  injuries jsonb,
  news jsonb,
  travel jsonb,
  rest jsonb,
  stadium jsonb,
  public_betting jsonb,
  sharp_money jsonb,
  ai_scores jsonb,
  momentum jsonb,
  matchup_ratings jsonb,
  ev_calculations jsonb,
  confidence_scores jsonb,
  recommendation_candidates jsonb,
  last_updated timestamptz default now()
);

-- ============================================================================
-- 4.2 Derived Intelligence Score Tables (v3.0)
-- ============================================================================

create table weather_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table injury_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table travel_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table rest_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table momentum_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table matchup_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table line_value_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table sharp_money_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table schedule_difficulty_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table offensive_matchup_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table defensive_matchup_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table coaching_edge_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
create table public_sentiment_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);

-- ============================================================================
-- Row Level Security — public read, service-role-only writes (Volume 3 §10, 2026-08-07 note)
-- ============================================================================

alter table sports enable row level security;
create policy "public_read" on sports for select using (true);

alter table leagues enable row level security;
create policy "public_read" on leagues for select using (true);

alter table seasons enable row level security;
create policy "public_read" on seasons for select using (true);

alter table teams enable row level security;
create policy "public_read" on teams for select using (true);

alter table players enable row level security;
create policy "public_read" on players for select using (true);

alter table games enable row level security;
create policy "public_read" on games for select using (true);

alter table player_stats enable row level security;
create policy "public_read" on player_stats for select using (true);

alter table team_stats enable row level security;
create policy "public_read" on team_stats for select using (true);

alter table player_stats_nfl enable row level security;
create policy "public_read" on player_stats_nfl for select using (true);

alter table odds_snapshots enable row level security;
create policy "public_read" on odds_snapshots for select using (true);

alter table injury_reports enable row level security;
create policy "public_read" on injury_reports for select using (true);

alter table weather_snapshots enable row level security;
create policy "public_read" on weather_snapshots for select using (true);

alter table depth_chart_snapshots enable row level security;
create policy "public_read" on depth_chart_snapshots for select using (true);

alter table referee_assignments enable row level security;
create policy "public_read" on referee_assignments for select using (true);

alter table daily_game_intelligence enable row level security;
create policy "public_read" on daily_game_intelligence for select using (true);

alter table weather_scores enable row level security;
create policy "public_read" on weather_scores for select using (true);

alter table injury_scores enable row level security;
create policy "public_read" on injury_scores for select using (true);

alter table travel_scores enable row level security;
create policy "public_read" on travel_scores for select using (true);

alter table rest_scores enable row level security;
create policy "public_read" on rest_scores for select using (true);

alter table momentum_scores enable row level security;
create policy "public_read" on momentum_scores for select using (true);

alter table matchup_scores enable row level security;
create policy "public_read" on matchup_scores for select using (true);

alter table line_value_scores enable row level security;
create policy "public_read" on line_value_scores for select using (true);

alter table sharp_money_scores enable row level security;
create policy "public_read" on sharp_money_scores for select using (true);

alter table schedule_difficulty_scores enable row level security;
create policy "public_read" on schedule_difficulty_scores for select using (true);

alter table offensive_matchup_scores enable row level security;
create policy "public_read" on offensive_matchup_scores for select using (true);

alter table defensive_matchup_scores enable row level security;
create policy "public_read" on defensive_matchup_scores for select using (true);

alter table coaching_edge_scores enable row level security;
create policy "public_read" on coaching_edge_scores for select using (true);

alter table public_sentiment_scores enable row level security;
create policy "public_read" on public_sentiment_scores for select using (true);
