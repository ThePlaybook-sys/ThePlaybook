-- Phase 3E-1: cross-provider game identity + season/week context (Volume 3 §4.0 additions)
--
-- Decision 2 (Mac, 2026-08-13): games.external_provider_id was a hidden single-vendor
-- assumption -- app/persistence/odds_snapshots.py resolved every game by matching this
-- one column against The Odds API's event id, with no way for a second vendor (e.g.
-- SportsDataIO's GameKey) to ever coexist. game_provider_ids replaces that: one internal
-- game can now carry many (provider_name, provider_game_id) pairs. games.external_provider_id
-- is deprecated (see column comment below), not dropped -- Mac's instruction was not to
-- silently delete it until proven safe.
--
-- Constraint design (evaluated per Mac's explicit checklist):
--   unique(provider_name, provider_game_id) -- a given vendor's id can resolve to exactly
--     one games row; this is what makes "provider id can't silently map to two different
--     games" true at the database level, not just in application code.
--   unique(game_id, provider_name) -- a game has at most one id per provider (a second
--     mapping attempt for the same provider must update, not duplicate).
--   FK games(id) on delete cascade -- mapping rows are meaningless without their game.
--   provider_name is constrained to the providers this codebase actually integrates
--     with today (the_odds_api, sportsdataio); extending to a new vendor is a follow-up
--     migration, matching the existing convention for games.status's own check-in list.
--   Both unique constraints create their own covering index in Postgres, which is exactly
--     the pair of lookup paths this table needs (by game_id -> all that game's provider
--     ids; by provider_name+provider_game_id -> the one game) -- no separate index required.
--
-- Decision 1 (Mac, 2026-08-13): games.season_type/week. Checked first for an existing
-- internal season-phase vocabulary anywhere in the codebase or Blueprint -- there is none;
-- the only existing occurrences of season-phase data are SportsDataIO's own raw numeric
-- `SeasonType` field (1/2/3) inside fixture JSON, never persisted or normalized anywhere.
-- So this migration establishes the first internal vocabulary (preseason/regular/postseason)
-- rather than adopting SportsDataIO's. Both columns are nullable: season_type because not
-- every future sport/provider will supply it, week because it's an NFL-specific concept
-- (mirroring the player_stats_nfl extension-table precedent of not forcing one sport's shape
-- onto a shared table).

create table game_provider_ids (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  provider_name text not null check (provider_name in ('the_odds_api', 'sportsdataio')),
  provider_game_id text not null,
  created_at timestamptz not null default now(),
  unique (provider_name, provider_game_id),
  unique (game_id, provider_name)
);

alter table game_provider_ids enable row level security;
create policy "public_read" on game_provider_ids for select using (true);

-- Backfill: preserve odds_snapshots.py's existing resolution behavior exactly. Every
-- existing games.external_provider_id was, and until this migration's follow-up code
-- change still is, treated as a The Odds API event id by that module. This makes that
-- assumption an explicit, queryable row instead of a hidden column convention -- no
-- games are duplicated or renumbered, this only adds mapping rows.
insert into game_provider_ids (game_id, provider_name, provider_game_id)
select id, 'the_odds_api', external_provider_id
from games
where external_provider_id is not null;

comment on column games.external_provider_id is
  'DEPRECATED 2026-08-13 (Decision 2): superseded by game_provider_ids as the authoritative '
  'multi-provider identity mechanism. Retained read-only during the 3E-1 transition -- new '
  'code resolves games through game_provider_ids, not this column. Do not add further '
  'provider-specific columns to games; use game_provider_ids instead.';

alter table games
  add column season_type text check (season_type in ('preseason', 'regular', 'postseason')),
  add column week integer;

comment on column games.season_type is
  'Normalized internal vocabulary (preseason/regular/postseason) -- deliberately not any '
  'single provider''s raw terminology (e.g. SportsDataIO''s numeric 1/2/3 SeasonType). '
  'Nullable: not every sport/provider supplies a season phase.';
comment on column games.week is
  'NFL week number (1-18 regular season plus playoff weeks) at launch. Nullable for sports '
  'or contexts that do not use week numbering.';
