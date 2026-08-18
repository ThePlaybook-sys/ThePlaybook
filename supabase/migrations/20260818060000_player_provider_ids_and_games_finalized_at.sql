-- Phase 3E-8: normalized player identity + game-finalization anchor (Volume 3 §4.0 addition)
--
-- Decision 1 (Mac, 2026-08-18, 3E-8 checkpoint, Option B): the same
-- single-vendor-assumption problem game_provider_ids (3E-1) and
-- team_provider_ids (3E-3) both fixed exists for players.external_provider_id
-- -- a single column with no way for a second vendor's own player
-- representation to coexist. SportsDataIO identifies players by a numeric
-- PlayerID; no second provider's player representation has been captured by
-- this project yet, but the table is built with the same two-provider check
-- constraint as game_provider_ids/team_provider_ids for consistency, not
-- because a second vendor's player id is known today.
--
-- Constraint design: identical pattern to game_provider_ids/team_provider_ids,
-- reused deliberately rather than re-derived --
--   unique(provider_name, provider_player_id) -- a provider's own player id
--     resolves to exactly one internal player; a provider id cannot silently
--     map to two different players.
--   unique(player_id, provider_name) -- a player has at most one id per provider.
--   FK players(id) on delete cascade -- mapping rows are meaningless without
--     their player.
--   provider_name constrained to the providers this codebase actually
--     integrates with today, matching game_provider_ids'/team_provider_ids'
--     own convention.

create table player_provider_ids (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references players(id) on delete cascade,
  provider_name text not null check (provider_name in ('the_odds_api', 'sportsdataio')),
  provider_player_id text not null,
  created_at timestamptz not null default now(),
  unique (provider_name, provider_player_id),
  unique (player_id, provider_name)
);

alter table player_provider_ids enable row level security;
create policy "public_read" on player_provider_ids for select using (true);

comment on column players.external_provider_id is
  'DEPRECATED 2026-08-18 (Phase 3E-8): superseded by player_provider_ids as the '
  'authoritative multi-provider player identity mechanism, mirroring '
  'game_provider_ids (Phase 3E-1) and team_provider_ids (Phase 3E-3). Never read '
  'by any existing code -- the players table itself was never populated before '
  'this phase, so there is no prior data to reconcile or backfill. Do not add '
  'further provider-specific columns to players; use player_provider_ids instead.';

-- Decision 2 (Postgame Ingestion Worker, game-final detection): a stable
-- anchor for "when did this game transition to final," distinct from
-- games.updated_at (which a Schedule re-poll can legitimately bump again
-- later for unrelated reasons -- e.g. a subsequent Master Refresh re-PATCHing
-- the same already-final row -- making it an unreliable proxy for the
-- original finalization moment). Nullable: only set once, the first time a
-- game's status is observed to transition into 'final'. This column, plus
-- the bounded reconciliation offsets in app.workers.reconciliation, is what
-- lets Postgame Worker compute "which reconciliation checkpoints are due"
-- as a pure function of elapsed time, without any other new persisted state.
alter table games add column if not exists finalized_at timestamptz;
comment on column games.finalized_at is
  'Set once (Phase 3E-8), the first time this game''s status is observed to '
  'transition to ''final''. Never recomputed afterward -- the anchor Postgame '
  'Worker''s bounded reconciliation schedule (app.workers.reconciliation) '
  'measures elapsed time against. Null for any game not yet final.';
