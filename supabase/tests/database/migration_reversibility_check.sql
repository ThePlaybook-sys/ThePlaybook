-- Phase 1 Testing Requirement: "Migration reversibility check on at least the additive
-- migrations (Volume 3 §12's backward-compatible preference)."
--
-- All five Phase 1 migrations are purely additive (new tables, functions, triggers, one
-- ALTER COLUMN ... SET DEFAULT) — no column removals or type changes, so §12's two-step
-- breaking-change process doesn't apply. This script is the DOWN side for each migration,
-- run in reverse order, each block undoing exactly what its matching UP migration added.
--
-- Verified 2026-08-07 on a disposable Supabase branch (not dev): applying all five UP
-- migrations (via branch creation, which replays every migration from empty) then running
-- every DOWN block below in reverse order landed at exactly 0 tables — table counts checked
-- after each step matched the prior migration's end state precisely (38 -> 31 -> 31 -> 3 -> 0).
-- Supabase CLI migrations are forward-only by convention (no paired up/down files), so this
-- script is a verification artifact, not part of the normal apply path — never run against
-- dev/staging/production directly.
--
-- 2026-08-13 addition (3E-1): 20260813180000_game_provider_ids_and_season_week is purely
-- additive (one new table, two new nullable columns, two column comments) -- no column
-- removal or type change, so it follows the same additive-migration convention as the five
-- Phase 1 migrations below. Its DOWN block is prepended since it's the most recently applied.
-- 20260813180500_games_external_provider_id_nullable is a constraint relaxation (NOT NULL ->
-- nullable); its DOWN would re-add NOT NULL, which is only safe if no row has a null value --
-- true immediately after this migration (no code writes null there yet), not guaranteed once
-- Schedule ingestion has actually run, so this DOWN block is documented but not silently
-- assumed always-safe to run.
-- 2026-08-13 addition (3E-3): 20260813210000_team_provider_ids and its backfill companion
-- are purely additive (one new table, one column comment, backfill rows) -- same convention.
-- Both DOWN blocks are prepended since they're the most recently applied.
-- 2026-08-14 addition (3E-4A): 20260814050000_expand_nfl_teams_and_provider_ids is purely
-- additive (26 new teams rows, 9 new team_provider_ids rows) -- no new tables or columns, same
-- convention. Its DOWN block is prepended since it's the most recently applied. Deleting by
-- team name (rather than id) matches how the UP migration itself identified rows, and is safe
-- here since no other migration or seed data reuses these 26 team names.

-- ============================================================================
-- DOWN: 20260814050000_expand_nfl_teams_and_provider_ids
-- ============================================================================
delete from team_provider_ids where provider_name = 'sportsdataio' and provider_team_id in
  ('ARI', 'ATL', 'CAR', 'CHI', 'LAR', 'NE', 'NO', 'SEA', 'TB');
delete from teams where name in (
  'Arizona Cardinals', 'Atlanta Falcons', 'Carolina Panthers', 'Chicago Bears',
  'Cincinnati Bengals', 'Cleveland Browns', 'Denver Broncos', 'Detroit Lions',
  'Green Bay Packers', 'Houston Texans', 'Indianapolis Colts', 'Jacksonville Jaguars',
  'Las Vegas Raiders', 'Los Angeles Chargers', 'Los Angeles Rams', 'Miami Dolphins',
  'Minnesota Vikings', 'New England Patriots', 'New Orleans Saints', 'New York Giants',
  'New York Jets', 'Pittsburgh Steelers', 'Seattle Seahawks', 'Tampa Bay Buccaneers',
  'Tennessee Titans', 'Washington Commanders'
);
-- expected table count after this block: 40 (no table count change, data only -- will FAIL if
-- any of these 26 teams has since acquired a games/players/team_provider_ids foreign-key
-- reference from other providers' data, same caveat as any other data-only DOWN block here)

-- ============================================================================
-- DOWN: 20260813210500_team_provider_ids_backfill
-- ============================================================================
delete from team_provider_ids where provider_name in ('the_odds_api', 'sportsdataio');
-- expected table count after this block: 40 (no table count change, data only)

-- ============================================================================
-- DOWN: 20260813210000_team_provider_ids
-- ============================================================================
drop table if exists team_provider_ids;
-- expected table count after this block: 39 (back to the pre-3E-3 table count)

-- ============================================================================
-- DOWN: 20260813180500_games_external_provider_id_nullable
-- ============================================================================
alter table games alter column external_provider_id set not null;
-- expected table count after this block: 39 (no table count change, constraint only --
-- will FAIL if any games row has a null external_provider_id at the time this runs)

-- ============================================================================
-- DOWN: 20260813180000_game_provider_ids_and_season_week
-- ============================================================================
alter table games drop column if exists week;
alter table games drop column if exists season_type;
drop table if exists game_provider_ids;
-- expected table count after this block: 38 (back to the pre-3E-1 table count)

-- ============================================================================
-- DOWN: 20260807220949_performance_postgame_config_tables
-- ============================================================================
drop trigger if exists trg_prompt_registry_audit on prompt_registry;
drop trigger if exists trg_agents_audit on agents;
drop trigger if exists trg_model_routing_rules_audit on model_routing_rules;
drop trigger if exists trg_feature_flags_audit on feature_flags;
drop trigger if exists trg_model_routing_rules_updated on model_routing_rules;
drop trigger if exists trg_prompt_registry_updated on prompt_registry;
drop trigger if exists trg_model_registry_updated on model_registry;
drop trigger if exists trg_feature_flags_updated on feature_flags;
drop function if exists log_config_change();

drop table if exists audit_log;
drop table if exists recommendation_costs;
drop table if exists feature_flags;
drop table if exists model_registry;
drop table if exists prompt_registry;
drop table if exists model_routing_rules;
drop table if exists market_monitoring_events;
drop table if exists postgame_reviews;
drop table if exists verified_user_performance;
drop table if exists projected_user_performance;
drop table if exists ai_performance;
drop table if exists verified_bets;
drop table if exists bet_slips;
-- expected table count after this block: 38

-- ============================================================================
-- DOWN: 20260807213358_ai_intelligence_tables
-- ============================================================================
drop trigger if exists trg_block_rao_update on recommendation_agent_outputs;
drop function if exists block_agent_output_updates();

drop table if exists recommendation_snapshots;
drop table if exists explainability_payloads;
drop table if exists consensus_snapshots;
drop table if exists recommendation_agent_outputs;
drop table if exists recommendations;
drop table if exists agent_performance_scores;
drop table if exists agents;
-- expected table count after this block: 31

-- ============================================================================
-- DOWN: 20260807213233_uuidv7_function_and_odds_snapshots_fix
-- Safe only once migrations 4 and 5 (above) are already reversed, since both
-- depend on uuid_generate_v7() too — reverse order matters here.
-- ============================================================================
alter table odds_snapshots alter column id set default gen_random_uuid();
drop function if exists uuid_generate_v7();
-- expected table count after this block: 31 (no table count change, function + default only)

-- ============================================================================
-- DOWN: 20260807211421_sports_data_tables
-- ============================================================================
drop trigger if exists trg_block_referee_assignments_update on referee_assignments;
drop trigger if exists trg_block_depth_chart_snapshots_update on depth_chart_snapshots;
drop trigger if exists trg_block_weather_snapshots_update on weather_snapshots;
drop trigger if exists trg_block_injury_reports_update on injury_reports;
drop trigger if exists trg_block_odds_snapshots_update on odds_snapshots;
drop trigger if exists trg_games_updated on games;
drop function if exists block_snapshot_updates();

drop table if exists public_sentiment_scores;
drop table if exists coaching_edge_scores;
drop table if exists defensive_matchup_scores;
drop table if exists offensive_matchup_scores;
drop table if exists schedule_difficulty_scores;
drop table if exists sharp_money_scores;
drop table if exists line_value_scores;
drop table if exists matchup_scores;
drop table if exists momentum_scores;
drop table if exists rest_scores;
drop table if exists travel_scores;
drop table if exists injury_scores;
drop table if exists weather_scores;
drop table if exists daily_game_intelligence;
drop table if exists referee_assignments;
drop table if exists depth_chart_snapshots;
drop table if exists weather_snapshots;
drop table if exists injury_reports;
drop table if exists odds_snapshots;
drop table if exists player_stats_nfl;
drop table if exists team_stats;
drop table if exists player_stats;
drop table if exists games;
drop table if exists players;
drop table if exists teams;
drop table if exists seasons;
drop table if exists leagues;
drop table if exists sports;
-- expected table count after this block: 3

-- ============================================================================
-- DOWN: 20260807210017_core_user_account_tables
-- ============================================================================
drop trigger if exists trg_subscriptions_updated on subscriptions;
drop trigger if exists trg_user_profiles_updated on user_profiles;
drop function if exists set_updated_at();

drop table if exists betting_dna;
drop table if exists subscriptions;
drop table if exists user_profiles;
-- expected table count after this block: 0
