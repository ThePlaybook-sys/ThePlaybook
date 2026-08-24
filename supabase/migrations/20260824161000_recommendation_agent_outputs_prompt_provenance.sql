-- Milestone 4.8 (Phase 4 Closeout Remediation), Prompt Provenance decision
-- (approved 2026-08-24): recommendations.prompt_version cannot truthfully
-- represent independently-versioned per-agent prompts once prompt_registry
-- is wired in (Milestone 4.8 inspection finding) -- each agent's prompt_name
-- (= agent_name) and prompt_version now become the canonical, queryable,
-- per-output Time Machine provenance, frozen at the moment each output is
-- persisted, exactly parallel to weight_applied. recommendations.prompt_version
-- remains in place, unchanged, but is documented as legacy/non-authoritative
-- for per-agent reconstruction (Volume 3 update accompanies this migration).
--
-- Nullable and backward-compatible: the 3 existing (Phase-1 seed fixture)
-- recommendation_agent_outputs rows get NULL for both new columns and are
-- untouched by this migration.
--
-- Composite FK to prompt_registry(prompt_name, version) -- operationally
-- safe today, reported before applying per Mac's explicit instruction:
--   * Nullable + MATCH SIMPLE (Postgres default): a row with either new
--     column NULL is never checked against the FK at all, so the 3 existing
--     legacy rows are unaffected.
--   * prompt_registry rows are never deleted by any code path in this
--     codebase (deprecation is a status UPDATE to 'deprecated', matching
--     the existing trg_prompt_registry_audit trigger which fires on
--     INSERT/UPDATE only) -- confirmed via full-codebase grep, zero DELETE
--     statements against prompt_registry exist anywhere.
--   * Caveat, reported honestly: unlike odds_snapshots/team_stats/
--     player_stats, prompt_registry has no DB-level trigger physically
--     preventing a future DELETE -- "never deleted" is a codebase
--     convention today, not a database-enforced guarantee. The FK is
--     judged safe under current code and data; if a future milestone adds
--     a delete/cleanup path for prompt_registry, this FK will correctly
--     force that decision to be made explicitly (ON DELETE behavior)
--     rather than silently orphaning historical provenance.
alter table recommendation_agent_outputs
  add column prompt_name text,
  add column prompt_version integer,
  add constraint fk_recommendation_agent_outputs_prompt
    foreign key (prompt_name, prompt_version)
    references prompt_registry (prompt_name, version);

create index idx_recommendation_agent_outputs_prompt
  on recommendation_agent_outputs (prompt_name, prompt_version)
  where prompt_name is not null;
