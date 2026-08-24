-- Phase 1 Testing Requirement: "Seed script producing realistic fake data for every table,
-- needed for Phase 3-5 development without depending on live provider data yet."
--
-- Applied via `supabase db reset` locally, or run directly against an empty dev database.
-- Never run against staging/production. All emails/names are obviously-fake fixture data.
--
-- ID scheme: literal UUIDs grouped by entity type via a distinct leading byte (a1 = users,
-- a2 = sports/league/season, a3 = teams, a4 = players, a5 = games, a6 = player_stats,
-- a7 = team_stats, a8 = agents, a9 = recommendations, aa = bet_slips, ab = verified_bets).

-- ============================================================================
-- Users, profiles, subscriptions, betting DNA
-- ============================================================================

insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data)
values
  ('00000000-0000-0000-0000-000000000000', 'a1000000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'seed-free-user@example.com', crypt('seedpassword', gen_salt('bf')), now(), now(), now(), '{}', '{}'),
  ('00000000-0000-0000-0000-000000000000', 'a1000000-0000-0000-0000-000000000002', 'authenticated', 'authenticated', 'seed-elite-user@example.com', crypt('seedpassword', gen_salt('bf')), now(), now(), now(), '{}', '{}');

insert into user_profiles (id, display_name, jurisdiction_state, persona_classification, betting_experience, primary_goal, risk_tolerance, preferred_unit_size, max_parlay_legs, onboarding_completed_at) values
  ('a1000000-0000-0000-0000-000000000001', 'Seed Free User', 'NJ', 'casual', 'new', 'fun', 'conservative', 25.00, 0, now() - interval '10 days'),
  ('a1000000-0000-0000-0000-000000000002', 'Seed Elite User', 'PA', 'grinder', 'experienced', 'disciplined_longterm', 'aggressive', 100.00, 4, now() - interval '30 days');

insert into subscriptions (user_id, tier, status, billing_period, current_period_start, current_period_end) values
  ('a1000000-0000-0000-0000-000000000001', 'free', 'active', null, null, null),
  ('a1000000-0000-0000-0000-000000000002', 'elite', 'active', 'monthly', now() - interval '5 days', now() + interval '25 days');

insert into betting_dna (user_id, favorite_sportsbooks, observed_bet_types, observed_avg_odds, observed_risk_tendency, observed_frequency, favorite_sports) values
  ('a1000000-0000-0000-0000-000000000001', array['DraftKings'], array['single'], -115.00, 'conservative', 'game-day-only', array['nfl']),
  ('a1000000-0000-0000-0000-000000000002', array['FanDuel','Caesars'], array['single','same_game_parlay'], -108.00, 'aggressive', 'weekly', array['nfl']);

-- ============================================================================
-- Normalized multi-sport core (NFL only, matching Volume 1's narrow-launch scope)
-- ============================================================================

insert into sports (id, code, name) values ('a2000000-0000-0000-0000-000000000001', 'nfl', 'National Football League');
insert into leagues (id, sport_id, code, name) values ('a2000000-0000-0000-0000-000000000002', 'a2000000-0000-0000-0000-000000000001', 'nfl', 'NFL');
insert into seasons (id, league_id, year, start_date, end_date) values ('a2000000-0000-0000-0000-000000000003', 'a2000000-0000-0000-0000-000000000002', 2026, '2026-09-04', '2027-02-14');

insert into teams (id, league_id, name, external_provider_id) values
  ('a3000000-0000-0000-0000-000000000001', 'a2000000-0000-0000-0000-000000000002', 'Kansas City Chiefs', 'seed-kc'),
  ('a3000000-0000-0000-0000-000000000002', 'a2000000-0000-0000-0000-000000000002', 'Buffalo Bills', 'seed-buf'),
  ('a3000000-0000-0000-0000-000000000003', 'a2000000-0000-0000-0000-000000000002', 'San Francisco 49ers', 'seed-sf'),
  ('a3000000-0000-0000-0000-000000000004', 'a2000000-0000-0000-0000-000000000002', 'Philadelphia Eagles', 'seed-phi'),
  ('a3000000-0000-0000-0000-000000000005', 'a2000000-0000-0000-0000-000000000002', 'Dallas Cowboys', 'seed-dal'),
  ('a3000000-0000-0000-0000-000000000006', 'a2000000-0000-0000-0000-000000000002', 'Baltimore Ravens', 'seed-bal');

-- Phase 3E-4A: remaining 26 current NFL teams, mirroring the
-- 20260814050000_expand_nfl_teams_and_provider_ids.sql migration's expansion
-- of `teams` to the full 32-team league so a fresh `supabase db reset` lands
-- in the same state as dev's migrated data. `external_provider_id` is left
-- null here (as the migration leaves it) -- these teams are identified going
-- forward via `team_provider_ids`, not the legacy column.
insert into teams (id, league_id, name) values
  ('a3000000-0000-0000-0000-000000000007', 'a2000000-0000-0000-0000-000000000002', 'Arizona Cardinals'),
  ('a3000000-0000-0000-0000-000000000008', 'a2000000-0000-0000-0000-000000000002', 'Atlanta Falcons'),
  ('a3000000-0000-0000-0000-000000000009', 'a2000000-0000-0000-0000-000000000002', 'Carolina Panthers'),
  ('a3000000-0000-0000-0000-00000000000a', 'a2000000-0000-0000-0000-000000000002', 'Chicago Bears'),
  ('a3000000-0000-0000-0000-00000000000b', 'a2000000-0000-0000-0000-000000000002', 'Cincinnati Bengals'),
  ('a3000000-0000-0000-0000-00000000000c', 'a2000000-0000-0000-0000-000000000002', 'Cleveland Browns'),
  ('a3000000-0000-0000-0000-00000000000d', 'a2000000-0000-0000-0000-000000000002', 'Denver Broncos'),
  ('a3000000-0000-0000-0000-00000000000e', 'a2000000-0000-0000-0000-000000000002', 'Detroit Lions'),
  ('a3000000-0000-0000-0000-00000000000f', 'a2000000-0000-0000-0000-000000000002', 'Green Bay Packers'),
  ('a3000000-0000-0000-0000-000000000010', 'a2000000-0000-0000-0000-000000000002', 'Houston Texans'),
  ('a3000000-0000-0000-0000-000000000011', 'a2000000-0000-0000-0000-000000000002', 'Indianapolis Colts'),
  ('a3000000-0000-0000-0000-000000000012', 'a2000000-0000-0000-0000-000000000002', 'Jacksonville Jaguars'),
  ('a3000000-0000-0000-0000-000000000013', 'a2000000-0000-0000-0000-000000000002', 'Las Vegas Raiders'),
  ('a3000000-0000-0000-0000-000000000014', 'a2000000-0000-0000-0000-000000000002', 'Los Angeles Chargers'),
  ('a3000000-0000-0000-0000-000000000015', 'a2000000-0000-0000-0000-000000000002', 'Los Angeles Rams'),
  ('a3000000-0000-0000-0000-000000000016', 'a2000000-0000-0000-0000-000000000002', 'Miami Dolphins'),
  ('a3000000-0000-0000-0000-000000000017', 'a2000000-0000-0000-0000-000000000002', 'Minnesota Vikings'),
  ('a3000000-0000-0000-0000-000000000018', 'a2000000-0000-0000-0000-000000000002', 'New England Patriots'),
  ('a3000000-0000-0000-0000-000000000019', 'a2000000-0000-0000-0000-000000000002', 'New Orleans Saints'),
  ('a3000000-0000-0000-0000-00000000001a', 'a2000000-0000-0000-0000-000000000002', 'New York Giants'),
  ('a3000000-0000-0000-0000-00000000001b', 'a2000000-0000-0000-0000-000000000002', 'New York Jets'),
  ('a3000000-0000-0000-0000-00000000001c', 'a2000000-0000-0000-0000-000000000002', 'Pittsburgh Steelers'),
  ('a3000000-0000-0000-0000-00000000001d', 'a2000000-0000-0000-0000-000000000002', 'Seattle Seahawks'),
  ('a3000000-0000-0000-0000-00000000001e', 'a2000000-0000-0000-0000-000000000002', 'Tampa Bay Buccaneers'),
  ('a3000000-0000-0000-0000-00000000001f', 'a2000000-0000-0000-0000-000000000002', 'Tennessee Titans'),
  ('a3000000-0000-0000-0000-000000000020', 'a2000000-0000-0000-0000-000000000002', 'Washington Commanders');

-- team_provider_ids: real (not synthetic) provider representations for each seed
-- team, mirroring the 3E-3 migration's backfill -- so a fresh `supabase db reset`
-- lands in the same state as dev's migrated data. See app/persistence/team_backfill.py
-- (the single source of truth for this mapping) for full provenance.
insert into team_provider_ids (team_id, provider_name, provider_team_id) values
  ('a3000000-0000-0000-0000-000000000001', 'the_odds_api', 'Kansas City Chiefs'),
  ('a3000000-0000-0000-0000-000000000001', 'sportsdataio', 'KC'),
  ('a3000000-0000-0000-0000-000000000002', 'the_odds_api', 'Buffalo Bills'),
  ('a3000000-0000-0000-0000-000000000002', 'sportsdataio', 'BUF'),
  ('a3000000-0000-0000-0000-000000000003', 'the_odds_api', 'San Francisco 49ers'),
  ('a3000000-0000-0000-0000-000000000003', 'sportsdataio', 'SF'),
  ('a3000000-0000-0000-0000-000000000004', 'the_odds_api', 'Philadelphia Eagles'),
  ('a3000000-0000-0000-0000-000000000004', 'sportsdataio', 'PHI'),
  ('a3000000-0000-0000-0000-000000000005', 'the_odds_api', 'Dallas Cowboys'),
  ('a3000000-0000-0000-0000-000000000005', 'sportsdataio', 'DAL'),
  ('a3000000-0000-0000-0000-000000000006', 'the_odds_api', 'Baltimore Ravens'),
  ('a3000000-0000-0000-0000-000000000006', 'sportsdataio', 'BAL');

-- Phase 3E-4A: 9 additional fixture-confirmed sportsdataio mappings,
-- mirroring the 20260814050000 migration's backfill exactly (see
-- app/persistence/team_backfill.py for full provenance).
insert into team_provider_ids (team_id, provider_name, provider_team_id) values
  ('a3000000-0000-0000-0000-000000000007', 'sportsdataio', 'ARI'),
  ('a3000000-0000-0000-0000-000000000008', 'sportsdataio', 'ATL'),
  ('a3000000-0000-0000-0000-000000000009', 'sportsdataio', 'CAR'),
  ('a3000000-0000-0000-0000-00000000000a', 'sportsdataio', 'CHI'),
  ('a3000000-0000-0000-0000-000000000015', 'sportsdataio', 'LAR'),
  ('a3000000-0000-0000-0000-000000000018', 'sportsdataio', 'NE'),
  ('a3000000-0000-0000-0000-000000000019', 'sportsdataio', 'NO'),
  ('a3000000-0000-0000-0000-00000000001d', 'sportsdataio', 'SEA'),
  ('a3000000-0000-0000-0000-00000000001e', 'sportsdataio', 'TB');

-- 2026-08-18: 17 additional sportsdataio mappings, confirmed via a live
-- capture of /v3/nfl/scores/json/Teams (mirroring the 20260818040000
-- migration exactly -- see app/persistence/team_backfill.py and
-- tests/fixtures/sportsdataio/PROVENANCE.md for full provenance).
-- sportsdataio coverage is now 32/32; the_odds_api remains at 6/32.
insert into team_provider_ids (team_id, provider_name, provider_team_id) values
  ('a3000000-0000-0000-0000-00000000000b', 'sportsdataio', 'CIN'),
  ('a3000000-0000-0000-0000-00000000000c', 'sportsdataio', 'CLE'),
  ('a3000000-0000-0000-0000-00000000000d', 'sportsdataio', 'DEN'),
  ('a3000000-0000-0000-0000-00000000000e', 'sportsdataio', 'DET'),
  ('a3000000-0000-0000-0000-00000000000f', 'sportsdataio', 'GB'),
  ('a3000000-0000-0000-0000-000000000010', 'sportsdataio', 'HOU'),
  ('a3000000-0000-0000-0000-000000000011', 'sportsdataio', 'IND'),
  ('a3000000-0000-0000-0000-000000000012', 'sportsdataio', 'JAX'),
  ('a3000000-0000-0000-0000-000000000013', 'sportsdataio', 'LV'),
  ('a3000000-0000-0000-0000-000000000014', 'sportsdataio', 'LAC'),
  ('a3000000-0000-0000-0000-000000000016', 'sportsdataio', 'MIA'),
  ('a3000000-0000-0000-0000-000000000017', 'sportsdataio', 'MIN'),
  ('a3000000-0000-0000-0000-00000000001a', 'sportsdataio', 'NYG'),
  ('a3000000-0000-0000-0000-00000000001b', 'sportsdataio', 'NYJ'),
  ('a3000000-0000-0000-0000-00000000001c', 'sportsdataio', 'PIT'),
  ('a3000000-0000-0000-0000-00000000001f', 'sportsdataio', 'TEN'),
  ('a3000000-0000-0000-0000-000000000020', 'sportsdataio', 'WAS');

insert into players (id, team_id, name, position, external_provider_id) values
  ('a4000000-0000-0000-0000-000000000001', 'a3000000-0000-0000-0000-000000000001', 'Seed QB Chiefs', 'QB', 'seed-p1'),
  ('a4000000-0000-0000-0000-000000000002', 'a3000000-0000-0000-0000-000000000001', 'Seed WR Chiefs', 'WR', 'seed-p2'),
  ('a4000000-0000-0000-0000-000000000003', 'a3000000-0000-0000-0000-000000000002', 'Seed QB Bills', 'QB', 'seed-p3'),
  ('a4000000-0000-0000-0000-000000000004', 'a3000000-0000-0000-0000-000000000002', 'Seed RB Bills', 'RB', 'seed-p4'),
  ('a4000000-0000-0000-0000-000000000005', 'a3000000-0000-0000-0000-000000000003', 'Seed QB Niners', 'QB', 'seed-p5'),
  ('a4000000-0000-0000-0000-000000000006', 'a3000000-0000-0000-0000-000000000004', 'Seed QB Eagles', 'QB', 'seed-p6');

-- ============================================================================
-- Games: one final (with stats + postgame review), one live, two scheduled
-- ============================================================================

insert into games (id, external_provider_id, sport_id, league_id, season_id, sport, home_team, away_team, scheduled_start, stadium, status, final_score) values
  ('a5000000-0000-0000-0000-000000000001', 'seed-game-final', 'a2000000-0000-0000-0000-000000000001', 'a2000000-0000-0000-0000-000000000002', 'a2000000-0000-0000-0000-000000000003', 'nfl', 'Kansas City Chiefs', 'Buffalo Bills', now() - interval '3 days', 'GEHA Field at Arrowhead Stadium', 'final', '{"home": 27, "away": 24}'),
  ('a5000000-0000-0000-0000-000000000002', 'seed-game-live', 'a2000000-0000-0000-0000-000000000001', 'a2000000-0000-0000-0000-000000000002', 'a2000000-0000-0000-0000-000000000003', 'nfl', 'San Francisco 49ers', 'Philadelphia Eagles', now() - interval '1 hour', 'Levi''s Stadium', 'live', null),
  ('a5000000-0000-0000-0000-000000000003', 'seed-game-upcoming', 'a2000000-0000-0000-0000-000000000001', 'a2000000-0000-0000-0000-000000000002', 'a2000000-0000-0000-0000-000000000003', 'nfl', 'Dallas Cowboys', 'Baltimore Ravens', now() + interval '2 days', 'AT&T Stadium', 'scheduled', null),
  ('a5000000-0000-0000-0000-000000000004', 'seed-game-later', 'a2000000-0000-0000-0000-000000000001', 'a2000000-0000-0000-0000-000000000002', 'a2000000-0000-0000-0000-000000000003', 'nfl', 'Buffalo Bills', 'Kansas City Chiefs', now() + interval '9 days', 'Highmark Stadium', 'scheduled', null);

-- game_provider_ids: mirrors the 3E-1 migration's backfill behavior (every existing
-- games.external_provider_id treated as a the_odds_api id) so a fresh `supabase db reset`
-- lands in the same state as dev's migrated data.
insert into game_provider_ids (game_id, provider_name, provider_game_id) values
  ('a5000000-0000-0000-0000-000000000001', 'the_odds_api', 'seed-game-final'),
  ('a5000000-0000-0000-0000-000000000002', 'the_odds_api', 'seed-game-live'),
  ('a5000000-0000-0000-0000-000000000003', 'the_odds_api', 'seed-game-upcoming'),
  ('a5000000-0000-0000-0000-000000000004', 'the_odds_api', 'seed-game-later');

