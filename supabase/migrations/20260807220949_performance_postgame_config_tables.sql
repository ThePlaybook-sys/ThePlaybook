-- Phase 1, Milestone 4: performance attribution, postgame review, market monitoring, and AI
-- orchestration config tables (Volume 3 §6-§8), including the v2.0 tables that actually belong
-- here (feature_flags, prompt_registry, model_registry, recommendation_costs, audit_log — §8,
-- not §5, despite being labeled a general "v2.0 addition" in the roadmap's Phase 1 blurb).
--
-- RLS, decided per-table, not inherited from Milestone 3's default:
--   bet_slips, verified_bets, projected_user_performance, verified_user_performance:
--     auth.uid() = user_id — §10 names these explicitly in its user-data RLS list.
--   feature_flags: public-read — §4's text explicitly says this table is "consumed by...
--     the frontend (beta dashboard features)," unlike anything said about Milestone 3's
--     internal tables. The one table here that does NOT default-deny.
--   ai_performance, postgame_reviews, market_monitoring_events, model_routing_rules,
--   prompt_registry, model_registry, recommendation_costs, audit_log:
--     RLS enabled, no select policy — default-deny for anon/authenticated, service role
--     bypasses. No blueprint text indicates direct frontend/Realtime access to any of these.
--
-- market_monitoring_events uses uuid_generate_v7() per the v2.0 amendment (same function as
-- odds_snapshots and recommendation_agent_outputs; see CHANGELOG v4.1.1).

create table bet_slips (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  image_storage_path text,
  ocr_extracted_data jsonb,
  linked_recommendation_id uuid references recommendations(id),
  created_at timestamptz default now()
);

create table verified_bets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  bet_slip_id uuid references bet_slips(id),
  recommendation_id uuid references recommendations(id),
  stake numeric(10,2),
  odds numeric(8,2),
  outcome text check (outcome in ('win','loss','push','pending')),
  payout numeric(10,2),
  created_at timestamptz default now()
);

create table ai_performance (
  id uuid primary key default gen_random_uuid(),
  evaluation_window_start date,
  evaluation_window_end date,
  roi numeric(8,4), ev numeric(8,4), clv numeric(8,4), units numeric(10,2),
  sport text, bet_type text,
  created_at timestamptz default now()
);

create table projected_user_performance (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  recommendation_id uuid not null references recommendations(id),
  projected_units numeric(10,4) not null,
  created_at timestamptz default now()
);

create table verified_user_performance (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  verified_bet_id uuid not null references verified_bets(id),
  actual_units numeric(10,4) not null,
  created_at timestamptz default now()
);

