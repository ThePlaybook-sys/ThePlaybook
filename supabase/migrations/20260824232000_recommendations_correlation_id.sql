-- Milestone 4.9 (Recommendation Worker), Idempotency decision (approved
-- 2026-08-24): the durable retry marker for one Recommendation Worker
-- execution against one game. Deliberately NOT unique on game_id alone
-- -- the same game must be allowed multiple legitimate analysis cycles
-- over time (a later Master Refresh run re-analyzing the same game is a
-- new cycle, not a duplicate).
--
-- Nullable and backward-compatible: every existing recommendations row
-- (Milestones 4.5-4.8, all created before correlation_id existed) gets
-- NULL here and remains valid, queryable history.
-- The `unique` constraint already creates its own index (Postgres unique
-- constraints treat NULL as distinct from every other NULL, so any
-- number of NULL/historical rows coexist without conflict) -- no
-- separate index needed for the lookup this column exists to serve.
alter table recommendations
  add column correlation_id text unique;