insert into player_stats (id, player_id, game_id, stats) values
  ('a6000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000001', '{"completions": 24, "attempts": 33}'),
  ('a6000000-0000-0000-0000-000000000002', 'a4000000-0000-0000-0000-000000000003', 'a5000000-0000-0000-0000-000000000001', '{"completions": 26, "attempts": 40}');
insert into player_stats_nfl (player_stat_id, passing_yards, receiving_yards, rushing_yards, interceptions, sacks) values
  ('a6000000-0000-0000-0000-000000000001', 286, 0, 12, 0, 2),
  ('a6000000-0000-0000-0000-000000000002', 312, 0, 8, 1, 3);
insert into team_stats (id, team_id, game_id, stats) values
  ('a7000000-0000-0000-0000-000000000001', 'a3000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000001', '{"total_yards": 401, "turnovers": 1}'),
  ('a7000000-0000-0000-0000-000000000002', 'a3000000-0000-0000-0000-000000000002', 'a5000000-0000-0000-0000-000000000001', '{"total_yards": 388, "turnovers": 2}');

-- ============================================================================
-- Append-only market/context snapshots (line movement on the upcoming game)
-- ============================================================================

insert into odds_snapshots (game_id, sportsbook, market_type, line_data, captured_at) values
  ('a5000000-0000-0000-0000-000000000003', 'DraftKings', 'spread', '{"home": -3.5, "away": 3.5, "home_price": -110, "away_price": -110}', now() - interval '2 days'),
  ('a5000000-0000-0000-0000-000000000003', 'DraftKings', 'spread', '{"home": -2.5, "away": 2.5, "home_price": -108, "away_price": -112}', now() - interval '1 day'),
  ('a5000000-0000-0000-0000-000000000003', 'DraftKings', 'moneyline', '{"home": -165, "away": 145}', now() - interval '1 day'),
  ('a5000000-0000-0000-0000-000000000003', 'FanDuel', 'total', '{"points": 47.5, "over_price": -110, "under_price": -110}', now() - interval '1 day');

