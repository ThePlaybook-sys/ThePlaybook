-- Sunday Ingestion Foundation Build (2026-09-11, HQ-authorized): MSF
-- team identity support. Applies the minimal widening designed (not
-- applied) across three prior passes -- the Sunday ingestion design's
-- Section 4, reconfirmed load-bearing in the preflight correction, and
-- named again as the SF/LAR blocker in the F2 preparation pass. Real
-- justification, not speculative: MySportsFeeds uses two legitimately
-- different identifier schemes across its own endpoints for the same
-- team -- abbreviation strings (from players.json/lineup.json, e.g.
-- "NE", "SEA", already backfilled for 12 teams) and numeric ids (from
-- the schedule/game_boxscore feeds, e.g. 50, 79 -- all 32 real values
-- already recovered and persisted as raw evidence in the MSF Week 1
-- Identity Recovery pass, backfilled below). The existing
-- unique(team_id, provider_name) constraint allows only one row per
-- team per provider, which cannot hold both schemes for the same team
-- at once.
--
-- Widening, exactly as scoped -- preserve one thing, allow another:
--   PRESERVED: unique(provider_name, provider_team_id) -- a given
--     provider's own identifier (abbreviation OR numeric) still
--     resolves to exactly one team; this is the collision guard that
--     matters and is untouched by this migration.
--   WIDENED: unique(team_id, provider_name) -> unique(team_id,
--     provider_name, provider_team_id) -- a team may now legitimately
--     hold multiple identifiers from the same provider (one
--     abbreviation row, one numeric row), but never a duplicate of the
--     exact same (team, provider, identifier) triple.
--
-- No other provider is affected in practice -- every existing
-- the_odds_api/sportsdataio/balldontlie row already had at most one
-- identifier per team per provider before this migration, so the wider
-- constraint is satisfied by 100% of existing data with no backfill
-- required for those rows.
alter table team_provider_ids
  drop constraint team_provider_ids_team_id_provider_name_key;

alter table team_provider_ids
  add constraint team_provider_ids_team_id_provider_name_provider_team_id_key
  unique (team_id, provider_name, provider_team_id);

comment on constraint team_provider_ids_provider_name_provider_team_id_key
  on team_provider_ids is
  'A given provider''s own identifier resolves to exactly one team -- '
  'unchanged by the 2026-09-11 multi-identifier widening.';
