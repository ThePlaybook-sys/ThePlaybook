-- 2026-08-18: SportsDataIO team-identity verification round. A
-- single-purpose, single-endpoint live capture of
-- /v3/nfl/scores/json/Teams (the 11th call of the 12-call Free Trial
-- budget; the 12th/final call was intentionally not authorized) allowed a
-- deterministic reconciliation of all 32 current NFL teams against this
-- project's own `teams` table -- exact FullName-to-teams.name match, zero
-- fuzzy matching, zero conflicts (see
-- apps/sports-intel-layer/tests/fixtures/sportsdataio/PROVENANCE.md and
-- teams_active_normal.json for the full evidence trail).
--
-- Two outcomes from that reconciliation:
--   1. Dallas Cowboys ('DAL') and Philadelphia Eagles ('PHI') -- flagged
--      in 3E-4A as inferred-not-fixture-confirmed -- are now CONFIRMED
--      CORRECT. Their existing team_provider_ids rows (applied in the
--      3E-3 migration) are left as-is; this migration does not touch them.
--   2. The remaining 17 teams with zero prior SportsDataIO evidence now
--      have a live-confirmed abbreviation. This migration adds exactly
--      those 17 rows, taking sportsdataio coverage to 32/32.
--
-- the_odds_api coverage is untouched -- this round captured no Odds API
-- evidence.

insert into team_provider_ids (team_id, provider_name, provider_team_id)
select t.id, 'sportsdataio', mapping.abbrev
from (values
  ('Cincinnati Bengals', 'CIN'), ('Cleveland Browns', 'CLE'), ('Denver Broncos', 'DEN'),
  ('Detroit Lions', 'DET'), ('Green Bay Packers', 'GB'), ('Houston Texans', 'HOU'),
  ('Indianapolis Colts', 'IND'), ('Jacksonville Jaguars', 'JAX'), ('Las Vegas Raiders', 'LV'),
  ('Los Angeles Chargers', 'LAC'), ('Miami Dolphins', 'MIA'), ('Minnesota Vikings', 'MIN'),
  ('New York Giants', 'NYG'), ('New York Jets', 'NYJ'), ('Pittsburgh Steelers', 'PIT'),
  ('Tennessee Titans', 'TEN'), ('Washington Commanders', 'WAS')
) as mapping(team_name, abbrev)
join teams t on t.name = mapping.team_name
on conflict (provider_name, provider_team_id) do nothing;