insert into injury_reports (game_id, report_data, captured_at) values
  ('a5000000-0000-0000-0000-000000000003', '{"player": "Seed RB Bills", "status": "questionable", "injury": "ankle"}', now() - interval '1 day');
insert into weather_snapshots (game_id, weather_data, captured_at) values
  ('a5000000-0000-0000-0000-000000000003', '{"temp_f": 72, "wind_mph": 8, "precipitation_pct": 5, "condition": "clear"}', now() - interval '6 hours');
insert into depth_chart_snapshots (game_id, depth_chart_data, captured_at) values
  ('a5000000-0000-0000-0000-000000000003', '{"team": "Dallas Cowboys", "changes": []}', now() - interval '1 day');
insert into referee_assignments (game_id, assignment_data, captured_at) values
  ('a5000000-0000-0000-0000-000000000003', '{"referee": "Seed Referee", "crew": "Crew A"}', now() - interval '2 days');

-- ============================================================================
-- Master working table + derived scores for the upcoming game
-- ============================================================================

insert into daily_game_intelligence (game_id, teams, odds, weather, injuries, ai_scores, last_updated) values
  ('a5000000-0000-0000-0000-000000000003',
   '{"home": "Dallas Cowboys", "away": "Baltimore Ravens"}',
   '{"value": {"spread": -2.5}, "source": "DraftKings", "confidence": 0.95, "last_updated": "2026-08-06T10:00:00Z", "status": "fresh"}',
   '{"value": {"temp_f": 72}, "source": "WeatherAPI", "confidence": 0.99, "last_updated": "2026-08-06T10:00:00Z", "status": "fresh"}',
   '{"value": {"questionable": 1}, "source": "SeedProvider", "confidence": 0.9, "last_updated": "2026-08-06T10:00:00Z", "status": "fresh"}',
   '{"weather_score": 0.62, "injury_score": 0.55}',
   now());

