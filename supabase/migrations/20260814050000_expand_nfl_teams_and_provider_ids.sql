-- Phase 3E-4A: expand the canonical NFL team set to all 32 current teams,
-- and extend team_provider_ids coverage to every provider identifier this
-- repository's own fixtures actually confirm.
--
-- `teams.name` is NOT provider-specific data -- it is the same public,
-- standard NFL naming already relied on throughout this project (the
-- original 6 seed teams). Mac's explicit "do not fabricate provider
-- identifiers" instruction governs `team_provider_ids` rows specifically,
-- not this internal canonical-name column.
--
-- `team_provider_ids` coverage added here is limited to exactly what a
-- direct grep of every fixture file in
-- tests/fixtures/{sportsdataio,the_odds_api}/ confirms (verified before
-- writing this migration, not assumed):
--   sportsdataio: ARI, ATL, BAL, BUF, CAR, CHI, KC, LAR, NE, NO, SEA, SF, TB
--     (13 teams -- every distinct Team/HomeTeam/AwayTeam value across
--     schedules_normal.json, rosters_normal.json, depth_charts_normal.json,
--     team_stats_week_bulk_normal.json, player_stats_week_bulk_normal.json,
--     injuries_normal.json)
--   the_odds_api: BAL, BUF, DAL, KC, PHI, SF (6 teams -- every distinct
--     home_team/away_team value across every non-error/non-malformed
--     fixture in tests/fixtures/the_odds_api/)
--
-- Of the 13 sportsdataio-confirmed teams, BAL/BUF/KC/SF already have a
-- sportsdataio mapping from Phase 3E-3 -- this migration adds the
-- remaining 9 (ARI, ATL, CAR, CHI, LAR, NE, NO, SEA, TB).
--
-- 19 teams have zero SportsDataIO fixture evidence; 26 teams have zero
-- The Odds API fixture evidence -- both reported to Mac as unverified
-- rather than filled in from general knowledge, per his explicit
-- instruction not to fabricate provider identifiers.

insert into teams (league_id, name)
select (select id from leagues where code = 'nfl' limit 1), name
from (values
  ('Arizona Cardinals'), ('Atlanta Falcons'), ('Carolina Panthers'), ('Chicago Bears'),
  ('Cincinnati Bengals'), ('Cleveland Browns'), ('Denver Broncos'), ('Detroit Lions'),
  ('Green Bay Packers'), ('Houston Texans'), ('Indianapolis Colts'), ('Jacksonville Jaguars'),
  ('Las Vegas Raiders'), ('Los Angeles Chargers'), ('Los Angeles Rams'), ('Miami Dolphins'),
  ('Minnesota Vikings'), ('New England Patriots'), ('New Orleans Saints'), ('New York Giants'),
  ('New York Jets'), ('Pittsburgh Steelers'), ('Seattle Seahawks'), ('Tampa Bay Buccaneers'),
  ('Tennessee Titans'), ('Washington Commanders')
) as new_teams(name)
where not exists (select 1 from teams t where t.name = new_teams.name);

insert into team_provider_ids (team_id, provider_name, provider_team_id)
select t.id, 'sportsdataio', mapping.abbrev
from (values
  ('Arizona Cardinals', 'ARI'), ('Atlanta Falcons', 'ATL'), ('Carolina Panthers', 'CAR'),
  ('Chicago Bears', 'CHI'), ('Los Angeles Rams', 'LAR'), ('New England Patriots', 'NE'),
  ('New Orleans Saints', 'NO'), ('Seattle Seahawks', 'SEA'), ('Tampa Bay Buccaneers', 'TB')
) as mapping(team_name, abbrev)
join teams t on t.name = mapping.team_name
on conflict (provider_name, provider_team_id) do nothing;
