-- Milestone 5.5 (Adaptive Agent Weighting), Decisions 1-27 (approved 2026-08-27).
--
-- V1 is PROPOSE-ONLY (Decision 2): this migration adds a persistence layer
-- for weighting EVALUATIONS/PROPOSALS. It never adds any mechanism that
-- writes agents.current_weight -- that remains a manual, future,
-- separately-authorized capability. No trigger, function, or column here
-- can mutate agents.current_weight; app code enforces the same boundary
-- (see app.orchestration.adaptive_weighting's own docstring).
--
-- Two additive, append-only tables, not one polymorphic table, matching
-- Milestone 5.4's own leg/product-grade-event split precedent:
--   1. adaptive_weight_proposals            -- one row per (agent, window, version)
--   2. adaptive_weight_proposal_observations -- normalized evidence rows,
--      never opaque JSON, per Decision 14's explicit instruction.
--
-- Idempotent-retry vs. legitimate-correction (Decision 22) uses the exact
-- same DB-enforced pattern as recommendation_leg_grade_events /
-- recommendation_product_grade_events: a partial unique index on
-- (agent_id, evaluation_window_start, evaluation_window_end,
-- weighting_version) WHERE is_correction = false.

-- ============================================================================
-- 1. Per-agent weighting evaluation/proposal (Decisions 1/4/5/6/8/9/10/13/14/19).
-- ============================================================================

create table adaptive_weight_proposals (
  id uuid primary key default uuid_generate_v7(),
  agent_id uuid not null references agents(id),
  previous_weight numeric not null,
  -- NULL only when sample_size = 0 -- no observations means no computable
  -- ROI/performance_delta, never a fabricated number (Decision 6's
  -- "never convert unavailable to zero/neutral/average" principle,
  -- extended here to the weighting calculation itself).
  raw_proposed_weight numeric,
  guardrail_adjusted_proposed_weight numeric,
  -- Always NULL in V1 (Decision 2/15) -- reserved for a future, separately
  -- authorized promotion mechanism. No code path in this migration or the
  -- application ever sets this column.
  applied_weight numeric,
  evaluation_window_start date not null,
  evaluation_window_end date not null,
  sample_size integer not null,
  roi numeric,
  committee_average_roi numeric,
  performance_delta numeric,
  -- Frozen at evaluation time (Decision 9/19's "historically traceable if
  -- the learning rate ever changes" requirement) -- never read live from a
  -- code constant at reconstruction time.
  learning_rate numeric not null,
  weighting_version text not null,
  status text not null check (status in ('proposed', 'rejected_insufficient_sample')),
  rejection_reason text,
  is_correction boolean not null default false,
  corrects_proposal_id uuid references adaptive_weight_proposals(id),
  created_at timestamptz not null default now(),
  check (is_correction = false or corrects_proposal_id is not null),
  check (raw_proposed_weight is not null or sample_size = 0)
);

create unique index idx_adaptive_weight_proposals_original_per_window
  on adaptive_weight_proposals (agent_id, evaluation_window_start, evaluation_window_end, weighting_version)
  where is_correction = false;

create index idx_adaptive_weight_proposals_agent on adaptive_weight_proposals (agent_id, evaluation_window_end desc);

create or replace function block_adaptive_weight_proposal_updates()
returns trigger as $$
begin
  raise exception 'adaptive_weight_proposals is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_adaptive_weight_proposal_update
  before update on adaptive_weight_proposals
  for each row execute function block_adaptive_weight_proposal_updates();

-- ============================================================================
-- 2. Normalized evidence rows (Decision 14: "enough provenance to
--    reproduce the evidence population... use normalized child/evidence
--    rows rather than hiding foreign-key relationships inside opaque
--    JSON"). One row per (proposal, graded leg) that actually counted.
-- ============================================================================

create table adaptive_weight_proposal_observations (
  id uuid primary key default uuid_generate_v7(),
  proposal_id uuid not null references adaptive_weight_proposals(id) on delete cascade,
  recommendation_leg_grade_event_id uuid not null references recommendation_leg_grade_events(id),
  classification text not null check (classification in ('correct', 'underperforming')),
  directional_lean text not null,
  notional_pnl numeric not null,
  created_at timestamptz not null default now(),
  unique (proposal_id, recommendation_leg_grade_event_id)
);

create index idx_adaptive_weight_proposal_observations_proposal on adaptive_weight_proposal_observations (proposal_id);

create or replace function block_adaptive_weight_proposal_observation_updates()
returns trigger as $$
begin
  raise exception 'adaptive_weight_proposal_observations is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_adaptive_weight_proposal_observation_update
  before update on adaptive_weight_proposal_observations
  for each row execute function block_adaptive_weight_proposal_observation_updates();

-- ============================================================================
-- RLS -- same "enabled, no select policy, service-role only" convention
-- already applied to every non-user-facing table in this schema.
-- ============================================================================

alter table adaptive_weight_proposals enable row level security;
alter table adaptive_weight_proposal_observations enable row level security;
