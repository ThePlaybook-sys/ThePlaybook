-- Milestone 4.7, Decision H (approved 2026-08-22): candidate_key mirrors
-- the recommendation_agent_outputs pattern (Milestone 4.6, Decision G)
-- exactly -- makes candidate identity first-class and queryable, never
-- buried inside model_routing_used. No uniqueness constraint, same
-- reasoning: retry/versioning semantics for a candidate-level consensus
-- snapshot aren't designed yet either.
--
-- final_aggregate_confidence is distinct from aggregate_confidence --
-- the post-Meta-Agent/Elite-reconciliation-adjustment number, never
-- collapsed into the single pre-adjustment column that already existed.
--
-- below_confidence_floor is the internal Phase-4 0.55 threshold result
-- as a raw fact -- explicitly NOT a Phase-5 recommendation_type='no_bet'
-- decision.
--
-- participation_metadata preserves the full configured/built/deferred/
-- attempted/successful/failed/fan_out_status/committee_completeness
-- breakdown for this specific historical run -- required because a
-- failed or deferred agent leaves NO row at all in
-- recommendation_agent_outputs, so this is the only durable record of
-- what was actually attempted at consensus time. Lets a future reader
-- distinguish "0.71 confidence from 17/17 available agents" from
-- "0.71 confidence while only 6/17 intended agents existed."
alter table consensus_snapshots add column candidate_key text;
alter table consensus_snapshots add column final_aggregate_confidence numeric;
alter table consensus_snapshots add column below_confidence_floor boolean;
alter table consensus_snapshots add column participation_metadata jsonb;
create index idx_consensus_snapshots_candidate_key on consensus_snapshots(recommendation_id, candidate_key) where candidate_key is not null;
