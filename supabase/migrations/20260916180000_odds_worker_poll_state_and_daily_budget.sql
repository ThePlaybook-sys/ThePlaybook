-- Odds Worker Cost + Failure Hardening (2026-09-16, HQ-authorized).
--
-- Two tables, deliberately mirroring the two the News Worker already uses
-- (20260907211500_news_provider_quota_and_poll_state.sql) rather than
-- inventing new shapes. News hit BOTH of these problems first and solved
-- them; Odds is the same problem with a bigger bill.
--
-- ===========================================================================
-- 1. odds_worker_poll_state -- separating ATTEMPT from SUCCESS
-- ===========================================================================
--
-- THE DEFECT THIS CLOSES. `last_polled_at` was derived from
-- `odds_snapshots.captured_at` (app/persistence/odds_snapshots.read_last_
-- polled_at). odds_snapshots is written ONLY when an event resolves to a
-- canonical game. So:
--
--     provider call succeeds
--       -> event cannot be linked (no team mapping, kickoff out of
--          tolerance, ambiguous candidate, ...)
--       -> no snapshot row is written
--       -> the game reads as NEVER POLLED
--       -> it is due again on the very next cron tick
--       -> forever.
--
-- Attempt and success were the same signal, and only success was recorded.
-- On 2026-09-16 that burned 36 credits across 12 consecutive ticks while
-- persisting zero rows, and it stopped only because the underlying team
-- mappings were repaired -- the mechanism itself was untouched.
--
-- This is EXACTLY the reasoning already written into news_worker_poll_state,
-- whose own migration comment reads: "news_article_history cannot serve this
-- purpose despite carrying an ingested_at column: it is insert-once-per-
-- (provider_name, article_url), so a team whose fetch succeeds with zero NEW
-- articles writes no row at all -- indistinguishable from 'never polled.'"
-- Same trap, same fix: a table that records "a real fetch was attempted for
-- this game," independent of whether that fetch produced anything.
--
-- This table is richer than news_worker_poll_state because Odds needs to
-- back off, not merely remember. It records the attempt, its outcome, the
-- last genuine success separately, and a consecutive-failure counter that
-- drives deterministic backoff (app/workers/odds_backoff.py).
--
-- NOT append-only, deliberately. This is current-state scheduling metadata,
-- not a fact worth preserving history of -- the same judgment
-- news_worker_poll_state's own comment records, and the opposite of
-- odds_snapshots, which IS append-only because an observed market price is
-- a fact. One row per (game, provider), always overwritten.

create table odds_worker_poll_state (
  game_id uuid not null,
  provider_name text not null,
  --: Every real attempt stamps this, whatever the outcome. This is the
  --: half that did not exist before.
  last_attempt_at timestamptz not null,
  --: 'success' | 'unresolved' | 'provider_failure'. Constrained rather
  --: than free text so a typo cannot silently write a status that no
  --: backoff branch matches -- which would fail OPEN, back to every-tick
  --: spending.
  last_attempt_outcome text not null,
  --: Last attempt that actually produced a persisted snapshot. NULL until
  --: the game has ever genuinely captured. This -- never last_attempt_at --
  --: is what feeds the kickoff-proximity cadence, so an unresolved attempt
  --: can never masquerade as fresh odds data.
  last_success_at timestamptz,
  --: Consecutive non-success attempts. Reset to 0 by any success. Drives
  --: the backoff schedule.
  consecutive_failure_count integer not null default 0,
  --: Human-readable reason for the most recent failure, preserved so a
  --: failure is never silently dropped. Cleared on success.
  last_failure_reason text,
  updated_at timestamptz not null default now(),
  primary key (game_id, provider_name),
  constraint odds_worker_poll_state_outcome_check
    check (last_attempt_outcome in ('success', 'unresolved', 'provider_failure')),
  constraint odds_worker_poll_state_failure_count_check
    check (consecutive_failure_count >= 0)
);

comment on table odds_worker_poll_state is
  'Per-game odds poll ATTEMPT state. Exists because odds_snapshots records '
  'only successes, so an attempted-but-unresolved poll left no trace and the '
  'game came due again every cron tick forever. last_success_at drives '
  'cadence; last_attempt_at + consecutive_failure_count drive backoff.';

alter table odds_worker_poll_state enable row level security;
create policy "public_read" on odds_worker_poll_state for select using (true);

-- ===========================================================================
-- 2. odds_api_daily_call_budget -- a hard per-day ceiling
-- ===========================================================================
--
-- WHY THE EXISTING MONTHLY GUARD IS NOT ENOUGH. odds_api_credit_ledger holds
-- a MONTHLY figure and `_check_credit_guard` trips only when
-- `budget - used <= floor`. That correctly prevents overrunning the period,
-- but it permits a legal-but-expensive single day from consuming the whole
-- allocation: under the current */15 cron, 96 ticks x 3 credits = 288 credits
-- in one day is reachable without the monthly guard objecting even once,
-- right up until the moment it slams shut and stops odds collection entirely
-- -- possibly mid-slate on a Sunday.
--
-- The monthly ledger is the outer bound. This is the inner one.
--
-- DAY-KEYED, SO THERE IS NO ROLLOVER LOGIC AT ALL. Each UTC day is its own
-- row; a new day simply has no row yet and reads as zero. This is the exact
-- rationale news_provider_daily_quota's own migration records, and it is
-- reused here for the same reason: retrofitting daily rollover onto the
-- monthly ledger would put new logic inside a table already trusted for real
-- financial safety.
--
-- COUNTS CALLS, NOT CREDITS. One bulk call is a fixed CREDITS_PER_CALL (3),
-- and one bulk call serves every due game at once regardless of how many
-- there are, so calls are the unit the policy can actually control. Credits
-- are derived (calls x 3) and reported.

create table odds_api_daily_call_budget (
  id uuid primary key default gen_random_uuid(),
  provider_name text not null,
  budget_date date not null,
  calls_used integer not null default 0,
  updated_at timestamptz not null default now()
);
create unique index idx_odds_api_daily_call_budget_identity
  on odds_api_daily_call_budget(provider_name, budget_date);

comment on table odds_api_daily_call_budget is
  'Per-UTC-day provider call count for The Odds API. Day-keyed so a new day '
  'needs no reset logic. Counts CALLS because one bulk call serves every due '
  'game at once; credits are derived as calls x CREDITS_PER_CALL.';

alter table odds_api_daily_call_budget enable row level security;
create policy "public_read" on odds_api_daily_call_budget for select using (true);

-- Atomic increment, matching increment_news_provider_quota exactly. A single
-- UPSERT with an expression-based increment is atomic under Postgres's own
-- row-lock semantics, with no read-modify-write window. Deliberately
-- STRONGER than odds_api_credit_ledger's accepted single-writer
-- read-then-write risk: this counter is a hard spending ceiling, so it should
-- not inherit a known race, however narrow.
create or replace function increment_odds_api_daily_calls(p_provider_name text, p_budget_date date)
returns integer
language sql
as $$
  insert into odds_api_daily_call_budget (provider_name, budget_date, calls_used, updated_at)
  values (p_provider_name, p_budget_date, 1, now())
  on conflict (provider_name, budget_date)
  do update set calls_used = odds_api_daily_call_budget.calls_used + 1, updated_at = now()
  returning calls_used;
$$;
