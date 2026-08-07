-- Phase 1, Milestone 1: core user/account tables (Volume 3 §3, §10, §11)
-- user_profiles, subscriptions, betting_dna — all extend auth.users via FK, never duplicate auth fields.

-- ============================================================================
-- Tables
-- ============================================================================

create table user_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  jurisdiction_state text not null,
  persona_classification text check (persona_classification in ('grinder','casual','numbers_person', null)),
  betting_experience text check (betting_experience in ('new','casual','experienced')),
  primary_goal text check (primary_goal in ('fun','disciplined_longterm','edge_seeking')),
  risk_tolerance text check (risk_tolerance in ('conservative','moderate','aggressive')),
  preferred_unit_size numeric(10,2),
  max_parlay_legs integer default 0,
  optional_bankroll numeric(12,2),
  onboarding_completed_at timestamptz,
  referral_code text unique,
  deleted_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index idx_user_profiles_persona on user_profiles(persona_classification);

create table subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  tier text not null check (tier in ('free','pro','elite','syndicate')),
  status text not null check (status in ('active','past_due','canceled','trialing')),
  billing_period text check (billing_period in ('monthly','annual')),
  current_period_start timestamptz,
  current_period_end timestamptz,
  external_billing_id text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index idx_subscriptions_user on subscriptions(user_id);
create index idx_subscriptions_status on subscriptions(status) where status = 'active';

create table betting_dna (
  user_id uuid primary key references auth.users(id) on delete cascade,
  favorite_sportsbooks text[],
  observed_bet_types text[],
  observed_avg_odds numeric(6,2),
  observed_risk_tendency text,
  observed_frequency text,
  favorite_sports text[],
  last_recalculated_at timestamptz default now()
);

-- ============================================================================
-- Triggers (Volume 3 §11)
-- ============================================================================

create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trg_user_profiles_updated
  before update on user_profiles
  for each row execute function set_updated_at();

create trigger trg_subscriptions_updated
  before update on subscriptions
  for each row execute function set_updated_at();

-- betting_dna has last_recalculated_at instead of updated_at — not covered by this trigger, by design.

-- ============================================================================
-- Row Level Security (Volume 3 §10)
-- ============================================================================

alter table user_profiles enable row level security;
create policy "own_profile_select" on user_profiles
  for select using (auth.uid() = id and deleted_at is null);
create policy "own_profile_update" on user_profiles
  for update using (auth.uid() = id);

alter table subscriptions enable row level security;
-- NOTE: subscriptions is not in §10's explicit named list of tables using the
-- auth.uid() = user_id pattern (only verified_bets, bet_slips,
-- projected_user_performance, verified_user_performance, betting_dna, and
-- conversations/conversation_messages are named). Applied here anyway per
-- §10's opening line ("RLS is enabled on every table containing user data")
-- and because subscriptions holds user-specific billing data. Flagged per
-- CLAUDE.md's blueprint-vs-reality process rather than treated as settled
-- blueprint text — see PROGRESS.md Phase 1 notes.
create policy "own_subscription_select" on subscriptions
  for select using (auth.uid() = user_id);

alter table betting_dna enable row level security;
create policy "own_betting_dna_select" on betting_dna
  for select using (auth.uid() = user_id);

-- subscriptions and betting_dna have no deleted_at column, so no soft-delete
-- filtering is added to their select policies (Volume 3 §10's soft-delete
-- filtering applies only to tables with a deleted_at column).
-- Neither table has a user-facing insert/update/delete policy: subscriptions
-- is written by the billing integration and betting_dna by a background
-- worker (Volume 3 §3), both via the service-role key, which bypasses RLS.
