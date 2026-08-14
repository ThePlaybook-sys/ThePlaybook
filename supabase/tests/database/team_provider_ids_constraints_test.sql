-- Phase 3E-3 required test evidence, mirroring game_provider_ids_constraints_test.sql:
--   1. A SportsDataIO team abbreviation and a The Odds API team name can both
--      resolve to the SAME teams.id without creating a duplicate team.
--   2. A provider team id cannot silently map to two different teams.
-- Run via `supabase test db`, or manually inside a transaction that's rolled back --
-- same convention as the other database test files in this directory.

begin;
create extension if not exists pgtap with schema extensions;
select plan(4);

insert into leagues (id, sport_id, code, name)
values ('e0000000-0000-0000-0000-000000000001', (select id from sports where code = 'nfl' limit 1), 'nfl-tptest', 'NFL Test');
insert into teams (id, league_id, name) values
  ('e0000000-0000-0000-0000-000000000002', 'e0000000-0000-0000-0000-000000000001', 'Test Team Alpha'),
  ('e0000000-0000-0000-0000-000000000003', 'e0000000-0000-0000-0000-000000000001', 'Test Team Beta');

-- Proof 1: two different providers' team ids both resolve to the same teams.id.
insert into team_provider_ids (team_id, provider_name, provider_team_id) values
  ('e0000000-0000-0000-0000-000000000002', 'the_odds_api', 'tptest-alpha'),
  ('e0000000-0000-0000-0000-000000000002', 'sportsdataio', 'TPA');

select ok(
  (select count(distinct team_id) from team_provider_ids
   where provider_team_id in ('tptest-alpha', 'TPA')) = 1,
  'a the_odds_api team id and a sportsdataio team id both resolve to exactly one teams.id'
);
select ok(
  (select count(*) from teams where id not in
    ('e0000000-0000-0000-0000-000000000002', 'e0000000-0000-0000-0000-000000000003')) = 0,
  'no extra team was created by mapping two provider team ids to one team'
);

-- Proof 2a: the SAME provider team id cannot map to a DIFFERENT team.
select throws_ok(
  $$ insert into team_provider_ids (team_id, provider_name, provider_team_id)
     values ('e0000000-0000-0000-0000-000000000003', 'sportsdataio', 'TPA') $$,
  '23505',
  null,
  'a provider team id already mapped to one team cannot be mapped to a second team'
);

-- Proof 2b: a team cannot have two different ids from the SAME provider.
select throws_ok(
  $$ insert into team_provider_ids (team_id, provider_name, provider_team_id)
     values ('e0000000-0000-0000-0000-000000000002', 'sportsdataio', 'ZZZ') $$,
  '23505',
  null,
  'a team cannot be mapped to two different ids from the same provider'
);

select * from finish();
rollback;
