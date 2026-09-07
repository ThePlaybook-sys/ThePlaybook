-- Phase 8.0.5 Data Activation Pass 1 (2026-09-07): additive widening to
-- support BALLDONTLIE as a real provider identity for game/team mapping,
-- exactly the same pattern already used for the_odds_api/sportsdataio
-- ("adding a new vendor is a small follow-up migration", Volume 3 §4.0).
alter table game_provider_ids drop constraint game_provider_ids_provider_name_check;
alter table game_provider_ids add constraint game_provider_ids_provider_name_check
  check (provider_name = any (array['the_odds_api', 'sportsdataio', 'balldontlie']));

alter table team_provider_ids drop constraint team_provider_ids_provider_name_check;
alter table team_provider_ids add constraint team_provider_ids_provider_name_check
  check (provider_name = any (array['the_odds_api', 'sportsdataio', 'balldontlie']));
