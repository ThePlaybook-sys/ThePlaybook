-- Milestone 4.6, Decision G (approved 2026-08-22): candidate_key makes
-- candidate identity a first-class, queryable part of a
-- recommendation_agent_outputs row, instead of existing only inside
-- raw_output JSON. Nullable and backward-compatible: existing
-- game-level fan-out outputs (Milestones 4.4/4.5) stay NULL; only the
-- sequential decision chain's candidate-level outputs populate it.
--
-- No uniqueness constraint: multiple evaluations of the same candidate
-- may legitimately exist over time (retry/versioning semantics are not
-- yet designed strongly enough to justify enforcing uniqueness at the
-- DB level). Indexed (recommendation_id, candidate_key) for the
-- expected Phase 5 lookup pattern -- "every candidate evaluated within
-- this recommendation cycle" / "this candidate's history within this
-- cycle" -- via a partial index (candidate_key is not null) so
-- non-candidate rows never pollute it.
alter table recommendation_agent_outputs add column candidate_key text;
create index idx_recommendation_agent_outputs_candidate_key on recommendation_agent_outputs(recommendation_id, candidate_key) where candidate_key is not null;