insert into weather_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.6200);
insert into injury_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.5500);
insert into travel_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.7100);
insert into rest_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.8000);
insert into momentum_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.4500);
insert into matchup_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.6600);
insert into line_value_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.5800);
insert into sharp_money_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.7000);
insert into schedule_difficulty_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.5000);
insert into offensive_matchup_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.6900);
insert into defensive_matchup_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.5300);
insert into coaching_edge_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.5100);
insert into public_sentiment_scores (game_id, score) values ('a5000000-0000-0000-0000-000000000003', 0.6300);

-- ============================================================================
-- AI intelligence: agents, recommendations, agent outputs, consensus, explainability
-- ============================================================================

insert into agents (id, name, category, active, current_weight) values
  ('a8000000-0000-0000-0000-000000000001', 'injury_intelligence_agent', 'context', true, 1.05),
  ('a8000000-0000-0000-0000-000000000002', 'weather_agent', 'context', true, 0.95),
  ('a8000000-0000-0000-0000-000000000003', 'sharp_money_agent', 'market', true, 1.10),
  ('a8000000-0000-0000-0000-000000000004', 'matchup_agent', 'analytics', true, 1.00),
  ('a8000000-0000-0000-0000-000000000005', 'momentum_agent', 'analytics', true, 0.90),
  ('a8000000-0000-0000-0000-000000000006', 'meta_agent', 'meta', true, 1.00);

-- Milestone 4.5 additive dev-only agent rows (Decision D, 2026-08-21):
-- rest_days_agent/travel_fatigue_agent were built in Milestone 4.4 but
-- never seeded (4.4 built no persistence path); vegas_line_agent/
-- closing_line_movement_agent are the two new Milestone 4.5 agents.
-- current_weight=1.00 is an UNTUNED INITIAL WEIGHT for all four -- it
-- does not mean historical performance has proven equal weighting. Purely
-- additive: no existing row above is modified or removed. The broader
-- Phase-1 fixture cleanup proposed at Milestone 4.1's close remains
-- deferred until the real 22-agent roster is seeded; this partial
-- 10-row dev configuration is not the final committee.
insert into agents (id, name, category, active, current_weight) values
  ('a8000000-0000-0000-0000-000000000007', 'rest_days_agent', 'context', true, 1.00),
  ('a8000000-0000-0000-0000-000000000008', 'travel_fatigue_agent', 'context', true, 1.00),
  ('a8000000-0000-0000-0000-000000000009', 'vegas_line_agent', 'market', true, 1.00),
  ('a8000000-0000-0000-0000-000000000010', 'closing_line_movement_agent', 'market', true, 1.00);

-- Milestone 4.6 additive dev-only agent rows (Decision D, 2026-08-22):
-- the four new sequential Decision & Advisory agents. current_weight=1.00
-- is again an UNTUNED INITIAL WEIGHT, not a tuned decision. Purely
-- additive: no existing row above is modified or removed. The broader
-- Phase-1 fixture cleanup remains deferred until the real 22-agent
-- roster is seeded; this partial 14-row dev configuration is still not
-- the final committee.
insert into agents (id, name, category, active, current_weight) values
  ('a8000000-0000-0000-0000-000000000011', 'probability_modeling_agent', 'decision', true, 1.00),
  ('a8000000-0000-0000-0000-000000000012', 'expected_value_agent', 'decision', true, 1.00),
  ('a8000000-0000-0000-0000-000000000013', 'risk_manager_agent', 'decision', true, 1.00),
  ('a8000000-0000-0000-0000-000000000014', 'bankroll_coach_agent', 'decision', true, 1.00);

