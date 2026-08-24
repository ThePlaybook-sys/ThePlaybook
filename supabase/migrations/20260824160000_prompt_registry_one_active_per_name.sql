-- Milestone 4.8 (Phase 4 Closeout Remediation), Prompt Version Determinism
-- decision (approved 2026-08-24): production must never silently choose
-- between multiple active prompt_registry rows for the same prompt_name.
--
-- Live dev data at migration time: exactly 2 rows (nfl_parlay_v1.0 v1,
-- nfl_single_v1.0 v1), each the only active row for its name -- this
-- constraint applies with zero conflicts against current data. The 12
-- canonical agent prompt rows seeded alongside this milestone are each
-- inserted with exactly one active version by construction, so no
-- conflict is expected there either.
--
-- Query-side "order by version desc limit 1" was explicitly rejected
-- (Mac's instruction) as insufficient on its own -- it would silently
-- paper over an invalid multi-active-row state instead of refusing it.
-- This partial unique index makes that state impossible to write in the
-- first place; app.persistence.model_config.resolve_active_prompt still
-- defensively raises PromptConfigError if more than one row is ever
-- returned, as defense in depth against this constraint being bypassed
-- (e.g. a migration not yet applied in some environment).
create unique index idx_prompt_registry_one_active_per_name
  on prompt_registry (prompt_name)
  where status = 'active';
