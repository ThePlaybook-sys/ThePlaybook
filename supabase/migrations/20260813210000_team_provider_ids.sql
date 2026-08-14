-- Phase 3E-3: cross-provider team identity (Volume 3 §4.0 addition)
--
-- Decision (Mac, 2026-08-13, 3E-3 checkpoint): the same problem Decision 2
-- solved for games.external_provider_id exists for teams.external_provider_id --
-- a single column with no way for a second vendor's own team representation to
-- coexist. SportsDataIO identifies teams by abbreviation ("KC", "SEA", "NE");
-- The Odds API identifies them by full name ("Kansas City Chiefs", "Seattle
-- Seahawks", "New England Patriots") -- confirmed directly from this project's
-- own already-captured fixtures, not assumed. Unlike games.external_provider_id
-- before 3E-1, no code anywhere in this codebase currently reads
-- teams.external_provider_id at all (grepped before writing this migration),
-- and the column was already nullable from its original Phase 1 migration --
-- so there is no NOT NULL conflict to fix here the way there was for games.
--
-- Constraint design: identical pattern to game_provider_ids (Phase 3E-1),
-- reused deliberately rather than re-derived --
--   unique(provider_name, provider_team_id) -- a provider's own team id
--     resolves to exactly one internal team; a provider id cannot silently
--     map to two different teams.
--   unique(team_id, provider_name) -- a team has at most one id per provider.
--   FK teams(id) on delete cascade -- mapping rows are meaningless without
--     their team.
--   provider_name constrained to the providers this codebase actually
--     integrates with today, matching game_provider_ids' own convention.
--   Both unique constraints create their own covering index -- no separate
--     index required, same reasoning as game_provider_ids.

create table team_provider_ids (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references teams(id) on delete cascade,
  provider_name text not null check (provider_name in ('the_odds_api', 'sportsdataio')),
  provider_team_id text not null,
  created_at timestamptz not null default now(),
  unique (provider_name, provider_team_id),
  unique (team_id, provider_name)
);

alter table team_provider_ids enable row level security;
create policy "public_read" on team_provider_ids for select using (true);

comment on column teams.external_provider_id is
  'DEPRECATED 2026-08-13 (Phase 3E-3): superseded by team_provider_ids as the '
  'authoritative multi-provider team identity mechanism, mirroring '
  'game_provider_ids (Decision 2, Phase 3E-1). Unlike games.external_provider_id, '
  'this column was already nullable and is not read by any existing code -- not '
  'backfilled, since its current seed values are synthetic placeholders '
  '("seed-kc" etc.), not real provider ids for any actual vendor. Do not add '
  'further provider-specific columns to teams; use team_provider_ids instead.';
