-- Phase 8.2 Player/Roster/Depth Activation (2026-09-08): additive widening
-- to support MySportsFeeds as a real provider identity for team/player
-- mapping, same pattern already used for balldontlie (see
-- 20260907193000_balldontlie_provider_identity.sql). Schema-only --
-- real identity rows (team_provider_ids for NE/SEA, player_provider_ids
-- for the activated roster) are inserted separately via direct SQL, not
-- this migration, matching this project's own established "schema via
-- migration, real data via execute_sql" convention.
alter table team_provider_ids drop constraint team_provider_ids_provider_name_check;
alter table team_provider_ids add constraint team_provider_ids_provider_name_check
  check (provider_name = any (array['the_odds_api', 'sportsdataio', 'balldontlie', 'mysportsfeeds']));

alter table player_provider_ids drop constraint player_provider_ids_provider_name_check;
alter table player_provider_ids add constraint player_provider_ids_provider_name_check
  check (provider_name = any (array['the_odds_api', 'sportsdataio', 'mysportsfeeds']));
