-- Phase 3E-3 follow-up: backfill team_provider_ids for the teams already
-- seeded in dev, using genuinely correct provider representations (public,
-- standard NFL abbreviations/names) rather than preserving teams.external_provider_id's
-- synthetic seed values ("seed-kc" etc.), which are not real provider ids for
-- any actual vendor and are not a safe backfill source (unlike games.external_provider_id
-- in Phase 3E-1, which held a real The Odds API-shaped id worth preserving).
--
-- the_odds_api's provider_team_id is the team's full name -- confirmed directly
-- from this project's own already-captured fixture
-- (tests/fixtures/the_odds_api/bulk_odds_multi_game.json: "home_team": "Kansas
-- City Chiefs"), which happens to already match teams.name verbatim for these
-- six teams. sportsdataio's provider_team_id is the standard team abbreviation,
-- confirmed from tests/fixtures/sportsdataio/rosters_normal.json's "Team": "KC".
-- Both are public, standard NFL naming facts, not vendor-specific data requiring
-- a live provider call to confirm.

-- on conflict do nothing: makes this migration safe to record against a
-- database where the same backfill was already applied by hand (this
-- project's own dev history) without erroring on the unique constraints.
insert into team_provider_ids (team_id, provider_name, provider_team_id)
select id, 'the_odds_api', name from teams
on conflict (provider_name, provider_team_id) do nothing;

insert into team_provider_ids (team_id, provider_name, provider_team_id)
select id, 'sportsdataio', case name
  when 'Kansas City Chiefs' then 'KC'
  when 'Buffalo Bills' then 'BUF'
  when 'San Francisco 49ers' then 'SF'
  when 'Philadelphia Eagles' then 'PHI'
  when 'Dallas Cowboys' then 'DAL'
  when 'Baltimore Ravens' then 'BAL'
end
from teams
on conflict (provider_name, provider_team_id) do nothing;
