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