-- Milestone 4.7 configuration-gap backfill (Milestone 4.8 fixture-sync
-- fix, 2026-08-24): consensus_reconciliation_agent (the Elite
-- Reconciliation Agent) was inserted directly against live dev during
-- Milestone 4.7 but never backfilled into this seed script -- a real
-- drift between seed.sql and live dev (15 live rows vs. 14 producible
-- from this file), found and closed during the Milestone 4.8 inspection.
-- id/category/current_weight match the live row exactly.
insert into agents (id, name, category, active, current_weight) values
  ('a8000000-0000-0000-0000-000000000015', 'consensus_reconciliation_agent', 'meta', true, 1.00);

insert into agent_performance_scores (agent_id, evaluation_window_start, evaluation_window_end, roi, ev, clv, confidence_calibration_score, sample_size) values
  ('a8000000-0000-0000-0000-000000000001', '2026-07-01', '2026-07-31', 0.0820, 0.0450, 1.2000, 0.8800, 42),
  ('a8000000-0000-0000-0000-000000000003', '2026-07-01', '2026-07-31', 0.1140, 0.0610, 1.8000, 0.9100, 38);

insert into recommendations (id, game_id, user_facing, recommendation_type, bet_details, confidence_score, expected_value, risk_level, status, min_required_tier, ai_version, prompt_version, agent_version, consensus_version, weight_version, display_id) values
  ('a9000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000003', true, 'single', '{"team": "Dallas Cowboys", "market": "spread", "line": -2.5, "odds": -108}', 0.6800, 0.0520, 'moderate', 'active', 'free', 'v1', 'nfl_single_v1.0', 'v1', 'v1', 'v1', 'PB-2026-NFL-000001'),
  ('a9000000-0000-0000-0000-000000000002', 'a5000000-0000-0000-0000-000000000003', true, 'same_game_parlay', '{"legs": [{"team": "Dallas Cowboys", "market": "moneyline"}, {"market": "total", "side": "under", "line": 47.5}]}', 0.5900, 0.0710, 'high', 'active', 'elite', 'v1', 'nfl_parlay_v1.0', 'v1', 'v1', 'v1', 'PB-2026-NFL-000002'),
  ('a9000000-0000-0000-0000-000000000003', 'a5000000-0000-0000-0000-000000000004', true, 'no_bet', null, null, null, null, 'active', 'free', 'v1', 'nfl_single_v1.0', 'v1', 'v1', 'v1', 'PB-2026-NFL-000003');

insert into recommendation_agent_outputs (recommendation_id, agent_id, raw_output, agent_confidence, weight_applied) values
  ('a9000000-0000-0000-0000-000000000001', 'a8000000-0000-0000-0000-000000000001', '{"finding": "no significant injuries", "classification": "fact"}', 0.7500, 1.05),
  ('a9000000-0000-0000-0000-000000000001', 'a8000000-0000-0000-0000-000000000003', '{"finding": "sharp money on home team", "classification": "fact"}', 0.7000, 1.10),
  ('a9000000-0000-0000-0000-000000000001', 'a8000000-0000-0000-0000-000000000004', '{"finding": "favorable matchup vs run defense", "classification": "assumption"}', 0.6200, 1.00);

insert into consensus_snapshots (recommendation_id, aggregate_confidence, agreement_variance, model_routing_used, second_pass_triggered) values
  ('a9000000-0000-0000-0000-000000000001', 0.6800, 0.0650, '{"injury_intelligence_agent": "claude-sonnet-5", "sharp_money_agent": "claude-sonnet-5"}', false);

insert into explainability_payloads (recommendation_id, why_this_recommendation, why_this_bet_type, why_now, why_not_alternatives, strongest_evidence, biggest_risks, invalidating_conditions, contributing_agents, persona_fit_explanation) values
  ('a9000000-0000-0000-0000-000000000001',
   'Dallas shows a favorable matchup edge against Baltimore''s run defense with sharp money already moving the line.',
   'A single bet keeps risk contained given moderate confidence.',
   'Line value is best now, before it moves further toward Dallas.',
   'A parlay was considered but rejected due to lower combined confidence.',
   'Sharp money movement from -3.5 to -2.5 despite even public betting split.',
   'Weather could shift late in the week; a key offensive lineman is questionable.',
   'If the questionable lineman is ruled out, confidence would drop below the recommendation threshold.',
   array['a8000000-0000-0000-0000-000000000001','a8000000-0000-0000-0000-000000000003','a8000000-0000-0000-0000-000000000004']::uuid[],
   'Matches the free-tier casual persona''s preference for single, lower-risk bets.');

insert into recommendation_snapshots (recommendation_id, full_environment_snapshot, agent_outputs_snapshot, consensus_snapshot) values
  ('a9000000-0000-0000-0000-000000000001',
   '{"odds": {"spread": -2.5}, "weather": {"temp_f": 72}, "injuries": {"questionable": 1}}',
   '{"agents": ["injury_intelligence_agent", "sharp_money_agent", "matchup_agent"]}',
   '{"aggregate_confidence": 0.68, "agreement_variance": 0.065}');

-- ============================================================================
-- Bet verification & performance attribution, tied to the finished game
-- ============================================================================

insert into recommendations (id, game_id, user_facing, recommendation_type, bet_details, confidence_score, expected_value, risk_level, status, min_required_tier, ai_version, display_id, created_at) values
  ('a9000000-0000-0000-0000-000000000004', 'a5000000-0000-0000-0000-000000000001', true, 'single', '{"team": "Kansas City Chiefs", "market": "moneyline", "odds": -150}', 0.7200, 0.0380, 'low', 'settled_win', 'free', 'v1', 'PB-2026-NFL-000000', now() - interval '4 days');

insert into bet_slips (id, user_id, image_storage_path, ocr_extracted_data, linked_recommendation_id) values
  ('aa000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000001', 'seed/bet-slips/seed-slip-1.jpg', '{"stake": 25.00, "odds": -150}', 'a9000000-0000-0000-0000-000000000004');

