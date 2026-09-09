-- Phase 3E-1 (Decision 2, 2026-08-13) required test evidence:
--   1. A SportsDataIO id and a The Odds API id can both resolve to the SAME games.id
--      without creating a duplicate game.
--   2. A provider id cannot silently map to two different games.
-- Run via `supabase test db`, or manually inside a transaction that's rolled back --
-- same convention as rls_policies_test.sql and migration_reversibility_check.sql.
--
-- MSF Game Provider ID Enablement (2026-09-09): Proof 3 below is the
-- minimum required coverage for the 20260909190200 migration -- confirms
-- 'mysportsfeeds' is now an accepted provider_name value on this table,
-- exactly the same shape as the existing the_odds_api/sportsdataio proofs
-- above, no new test mechanism invented.

begin;
create extension if not exists pgtap with schema extensions;
select plan(5);

insert into sports (id, code, name) values ('d0000000-0000-0000-0000-000000000001', 'nfl', 'NFL');
insert into leagues (id, sport_id, code, name) values ('d0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000001', 'nfl', 'NFL');
insert into seasons (id, league_id, year) values ('d0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000002', 2026);
insert into games (id, sport_id, league_id, season_id, sport, home_team, away_team, scheduled_start, status)
values ('d0000000-0000-0000-0000-000000000004', 'd0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000003', 'nfl', 'Home', 'Away', now() + interval '1 day', 'scheduled'),
       ('d0000000-0000-0000-0000-000000000005', 'd0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000003', 'nfl', 'Home2', 'Away2', now() + interval '2 days', 'scheduled');

-- Proof 1: two different providers' ids both resolve to the same games.id.
insert into game_provider_ids (game_id, provider_name, provider_game_id) values
  ('d0000000-0000-0000-0000-000000000004', 'the_odds_api', 'gptest-odds-1'),
  ('d0000000-0000-0000-0000-000000000004', 'sportsdataio', '202609061');

select ok(
  (select count(distinct game_id) from game_provider_ids
   where provider_game_id in ('gptest-odds-1', '202609061')) = 1,
  'a the_odds_api id and a sportsdataio id both resolve to exactly one games.id'
);
select ok(
  (select count(*) = 0 from games g
   where g.id not in ('d0000000-0000-0000-0000-000000000004', 'd0000000-0000-0000-0000-000000000005')),
  'no extra games row was created by mapping two provider ids to one game'
);

-- Proof 2a: the SAME provider id cannot map to a DIFFERENT game.
select throws_ok(
  $$ insert into game_provider_ids (game_id, provider_name, provider_game_id)
     values ('d0000000-0000-0000-0000-000000000005', 'sportsdataio', '202609061') $$,
  '23505',
  null,
  'a provider id already mapped to one game cannot be mapped to a second game'
);

-- Proof 2b: a game cannot have two different ids from the SAME provider.
select throws_ok(
  $$ insert into game_provider_ids (game_id, provider_name, provider_game_id)
     values ('d0000000-0000-0000-0000-000000000004', 'sportsdataio', '999999999') $$,
  '23505',
  null,
  'a game cannot be mapped to two different ids from the same provider'
);

-- Proof 3: 'mysportsfeeds' is a real, accepted provider_name value
-- (20260909190200_mysportsfeeds_game_provider_ids.sql) -- reuses the
-- second seed game (d0...005), which has no other mapping in this test.
insert into game_provider_ids (game_id, provider_name, provider_game_id) values
  ('d0000000-0000-0000-0000-000000000005', 'mysportsfeeds', 'gptest-msf-1');

select ok(
  (select count(*) = 1 from game_provider_ids
   where game_id = 'd0000000-0000-0000-0000-000000000005' and provider_name = 'mysportsfeeds'),
  'mysportsfeeds is an accepted game_provider_ids.provider_name value'
);

select * from finish();
rollback;
