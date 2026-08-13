-- Phase 3E-1 follow-up: games.external_provider_id must become nullable.
--
-- Surfaced while building Schedule ingestion (Decision 2, 2026-08-13): a new games row
-- created from a SportsDataIO Schedule entry has no meaningful value for this column --
-- it was never SportsDataIO's id, only ever The Odds API's, and Decision 2's whole point
-- is that a game's provider ids now live in game_provider_ids, not this one column. With
-- the NOT NULL constraint still in place, the very capability Decision 2 approved (a
-- non-the_odds_api source creating a game) would be blocked at the database level.
--
-- This is exactly the "blueprint vs reality" gap CLAUDE.md's process calls for flagging,
-- not silently working around: reported to Mac in the 3E-1 completion report as an
-- architectural conflict that surfaced during implementation. The fix is a pure constraint
-- relaxation (nullable is strictly weaker than not null, so nothing that satisfied the
-- column before stops satisfying it now) -- no data changes, no application code depends
-- on this column being non-null (odds_snapshots.py and schedule.py both now resolve games
-- through game_provider_ids instead).

alter table games alter column external_provider_id drop not null;

comment on column games.external_provider_id is
  'DEPRECATED 2026-08-13 (Decision 2): superseded by game_provider_ids as the authoritative '
  'multi-provider identity mechanism. Made nullable in this follow-up migration because new '
  'games created by a non-the_odds_api Schedule source (e.g. sportsdataio) have no meaningful '
  'value for it. Retained read-only for pre-3E-1 rows -- new code resolves games through '
  'game_provider_ids, not this column. Do not add further provider-specific columns to '
  'games; use game_provider_ids instead.';