insert into verified_bets (id, user_id, bet_slip_id, recommendation_id, stake, odds, outcome, payout) values
  ('ab000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000001', 'aa000000-0000-0000-0000-000000000001', 'a9000000-0000-0000-0000-000000000004', 25.00, -150.00, 'win', 41.67);

insert into ai_performance (evaluation_window_start, evaluation_window_end, roi, ev, clv, units, sport, bet_type) values
  ('2026-07-01', '2026-07-31', 0.0640, 0.0410, 1.3500, 12.40, 'nfl', 'single');

insert into projected_user_performance (user_id, recommendation_id, projected_units) values
  ('a1000000-0000-0000-0000-000000000001', 'a9000000-0000-0000-0000-000000000004', 1.0000);
insert into verified_user_performance (user_id, verified_bet_id, actual_units) values
  ('a1000000-0000-0000-0000-000000000001', 'ab000000-0000-0000-0000-000000000001', 0.6668);

-- ============================================================================
-- Postgame review & market monitoring
-- ============================================================================

insert into postgame_reviews (recommendation_id, outcome_summary, why_it_won_or_lost, weather_impact_assessment, injury_impact_assessment, line_movement_impact_assessment, correct_agents, underperforming_agents, learning_notes) values
  ('a9000000-0000-0000-0000-000000000004',
   'Chiefs won 27-24, covering the moneyline as recommended.',
   'Chiefs'' offense controlled the fourth quarter as the sharp-money signal predicted.',
   'Clear conditions, no material weather impact.',
   'No key injuries affected the outcome.',
   'Line held steady pre-game, consistent with the initial read.',
   array['a8000000-0000-0000-0000-000000000003']::uuid[],
   array[]::uuid[],
   'Sharp money signal correlated well with this outcome; continue weighting it favorably.');

insert into market_monitoring_events (game_id, event_type, event_data, affected_recommendation_ids, action_taken) values
  ('a5000000-0000-0000-0000-000000000003', 'line_movement', '{"from": -3.5, "to": -2.5, "sportsbook": "DraftKings"}', array['a9000000-0000-0000-0000-000000000001']::uuid[], 'none');

-- ============================================================================
-- AI orchestration config (feature_flags/prompt_registry/model_routing_rules writes
-- also exercise the log_config_change() audit trigger automatically)
-- ============================================================================

insert into model_routing_rules (task_type, primary_model, fallback_model, min_tier_for_second_pass, active) values
  ('injury_analysis', 'claude-sonnet-5', 'claude-haiku-4-5-20251001', 'elite', true),
  ('consensus_reconciliation', 'claude-opus-5', 'claude-sonnet-5', 'elite', true);

-- Milestone 4.5 additive dev-only routing rows (Decision D, 2026-08-21):
-- the two new Market agents' task_types. Same primary/fallback pairing
-- as injury_analysis -- a Phase-1-seed-style placeholder, not a
-- cost-tuned decision (matching the precedent already documented for
-- the two original rows above).
insert into model_routing_rules (task_type, primary_model, fallback_model, min_tier_for_second_pass, active) values
  ('vegas_line_analysis', 'claude-sonnet-5', 'claude-haiku-4-5-20251001', 'elite', true),
  ('closing_line_movement_analysis', 'claude-sonnet-5', 'claude-haiku-4-5-20251001', 'elite', true);

-- Milestone 4.6 configuration-gap backfill (2026-08-22): these three
-- Milestone 4.4 agents' task_types were never seeded (4.4 built no
-- persistence/routing wiring at all) -- closing that gap, not new scope.
insert into model_routing_rules (task_type, primary_model, fallback_model, min_tier_for_second_pass, active) values
  ('rest_days_analysis', 'claude-sonnet-5', 'claude-haiku-4-5-20251001', 'elite', true),
  ('travel_fatigue_analysis', 'claude-sonnet-5', 'claude-haiku-4-5-20251001', 'elite', true),
  ('weather_analysis', 'claude-sonnet-5', 'claude-haiku-4-5-20251001', 'elite', true);

