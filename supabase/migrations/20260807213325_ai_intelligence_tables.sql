-- Phase 1, Milestone 3: AI intelligence tables (Volume 3 §5 only).
-- feature_flags/prompt_registry/model_registry/recommendation_costs/audit_log live in §8 and
-- belong to Milestone 4, despite being labeled a "v2.0 addition" in the roadmap's Phase 1 blurb.
--
-- RLS: `recommendations` gets the exact tier-gated select policy §10 already specifies verbatim,
-- combined with the soft-delete filter §10 explicitly names `recommendations` under. The other
-- six tables here (agents, agent_performance_scores, recommendation_agent_outputs,
-- consensus_snapshots, explainability_payloads, recommendation_snapshots) get RLS enabled with
-- NO select policy — default-deny for anon/authenticated, service role bypasses as always.
-- Unlike §4's public sports data, nothing in Volume 2 indicates these are read directly by the
-- frontend via Realtime; they're consumed through the API Gateway, which uses the service role.
-- Flagged as a decision, not settled blueprint text — see PROGRESS.md.

create table agents (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  category text,
  active boolean default true,
  current_weight numeric(5,4) default 1.0,
  created_at timestamptz default now()
);

create table agent_performance_scores (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references agents(id),
  evaluation_window_start date not null,
  evaluation_window_end date not null,
  roi numeric(8,4),
  ev numeric(8,4),
  clv numeric(8,4),
  confidence_calibration_score numeric(5,4),
  sample_size integer not null,
  created_at timestamptz default now()
);
create index idx_agent_perf_agent_window on agent_performance_scores(agent_id, evaluation_window_end desc);

create table recommendations (
  id uuid primary key default gen_random_uuid(),
  game_id uuid references games(id),
  user_facing boolean default true,
  recommendation_type text check (recommendation_type in
    ('single','player_prop','same_game_parlay','multi_game_parlay','multiple_singles','no_bet')),
  bet_details jsonb,
  confidence_score numeric(5,4),
  expected_value numeric(8,4),
  risk_level text check (risk_level in ('low','moderate','high')),
  status text check (status in ('active','withdrawn','settled_win','settled_loss','settled_push')),
  min_required_tier text default 'free',
  ai_version text not null default 'v1',
  prompt_version text,
  agent_version text,
  consensus_version text,
  weight_version text,
  deleted_at timestamptz,
  display_id text unique,
  created_at timestamptz default now(),
  withdrawn_at timestamptz,
  withdrawal_reason text
);
create index idx_recs_game on recommendations(game_id);
create index idx_recs_status on recommendations(status) where status = 'active';
create index idx_recs_created on recommendations(created_at desc);

-- UUIDv7 per the v2.0 amendment (CHANGELOG v4.1.1) — uuid_generate_v7() defined in the prior migration.
create table recommendation_agent_outputs (
  id uuid primary key default uuid_generate_v7(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  agent_id uuid not null references agents(id),
  raw_output jsonb not null,
  agent_confidence numeric(5,4),
  weight_applied numeric(5,4) not null,
  created_at timestamptz default now()
);
create index idx_rao_recommendation on recommendation_agent_outputs(recommendation_id);

create table consensus_snapshots (
  id uuid primary key default gen_random_uuid(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  aggregate_confidence numeric(5,4) not null,
  agreement_variance numeric(5,4),
  model_routing_used jsonb,
  second_pass_triggered boolean default false,
  created_at timestamptz default now()
);

create table explainability_payloads (
  id uuid primary key default gen_random_uuid(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  why_this_recommendation text,
  why_this_bet_type text,
  why_now text,
  why_not_alternatives text,
  strongest_evidence text,
  biggest_risks text,
  invalidating_conditions text,
  contributing_agents uuid[],
  persona_fit_explanation text,
  created_at timestamptz default now()
);

create table recommendation_snapshots (
  recommendation_id uuid primary key references recommendations(id) on delete cascade,
  full_environment_snapshot jsonb not null,
  agent_outputs_snapshot jsonb not null,
  consensus_snapshot jsonb not null,
  created_at timestamptz default now()
);

-- ============================================================================
-- Append-only enforcement (Volume 3 §11, exact names as specified)
-- ============================================================================

create or replace function block_agent_output_updates()
returns trigger as $$
begin
  raise exception 'recommendation_agent_outputs is append-only and cannot be modified';
end;
$$ language plpgsql;

create trigger trg_block_rao_update
  before update on recommendation_agent_outputs
  for each row execute function block_agent_output_updates();

-- ============================================================================
-- Row Level Security
-- ============================================================================

alter table recommendations enable row level security;
create policy "recommendations_tier_gated_select" on recommendations
  for select using (
    deleted_at is null
    and (
      min_required_tier = 'free'
      or exists (
        select 1 from subscriptions s
        where s.user_id = auth.uid()
          and s.status = 'active'
          and (
            (min_required_tier = 'pro' and s.tier in ('pro','elite','syndicate'))
            or (min_required_tier = 'elite' and s.tier in ('elite','syndicate'))
          )
      )
    )
  );

alter table agents enable row level security;
alter table agent_performance_scores enable row level security;
alter table recommendation_agent_outputs enable row level security;
alter table consensus_snapshots enable row level security;
alter table explainability_payloads enable row level security;
alter table recommendation_snapshots enable row level security;
-- No select policy on the six tables above: RLS enabled with zero policies means anon/
-- authenticated get zero rows by default; the service role (API Gateway, Orchestrator,
-- background workers) bypasses RLS entirely, per §10's existing service-role principle.
