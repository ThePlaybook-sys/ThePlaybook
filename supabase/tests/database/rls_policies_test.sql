-- Phase 1 Testing Requirement: "Automated RLS test suite: for every table with a policy,
-- a test that confirms both the 'owner can access' and 'non-owner cannot access' cases."
-- Run via `supabase test db` (pgTAP), or manually inside a transaction that's rolled back.
--
-- Coverage: 7 user-owned tables (owner/non-owner, 2 assertions each), recommendations'
-- tier-gated + soft-delete policy (3 assertions), 30 public-read tables (1 assertion each),
-- 14 default-deny tables (1 assertion each). 14 + 3 + 30 + 14 = 61 assertions total.
--
-- All results are collected into a temp table (test_results) rather than left as bare
-- top-level SELECTs, so a single client round-trip can inspect every assertion's outcome.

begin;
create extension if not exists pgtap with schema extensions;
create temp table test_results (id serial primary key, result text);
select plan(61);

-- ============================================================================
-- Fixture data (inserted as the elevated role, which bypasses RLS)
-- ============================================================================

insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data)
values
  ('00000000-0000-0000-0000-000000000000', 'a0000000-0000-0000-0000-00000000000a', 'authenticated', 'authenticated', 'rlstest-a@example.com', crypt('password', gen_salt('bf')), now(), now(), now(), '{}', '{}'),
  ('00000000-0000-0000-0000-000000000000', 'b0000000-0000-0000-0000-00000000000b', 'authenticated', 'authenticated', 'rlstest-b@example.com', crypt('password', gen_salt('bf')), now(), now(), now(), '{}', '{}');

insert into user_profiles (id, jurisdiction_state) values
  ('a0000000-0000-0000-0000-00000000000a', 'NJ'),
  ('b0000000-0000-0000-0000-00000000000b', 'NY');
insert into subscriptions (user_id, tier, status) values
  ('a0000000-0000-0000-0000-00000000000a', 'free', 'active'),
  ('b0000000-0000-0000-0000-00000000000b', 'free', 'active');
insert into betting_dna (user_id) values
  ('a0000000-0000-0000-0000-00000000000a'),
  ('b0000000-0000-0000-0000-00000000000b');

insert into sports (id, code, name) values ('c0000000-0000-0000-0000-000000000001', 'nfl', 'NFL');
insert into leagues (id, sport_id, code, name) values ('c0000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000001', 'nfl', 'NFL');
insert into seasons (id, league_id, year) values ('c0000000-0000-0000-0000-000000000003', 'c0000000-0000-0000-0000-000000000002', 2026);
insert into teams (id, league_id, name) values ('c0000000-0000-0000-0000-000000000004', 'c0000000-0000-0000-0000-000000000002', 'Test Team');
insert into players (id, team_id, name) values ('c0000000-0000-0000-0000-000000000005', 'c0000000-0000-0000-0000-000000000004', 'Test Player');
insert into games (id, external_provider_id, sport_id, league_id, season_id, sport, home_team, away_team, scheduled_start, status)
values ('c0000000-0000-0000-0000-000000000006', 'rlstest-game', 'c0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000003', 'nfl', 'Home', 'Away', now() + interval '1 day', 'scheduled');
insert into game_provider_ids (game_id, provider_name, provider_game_id) values ('c0000000-0000-0000-0000-000000000006', 'the_odds_api', 'rlstest-game');
insert into player_stats (id, player_id, game_id, stats) values ('c0000000-0000-0000-0000-000000000007', 'c0000000-0000-0000-0000-000000000005', 'c0000000-0000-0000-0000-000000000006', '{}');
insert into team_stats (id, team_id, game_id, stats) values ('c0000000-0000-0000-0000-000000000008', 'c0000000-0000-0000-0000-000000000004', 'c0000000-0000-0000-0000-000000000006', '{}');
insert into player_stats_nfl (player_stat_id) values ('c0000000-0000-0000-0000-000000000007');
insert into odds_snapshots (game_id, sportsbook, market_type, line_data) values ('c0000000-0000-0000-0000-000000000006', 'TestBook', 'moneyline', '{}');
insert into injury_reports (game_id, report_data) values ('c0000000-0000-0000-0000-000000000006', '{}');
insert into weather_snapshots (game_id, weather_data) values ('c0000000-0000-0000-0000-000000000006', '{}');
insert into depth_chart_snapshots (game_id, depth_chart_data) values ('c0000000-0000-0000-0000-000000000006', '{}');
insert into referee_assignments (game_id, assignment_data) values ('c0000000-0000-0000-0000-000000000006', '{}');
insert into daily_game_intelligence (game_id) values ('c0000000-0000-0000-0000-000000000006');
insert into weather_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into injury_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into travel_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into rest_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into momentum_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into matchup_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into line_value_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into sharp_money_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into schedule_difficulty_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into offensive_matchup_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into defensive_matchup_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into coaching_edge_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);
insert into public_sentiment_scores (game_id, score) values ('c0000000-0000-0000-0000-000000000006', 0.5);

