-- MSF Game Provider ID Enablement (2026-09-09): additive widening to
-- support MySportsFeeds as a real provider identity for GAME mapping,
-- exactly the same pattern already used for the_odds_api/sportsdataio/
-- balldontlie (see 20260907193000_balldontlie_provider_identity.sql,
-- Volume 3 §4.0's "adding a new vendor is a small follow-up migration").
--
-- `team_provider_ids`/`player_provider_ids` were already widened for
-- `mysportsfeeds` by 20260908150000_mysportsfeeds_provider_identity.sql;
-- `game_provider_ids` was not, leaving no schema-legal way to persist the
-- real, already-proven MSF game-ID mapping (Gate B preflight prerequisite,
-- 2026-09-09) until now. Every currently allowed value is preserved --
-- this is a pure addition, not a redesign of the provider taxonomy.
alter table game_provider_ids drop constraint game_provider_ids_provider_name_check;
alter table game_provider_ids add constraint game_provider_ids_provider_name_check
  check (provider_name = any (array['the_odds_api', 'sportsdataio', 'balldontlie', 'mysportsfeeds']));