create table postgame_reviews (
  id uuid primary key default gen_random_uuid(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  outcome_summary text,
  why_it_won_or_lost text,
  weather_impact_assessment text,
  injury_impact_assessment text,
  line_movement_impact_assessment text,
  correct_agents uuid[],
  underperforming_agents uuid[],
  learning_notes text,
  created_at timestamptz default now()
);

create table market_monitoring_events (
  id uuid primary key default uuid_generate_v7(),
  game_id uuid not null references games(id),
  event_type text check (event_type in
    ('line_movement','injury_update','weather_change','lineup_change','breaking_news')),
  event_data jsonb,
  affected_recommendation_ids uuid[],
  action_taken text check (action_taken in ('none','updated','withdrawn')),
  created_at timestamptz default now()
);
create index idx_mme_game on market_monitoring_events(game_id);

create table model_routing_rules (
  id uuid primary key default gen_random_uuid(),
  task_type text not null,
  primary_model text not null,
  fallback_model text,
  min_tier_for_second_pass text default 'elite',
  active boolean default true,
  updated_at timestamptz default now()
);

create table prompt_registry (
  id uuid primary key default gen_random_uuid(),
  prompt_name text not null,
  version integer not null,
  prompt_text text not null,
  status text check (status in ('draft','active','deprecated')),
  owner text,
  updated_at timestamptz default now(),
  unique(prompt_name, version)
);

create table model_registry (
  id uuid primary key default gen_random_uuid(),
  model_name text not null unique,
  strengths text,
  weaknesses text,
  cost_per_1k_tokens numeric(10,6),
  avg_latency_ms integer,
  preferred_tasks text[],
  capabilities text[],
  status text check (status in ('active','retired')),
  updated_at timestamptz default now()
);

create table feature_flags (
  id uuid primary key default gen_random_uuid(),
  flag_key text not null unique,
  description text,
  enabled boolean default false,
  audience_tier text[],
  rollout_percentage integer default 0 check (rollout_percentage between 0 and 100),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table recommendation_costs (
  id uuid primary key default gen_random_uuid(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  provider text check (provider in ('openai','anthropic','ocr','sports_api')),
  cost_usd numeric(10,6),
  created_at timestamptz default now()
);
create index idx_reccosts_recommendation on recommendation_costs(recommendation_id);

create table audit_log (
  id uuid primary key default gen_random_uuid(),
  actor text,
  action_type text check (action_type in
    ('prompt_change','weight_change','routing_change','model_swap',
     'consensus_change','admin_action','feature_flag_change')),
  target_id uuid,
  before_state jsonb,
  after_state jsonb,
  created_at timestamptz default now()
);

-- ============================================================================
-- Triggers
-- ============================================================================

create trigger trg_model_routing_rules_updated
  before update on model_routing_rules
  for each row execute function set_updated_at();
create trigger trg_prompt_registry_updated
  before update on prompt_registry
  for each row execute function set_updated_at();
create trigger trg_model_registry_updated
  before update on model_registry
  for each row execute function set_updated_at();
create trigger trg_feature_flags_updated
  before update on feature_flags
  for each row execute function set_updated_at();

-- v2.0: auto-populate audit_log on writes to system-config tables (§11, exact spec)
create or replace function log_config_change()
returns trigger as $$
begin
  insert into audit_log (actor, action_type, target_id, before_state, after_state)
  values (
    coalesce(current_setting('request.jwt.claim.sub', true), 'system'),
    case TG_TABLE_NAME
      when 'prompt_registry' then 'prompt_change'
      when 'agents' then 'weight_change'
      when 'model_routing_rules' then 'routing_change'
      when 'feature_flags' then 'feature_flag_change'
    end,
    coalesce(new.id, old.id),
    to_jsonb(old),
    to_jsonb(new)
  );
  return new;
end;
$$ language plpgsql;

create trigger trg_prompt_registry_audit
  after insert or update on prompt_registry
  for each row execute function log_config_change();
create trigger trg_agents_audit
  after insert or update on agents
  for each row execute function log_config_change();
create trigger trg_model_routing_rules_audit
  after insert or update on model_routing_rules
  for each row execute function log_config_change();
create trigger trg_feature_flags_audit
  after insert or update on feature_flags
  for each row execute function log_config_change();

-- ============================================================================
-- Row Level Security
-- ============================================================================

alter table bet_slips enable row level security;
create policy "own_bet_slips_select" on bet_slips
  for select using (auth.uid() = user_id);

alter table verified_bets enable row level security;
create policy "own_verified_bets_select" on verified_bets
  for select using (auth.uid() = user_id);

alter table projected_user_performance enable row level security;
create policy "own_projected_performance_select" on projected_user_performance
  for select using (auth.uid() = user_id);

alter table verified_user_performance enable row level security;
create policy "own_verified_performance_select" on verified_user_performance
  for select using (auth.uid() = user_id);

alter table feature_flags enable row level security;
create policy "public_read" on feature_flags for select using (true);

alter table ai_performance enable row level security;
alter table postgame_reviews enable row level security;
alter table market_monitoring_events enable row level security;
alter table model_routing_rules enable row level security;
alter table prompt_registry enable row level security;
alter table model_registry enable row level security;
alter table recommendation_costs enable row level security;
alter table audit_log enable row level security;
-- No select policy on the eight tables above: default-deny for anon/authenticated,
-- service role bypasses per §10's existing service-role principle.