-- Milestone 4.6 new routing rows for the sequential Decision & Advisory
-- chain (Decision: routing config). Probability Modeling routes to the
-- stronger tier (Volume 4 Section 3.2 names it explicitly); Expected
-- Value/Risk Manager/Bankroll Coach stay on the cheap tier -- their
-- arithmetic is deterministic application code, the LLM layer is
-- narration only, so there's no evidence they need a stronger model
-- (Mac's explicit instruction: "do not overpay for arithmetic
-- narration"). All provisional configuration, FakeModelAdapter-only
-- until real model validation.
insert into model_routing_rules (task_type, primary_model, fallback_model, min_tier_for_second_pass, active) values
  ('probability_modeling_analysis', 'claude-opus-5', 'claude-sonnet-5', 'elite', true),
  ('expected_value_analysis', 'claude-sonnet-5', 'claude-haiku-4-5-20251001', 'elite', true),
  ('risk_manager_analysis', 'claude-sonnet-5', 'claude-haiku-4-5-20251001', 'elite', true),
  ('bankroll_coach_analysis', 'claude-sonnet-5', 'claude-haiku-4-5-20251001', 'elite', true);

insert into prompt_registry (prompt_name, version, prompt_text, status, owner) values
  ('nfl_single_v1.0', 1, 'Seed prompt text for single-bet recommendation generation.', 'active', 'seed-script'),
  ('nfl_parlay_v1.0', 1, 'Seed prompt text for same-game parlay recommendation generation.', 'active', 'seed-script');

-- Milestone 4.8 (Phase 4 Closeout Remediation) canonical agent prompts:
-- prompt_registry becomes the production source of every real agent's
-- system prompt (Mac's approved direction), prompt_name = agent_name.
-- These are NOT a reinterpretation of nfl_single_v1.0/nfl_parlay_v1.0
-- above (an unrelated, separate Phase-1 "recommendation-type prompt"
-- concept, left untouched) -- one row per real built agent, wording
-- preserved byte-for-byte from each agent base class's prior hardcoded
-- template via scripts/generate_prompt_registry_seed.py (not
-- hand-transcribed). idx_prompt_registry_one_active_per_name guarantees
-- exactly one active version per prompt_name.
insert into prompt_registry (prompt_name, version, prompt_text, status, owner) values
  ('bankroll_coach_agent', 1, 'You are the bankroll_coach_agent, part of The Playbook''s sequential decision chain -- you reason over the committee''s own findings and already-computed deterministic numbers, never raw game facts directly.

You will be given a JSON object containing upstream findings and/or already-computed deterministic values (probabilities, EV, variance, stake math). Do not recompute, guess, or invent any numeric value that is already provided -- treat every given value exactly as given, including any "null" value, which means that piece of information is genuinely unavailable, never neutral or zero. Reason only about what these already-computed facts mean for this specific wager.

Partial committee participation is normal, not a failure: some upstream agent categories may be intentionally deferred (no capability exists yet), which is different from an agent that ran and failed this cycle. Weigh only the findings actually present; never fabricate a missing category''s opinion.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "<this agent''s name>",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}', 'active', 'milestone-4.8-seed'),
  ('closing_line_movement_agent', 1, 'You are the closing_line_movement_agent, one independent voice on The Playbook''s committee of sports-betting analysis agents.

You will be given a JSON object of already-computed facts. Do not recompute, guess, or invent any numeric or factual value -- treat every value in the evidence exactly as given, including any "null" value, which means that piece of information is genuinely unavailable, never neutral or zero. Reason only about this game''s football/betting significance.

Freshness discipline: a fact whose "status" field reads "needs_refresh" or "stale" may still be reasoned over, but your evidence_classification and confidence must reflect that staleness risk. A "null" fact must never be treated as if it were a neutral/average value -- classify your finding as "assumption" and lower your confidence accordingly, naming the specific missing evidence in your finding and would_change_mind_if fields.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "closing_line_movement_agent",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}', 'active', 'milestone-4.8-seed'),
  ('consensus_reconciliation_agent', 1, 'You are the consensus_reconciliation_agent, reviewing The Playbook''s committee output for one specific betting candidate -- you do not analyze the game or the candidate directly, only the committee''s already-computed findings and consensus result given to you.

You will be given the fan-out committee''s findings (grouped by functional category) and the deterministic aggregate_confidence/agreement_variance already computed for this candidate. Do not recompute, guess, or invent any numeric value that is already provided -- treat every given value exactly as given. Partial committee participation is normal: some agent categories may be intentionally deferred (no capability exists yet), which is different from an agent that ran and failed this cycle -- weigh only the findings actually present.

Hard rule: confidence_adjustment can only ever be zero or negative -- reconciliation may preserve or reduce confidence, never increase it.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "<this agent''s name>",
  "candidate_key": "<the candidate key, exactly as given>",
  "reasoning": "reconciliation reasoning",
  "confidence_adjustment": 0.0,
  "supporting_evidence": ["specific disagreement points reconciled"],
  "would_change_mind_if": "explicit invalidation condition"
}', 'active', 'milestone-4.8-seed'),
  ('expected_value_agent', 1, 'You are the expected_value_agent, part of The Playbook''s sequential decision chain -- you reason over the committee''s own findings and already-computed deterministic numbers, never raw game facts directly.

You will be given a JSON object containing upstream findings and/or already-computed deterministic values (probabilities, EV, variance, stake math). Do not recompute, guess, or invent any numeric value that is already provided -- treat every given value exactly as given, including any "null" value, which means that piece of information is genuinely unavailable, never neutral or zero. Reason only about what these already-computed facts mean for this specific wager.

Partial committee participation is normal, not a failure: some upstream agent categories may be intentionally deferred (no capability exists yet), which is different from an agent that ran and failed this cycle. Weigh only the findings actually present; never fabricate a missing category''s opinion.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "<this agent''s name>",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}', 'active', 'milestone-4.8-seed'),
  ('injury_intelligence_agent', 1, 'You are the injury_intelligence_agent, one independent voice on The Playbook''s committee of sports-betting analysis agents.

You will be given a JSON object of already-computed facts. Do not recompute, guess, or invent any numeric or factual value -- treat every value in the evidence exactly as given, including any "null" value, which means that piece of information is genuinely unavailable, never neutral or zero. Reason only about this game''s football/betting significance.

Freshness discipline: a fact whose "status" field reads "needs_refresh" or "stale" may still be reasoned over, but your evidence_classification and confidence must reflect that staleness risk. A "null" fact must never be treated as if it were a neutral/average value -- classify your finding as "assumption" and lower your confidence accordingly, naming the specific missing evidence in your finding and would_change_mind_if fields.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "injury_intelligence_agent",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}', 'active', 'milestone-4.8-seed'),
  ('meta_agent', 1, 'You are the meta_agent, reviewing The Playbook''s committee output for one specific betting candidate -- you do not analyze the game or the candidate directly, only the committee''s already-computed findings and consensus result given to you.

You will be given the fan-out committee''s findings (grouped by functional category) and the deterministic aggregate_confidence/agreement_variance already computed for this candidate. Do not recompute, guess, or invent any numeric value that is already provided -- treat every given value exactly as given. Partial committee participation is normal: some agent categories may be intentionally deferred (no capability exists yet), which is different from an agent that ran and failed this cycle -- weigh only the findings actually present.

Hard rule: confidence_adjustment can only ever be zero or negative -- you may only hold or lower confidence, never raise it.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "<this agent''s name>",
  "polarization_score": 0.0,
  "uncertainty_flag": false,
  "confidence_adjustment": 0.0,
  "reasoning": "plain-language summary of committee health for this candidate"
}', 'active', 'milestone-4.8-seed'),
  ('probability_modeling_agent', 1, 'You are the probability_modeling_agent, part of The Playbook''s sequential decision chain -- you reason over the committee''s own findings and already-computed deterministic numbers, never raw game facts directly.

You will be given a JSON object containing upstream findings and/or already-computed deterministic values (probabilities, EV, variance, stake math). Do not recompute, guess, or invent any numeric value that is already provided -- treat every given value exactly as given, including any "null" value, which means that piece of information is genuinely unavailable, never neutral or zero. Reason only about what these already-computed facts mean for this specific wager.

Partial committee participation is normal, not a failure: some upstream agent categories may be intentionally deferred (no capability exists yet), which is different from an agent that ran and failed this cycle. Weigh only the findings actually present; never fabricate a missing category''s opinion.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "<this agent''s name>",
  "candidate_key": "<the evaluated candidate''s key, exactly as given>",
  "selection": "<which side this probability applies to>",
  "modeled_probability": 0.0,
  "confidence_in_probability": 0.0,
  "reasoning": "plain-language explanation",
  "supporting_evidence": ["specific data points used"],
  "would_change_mind_if": "explicit invalidation condition"
}
modeled_probability is your calibrated estimate that this SPECIFIC candidate wins -- it is a different number from confidence_in_probability, which is how strongly you hold that estimate given the evidence actually available (e.g. lower confidence_in_probability when committee participation is partial).', 'active', 'milestone-4.8-seed'),
  ('rest_days_agent', 1, 'You are the rest_days_agent, one independent voice on The Playbook''s committee of sports-betting analysis agents.

You will be given a JSON object of already-computed facts. Do not recompute, guess, or invent any numeric or factual value -- treat every value in the evidence exactly as given, including any "null" value, which means that piece of information is genuinely unavailable, never neutral or zero. Reason only about this game''s football/betting significance.

Freshness discipline: a fact whose "status" field reads "needs_refresh" or "stale" may still be reasoned over, but your evidence_classification and confidence must reflect that staleness risk. A "null" fact must never be treated as if it were a neutral/average value -- classify your finding as "assumption" and lower your confidence accordingly, naming the specific missing evidence in your finding and would_change_mind_if fields.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "rest_days_agent",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}', 'active', 'milestone-4.8-seed'),
  ('risk_manager_agent', 1, 'You are the risk_manager_agent, part of The Playbook''s sequential decision chain -- you reason over the committee''s own findings and already-computed deterministic numbers, never raw game facts directly.

You will be given a JSON object containing upstream findings and/or already-computed deterministic values (probabilities, EV, variance, stake math). Do not recompute, guess, or invent any numeric value that is already provided -- treat every given value exactly as given, including any "null" value, which means that piece of information is genuinely unavailable, never neutral or zero. Reason only about what these already-computed facts mean for this specific wager.

Partial committee participation is normal, not a failure: some upstream agent categories may be intentionally deferred (no capability exists yet), which is different from an agent that ran and failed this cycle. Weigh only the findings actually present; never fabricate a missing category''s opinion.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "<this agent''s name>",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}', 'active', 'milestone-4.8-seed'),
  ('travel_fatigue_agent', 1, 'You are the travel_fatigue_agent, one independent voice on The Playbook''s committee of sports-betting analysis agents.

You will be given a JSON object of already-computed facts. Do not recompute, guess, or invent any numeric or factual value -- treat every value in the evidence exactly as given, including any "null" value, which means that piece of information is genuinely unavailable, never neutral or zero. Reason only about this game''s football/betting significance.

Freshness discipline: a fact whose "status" field reads "needs_refresh" or "stale" may still be reasoned over, but your evidence_classification and confidence must reflect that staleness risk. A "null" fact must never be treated as if it were a neutral/average value -- classify your finding as "assumption" and lower your confidence accordingly, naming the specific missing evidence in your finding and would_change_mind_if fields.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "travel_fatigue_agent",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}', 'active', 'milestone-4.8-seed'),
  ('vegas_line_agent', 1, 'You are the vegas_line_agent, one independent voice on The Playbook''s committee of sports-betting analysis agents.

You will be given a JSON object of already-computed facts. Do not recompute, guess, or invent any numeric or factual value -- treat every value in the evidence exactly as given, including any "null" value, which means that piece of information is genuinely unavailable, never neutral or zero. Reason only about this game''s football/betting significance.

Freshness discipline: a fact whose "status" field reads "needs_refresh" or "stale" may still be reasoned over, but your evidence_classification and confidence must reflect that staleness risk. A "null" fact must never be treated as if it were a neutral/average value -- classify your finding as "assumption" and lower your confidence accordingly, naming the specific missing evidence in your finding and would_change_mind_if fields.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "vegas_line_agent",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}', 'active', 'milestone-4.8-seed'),
  ('weather_agent', 1, 'You are the weather_agent, one independent voice on The Playbook''s committee of sports-betting analysis agents.

You will be given a JSON object of already-computed facts. Do not recompute, guess, or invent any numeric or factual value -- treat every value in the evidence exactly as given, including any "null" value, which means that piece of information is genuinely unavailable, never neutral or zero. Reason only about this game''s football/betting significance.

Freshness discipline: a fact whose "status" field reads "needs_refresh" or "stale" may still be reasoned over, but your evidence_classification and confidence must reflect that staleness risk. A "null" fact must never be treated as if it were a neutral/average value -- classify your finding as "assumption" and lower your confidence accordingly, naming the specific missing evidence in your finding and would_change_mind_if fields.

Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "weather_agent",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}', 'active', 'milestone-4.8-seed');

insert into model_registry (model_name, strengths, weaknesses, cost_per_1k_tokens, avg_latency_ms, preferred_tasks, capabilities, status) values
  ('claude-sonnet-5', 'Strong reasoning, good cost/latency balance', 'N/A', 0.003000, 1800, array['injury_analysis','matchup_analysis'], array['reasoning','tool_use'], 'active'),
  ('claude-opus-5', 'Highest reasoning quality', 'Higher cost/latency', 0.015000, 3200, array['consensus_reconciliation'], array['reasoning','tool_use'], 'active');

insert into feature_flags (flag_key, description, enabled, audience_tier, rollout_percentage) values
  ('beta_dashboard_v2', 'New dashboard layout, elite-tier beta', true, array['elite'], 25),
  ('experimental_consensus_v2', 'Experimental consensus algorithm', false, array['elite'], 0);

insert into recommendation_costs (recommendation_id, provider, cost_usd) values
  ('a9000000-0000-0000-0000-000000000001', 'anthropic', 0.042000),
  ('a9000000-0000-0000-0000-000000000001', 'sports_api', 0.008000),
  ('a9000000-0000-0000-0000-000000000004', 'anthropic', 0.038000);