insert into recommendations (id, game_id, min_required_tier, status, deleted_at) values
  ('c0000000-0000-0000-0000-00000000000f', 'c0000000-0000-0000-0000-000000000006', 'free', 'active', null),
  ('c0000000-0000-0000-0000-000000000010', 'c0000000-0000-0000-0000-000000000006', 'elite', 'active', null),
  ('c0000000-0000-0000-0000-000000000011', 'c0000000-0000-0000-0000-000000000006', 'free', 'active', now());

insert into agents (id, name) values ('c0000000-0000-0000-0000-000000000012', 'rlstest_agent');
insert into agent_performance_scores (agent_id, evaluation_window_start, evaluation_window_end, sample_size) values ('c0000000-0000-0000-0000-000000000012', '2026-01-01', '2026-01-07', 10);
insert into recommendation_agent_outputs (recommendation_id, agent_id, raw_output, weight_applied) values ('c0000000-0000-0000-0000-00000000000f', 'c0000000-0000-0000-0000-000000000012', '{}', 1.0);
insert into consensus_snapshots (recommendation_id, aggregate_confidence) values ('c0000000-0000-0000-0000-00000000000f', 0.7);
insert into explainability_payloads (recommendation_id) values ('c0000000-0000-0000-0000-00000000000f');
insert into recommendation_snapshots (recommendation_id, full_environment_snapshot, agent_outputs_snapshot, consensus_snapshot) values ('c0000000-0000-0000-0000-00000000000f', '{}', '{}', '{}');

insert into bet_slips (id, user_id, linked_recommendation_id) values
  ('c0000000-0000-0000-0000-000000000013', 'a0000000-0000-0000-0000-00000000000a', 'c0000000-0000-0000-0000-00000000000f'),
  ('c0000000-0000-0000-0000-000000000014', 'b0000000-0000-0000-0000-00000000000b', 'c0000000-0000-0000-0000-00000000000f');
insert into verified_bets (id, user_id, bet_slip_id, recommendation_id, outcome) values
  ('c0000000-0000-0000-0000-000000000015', 'a0000000-0000-0000-0000-00000000000a', 'c0000000-0000-0000-0000-000000000013', 'c0000000-0000-0000-0000-00000000000f', 'pending'),
  ('c0000000-0000-0000-0000-000000000016', 'b0000000-0000-0000-0000-00000000000b', 'c0000000-0000-0000-0000-000000000014', 'c0000000-0000-0000-0000-00000000000f', 'pending');
insert into projected_user_performance (user_id, recommendation_id, projected_units) values
  ('a0000000-0000-0000-0000-00000000000a', 'c0000000-0000-0000-0000-00000000000f', 1.0),
  ('b0000000-0000-0000-0000-00000000000b', 'c0000000-0000-0000-0000-00000000000f', 1.0);
insert into verified_user_performance (user_id, verified_bet_id, actual_units) values
  ('a0000000-0000-0000-0000-00000000000a', 'c0000000-0000-0000-0000-000000000015', 1.0),
  ('b0000000-0000-0000-0000-00000000000b', 'c0000000-0000-0000-0000-000000000016', 1.0);

insert into ai_performance (evaluation_window_start, evaluation_window_end, sport) values ('2026-01-01', '2026-01-07', 'nfl');
insert into postgame_reviews (recommendation_id, outcome_summary) values ('c0000000-0000-0000-0000-00000000000f', 'test');
insert into market_monitoring_events (game_id, event_type, action_taken) values ('c0000000-0000-0000-0000-000000000006', 'line_movement', 'none');
insert into model_routing_rules (task_type, primary_model) values ('rlstest_task', 'test-model');
insert into prompt_registry (prompt_name, version, prompt_text, status) values ('rlstest_prompt', 1, 'hello', 'active');
insert into model_registry (model_name, status) values ('rlstest-model', 'active');
insert into feature_flags (flag_key) values ('rlstest_flag');
insert into recommendation_costs (recommendation_id, provider, cost_usd) values ('c0000000-0000-0000-0000-00000000000f', 'anthropic', 0.01);
insert into audit_log (actor, action_type, target_id) values ('system', 'admin_action', 'c0000000-0000-0000-0000-00000000000f');

-- ============================================================================
-- Main test run. A single DO block, not standalone functions called from
-- INSERT...SELECT: an earlier version of this suite split role-switch/reset
-- across separate top-level statements for the recommendations checks, which
-- failed with "permission denied for table test_results" the moment an
-- insert ran while still under the unprivileged `authenticated` role.
-- Every set local role here is paired with its own reset role before the
-- corresponding insert into test_results — caught and fixed while first
-- writing this suite, kept as one disciplined pattern throughout.
-- ============================================================================

