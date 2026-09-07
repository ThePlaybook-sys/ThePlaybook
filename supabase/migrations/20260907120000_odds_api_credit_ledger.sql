-- Phase 7 Controlled Real Odds Activation (2026-09-07, HQ-authorized).
--
-- A self-counted credit accounting ledger for The Odds API's bulk /odds
-- endpoint, deliberately NOT dependent on parsing the vendor's own
-- x-requests-remaining/x-requests-used response headers -- those header
-- names are already flagged elsewhere in this codebase as ASSUMED, never
-- live-verified (app.adapters.providers.the_odds_api's own _get helper).
-- Every bulk /odds call this project's adapter makes costs a fixed,
-- deterministic 3 credits (markets=h2h,spreads,totals x regions=us,
-- CONFIRMED from the vendor's own docs, 2026-08-10 credit-usage
-- projection) -- counting OUR OWN successful calls x 3 is more reliable
-- than trusting an unverified header name for a safety guard whose whole
-- job is to fail closed correctly.
--
-- One row per provider, upserted on every successful real call (never on
-- a cache hit, never on a failed/skipped call) by
-- app.workers.odds_worker. No automatic monthly period rollover is built
-- here -- a real "is it a new calendar month" reset is a disclosed,
-- deliberate scope limit for this pass (HQ can reset the counter
-- manually, or a future milestone can add real rollover); the guard's
-- job today is "never silently exceed the free-tier budget," not
-- "automatically track billing periods."
create table odds_api_credit_ledger (
  id uuid primary key default gen_random_uuid(),
  provider_name text not null unique,
  credits_used_this_period integer not null default 0,
  period_start timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Internal accounting table, not user data -- same "RLS enabled, no
-- policy" convention already established for display_id_counters/
-- recommendation_agent_outputs/consensus_snapshots (service-role access
-- only, via the service key's RLS bypass).
alter table odds_api_credit_ledger enable row level security;