do $do$
declare
  cnt integer;
  tbl text;
  visible boolean;
  owned_tables text[][] := array[
    array['user_profiles','id'], array['subscriptions','user_id'], array['betting_dna','user_id'],
    array['bet_slips','user_id'], array['verified_bets','user_id'],
    array['projected_user_performance','user_id'], array['verified_user_performance','user_id']
  ];
  row_pair text[];
  public_tables text[] := array[
    'sports','leagues','seasons','teams','players','games','game_provider_ids','player_stats','team_stats',
    'player_stats_nfl','odds_snapshots','injury_reports','weather_snapshots','depth_chart_snapshots',
    'referee_assignments','daily_game_intelligence','weather_scores','injury_scores','travel_scores',
    'rest_scores','momentum_scores','matchup_scores','line_value_scores','sharp_money_scores',
    'schedule_difficulty_scores','offensive_matchup_scores','defensive_matchup_scores',
    'coaching_edge_scores','public_sentiment_scores','feature_flags'
  ];
  deny_tables text[] := array[
    'agents','agent_performance_scores','recommendation_agent_outputs','consensus_snapshots',
    'explainability_payloads','recommendation_snapshots','ai_performance','postgame_reviews',
    'market_monitoring_events','model_routing_rules','prompt_registry','model_registry',
    'recommendation_costs','audit_log'
  ];
  res text; res1 text; res2 text; res3 text;
begin
  -- 7 user-owned tables x 2 (owner sees / non-owner doesn't) = 14
  foreach row_pair slice 1 in array owned_tables loop
    tbl := row_pair[1];
    perform set_config('request.jwt.claims', json_build_object('sub','a0000000-0000-0000-0000-00000000000a','role','authenticated')::text, true);
    set local role authenticated;
    execute format('select count(*) from %I where %I = %L', tbl, row_pair[2], 'a0000000-0000-0000-0000-00000000000a') into cnt;
    reset role;
    res := ok(cnt = 1, tbl || ': owner can see own row');
    insert into test_results(result) values (res);

    perform set_config('request.jwt.claims', json_build_object('sub','b0000000-0000-0000-0000-00000000000b','role','authenticated')::text, true);
    set local role authenticated;
    execute format('select count(*) from %I where %I = %L', tbl, row_pair[2], 'a0000000-0000-0000-0000-00000000000a') into cnt;
    reset role;
    res := ok(cnt = 0, tbl || ': non-owner cannot see others'' row');
    insert into test_results(result) values (res);
  end loop;

  -- recommendations: tier-gated + soft-delete (3 assertions)
  perform set_config('request.jwt.claims', json_build_object('sub','a0000000-0000-0000-0000-00000000000a','role','authenticated')::text, true);
  set local role authenticated;
  execute 'select count(*) from recommendations where id = $1' into cnt using 'c0000000-0000-0000-0000-00000000000f'::uuid;
  res1 := ok(cnt = 1, 'recommendations: free-tier row visible to free-tier user');
  execute 'select count(*) from recommendations where id = $1' into cnt using 'c0000000-0000-0000-0000-000000000010'::uuid;
  res2 := ok(cnt = 0, 'recommendations: elite-tier row hidden from free-tier user');
  execute 'select count(*) from recommendations where id = $1' into cnt using 'c0000000-0000-0000-0000-000000000011'::uuid;
  res3 := ok(cnt = 0, 'recommendations: soft-deleted row hidden even when tier matches');
  reset role;
  insert into test_results(result) values (res1);
  insert into test_results(result) values (res2);
  insert into test_results(result) values (res3);

  -- 29 public-read tables (1 assertion each)
  foreach tbl in array public_tables loop
    set local role anon;
    execute format('select count(*) > 0 from %I', tbl) into visible;
    reset role;
    res := ok(visible, tbl || ': publicly readable (anon)');
    insert into test_results(result) values (res);
  end loop;

  -- 14 default-deny tables (1 assertion each)
  foreach tbl in array deny_tables loop
    perform set_config('request.jwt.claims', json_build_object('sub','a0000000-0000-0000-0000-00000000000a','role','authenticated')::text, true);
    set local role authenticated;
    execute format('select count(*) from %I', tbl) into cnt;
    reset role;
    res := ok(cnt = 0, tbl || ': default-deny holds for authenticated role');
    insert into test_results(result) values (res);
  end loop;
end $do$;

select count(*) as total_tests,
  count(*) filter (where result like 'ok %') as passed,
  count(*) filter (where result like 'not ok%') as failed,
  string_agg(result, E'\n') filter (where result like 'not ok%') as failures
from test_results;

select * from finish();
rollback;
