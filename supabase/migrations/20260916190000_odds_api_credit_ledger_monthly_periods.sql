-- Odds API credit ledger: real UTC calendar-month periods + provider header
-- reconciliation (2026-09-16, HQ-authorized "ODDS CREDIT LEDGER MONTHLY
-- ROLLOVER -- IMPLEMENT").
--
-- ===========================================================================
-- WHY
-- ===========================================================================
--
-- The original ledger (20260907120000) said so itself: "No automatic monthly
-- period rollover is built here -- a real 'is it a new calendar month' reset
-- is a disclosed, deliberate scope limit for this pass (HQ can reset the
-- counter manually, or a future milestone can add real rollover)." This is
-- that milestone.
--
-- The defect that made it urgent: `record_call` never wrote `period_start`
-- (it is absent from the upsert payload, so PostgREST left the column at its
-- row-creation default forever), and no code ever READ it. So the guard was
-- comparing a MONOTONICALLY INCREASING LIFETIME counter against a MONTHLY
-- budget. Once `credits_used_this_period` crossed 450 the guard would trip
-- and -- because nothing ever reset it -- stay tripped permanently, silently
-- stopping all odds collection while the real vendor allowance was full.
--
-- THE AUTHORITATIVE RULE, now confirmed from The Odds API's official FAQ and
-- supplied by HQ: "Usage credits are automatically reset on the first of
-- every month." So the period is a CALENDAR MONTH. MANSA's internal
-- accounting convention is the UTC calendar month, keyed 'YYYY-MM'.
--
-- ===========================================================================
-- THE DESIGN: rollover is a LOOKUP, not a MUTATION
-- ===========================================================================
--
-- `period_key` becomes part of the row's identity. A new month has no row
-- yet, so it reads as zero -- there is no reset logic to run, no date
-- arithmetic to get wrong at the boundary, and nothing to fail halfway.
--
-- This is the same trick two tables in this project already use, and it is
-- reused deliberately rather than invented: `news_provider_daily_quota` and
-- `odds_api_daily_call_budget` are both day-keyed, and the latter's own
-- migration records the reason -- "Day-keyed, so there is no rollover logic
-- at all."
--
-- It also satisfies the requirements in a way that mutating `period_start`
-- in place could not:
--   * a stale prior-period row can NEVER block a new month, because the new
--     month simply does not read it (requirement 6);
--   * prior months are immutable and auditable, because nothing ever writes
--     to them again (requirements 1, 2);
--   * rollover needs NO provider call -- the key is computed from the clock
--     (requirement 4);
--   * a process restart changes nothing, because usage lives here keyed by
--     period rather than in memory (requirement 7).
--
-- ===========================================================================
-- PROVIDER HEADER RECONCILIATION
-- ===========================================================================
--
-- The provider returns `x-requests-used`, `x-requests-remaining` and
-- `x-requests-last` on quota-bearing responses, and is definitionally
-- authoritative about its own quota. Those are recorded here ALONGSIDE our
-- own count, never on top of it:
--
--   credits_used_this_period  -- OUR deterministic count (calls x 3). Never
--                                overwritten by the provider, so our own
--                                spend record is never destroyed.
--   provider_reported_used    -- what the vendor last said. The guard treats
--                                THIS as authoritative when present.
--
-- Keeping both is what makes a discrepancy visible instead of silently
-- resolved. It matters most at the exact reset boundary: at 00:05 on the 1st
-- our new-month row reads 0 while the vendor may not have reset yet and
-- still reports 490 used -- trusting only our local count there would
-- overspend a real allowance. The reverse case (vendor resets slightly
-- early) is equally covered.

-- --------------------------------------------------------------------------
-- 1. Add the period key and the provider-reconciliation columns.
-- --------------------------------------------------------------------------
alter table odds_api_credit_ledger
  add column period_key text,
  add column provider_reported_used integer,
  add column provider_reported_remaining integer,
  add column provider_reported_last integer,
  add column provider_reported_at timestamptz,
  --: Set whenever the vendor's number and ours disagree. Purely an audit
  --: trail -- never read by the guard -- so a discrepancy is preserved
  --: rather than silently ignored.
  last_discrepancy text;

-- --------------------------------------------------------------------------
-- 2. Backfill the existing row from its own period_start.
--
-- The live row is 276 credits with period_start 2026-09-07 02:30:23+00,
-- which falls in 2026-09. That 276 is genuine usage and is preserved as
-- September's history rather than discarded or reset -- the same "an honest
-- record of real usage, not zeroed out" discipline already applied to this
-- ledger once before.
--
-- Derived from the data, not hardcoded, so this is correct for every
-- environment regardless of when its own row was created.
-- --------------------------------------------------------------------------
update odds_api_credit_ledger
set period_key = to_char(period_start at time zone 'UTC', 'YYYY-MM')
where period_key is null;

alter table odds_api_credit_ledger
  alter column period_key set not null;

-- --------------------------------------------------------------------------
-- 3. Move uniqueness from (provider_name) to (provider_name, period_key).
--
-- The old constraint allowed exactly ONE row per provider, for all time --
-- which is precisely what made a second period impossible to represent.
-- --------------------------------------------------------------------------
alter table odds_api_credit_ledger
  drop constraint odds_api_credit_ledger_provider_name_key;

alter table odds_api_credit_ledger
  add constraint odds_api_credit_ledger_provider_period_key
  unique (provider_name, period_key);

comment on column odds_api_credit_ledger.period_key is
  'UTC calendar month, ''YYYY-MM''. The vendor resets usage credits on the '
  'first of every month, so a new month is a new row: rollover is a lookup, '
  'never a mutation, and prior months stay immutable and auditable.';

comment on column odds_api_credit_ledger.credits_used_this_period is
  'OUR OWN deterministic count for this period (real round-trips x '
  'CREDITS_PER_CALL). Never overwritten by provider headers, so our spend '
  'record survives reconciliation.';

comment on column odds_api_credit_ledger.provider_reported_used is
  'Vendor''s own x-requests-used for this period. Authoritative for the '
  'guard when present; kept separate from our count so a disagreement is '
  'visible rather than silently resolved.';

-- --------------------------------------------------------------------------
-- 4. Atomic, idempotent, concurrency-safe increment.
--
-- Replaces the previous read-then-write upsert in
-- app.persistence.odds_api_credit_ledger, whose race window was an accepted
-- disclosed risk on the old single-row design. A hard spending guard should
-- not inherit a known race, and with per-month rows two workers crossing the
-- boundary together is exactly when one would bite. A single UPSERT with an
-- expression-based increment is atomic under Postgres's own row-lock
-- semantics: concurrent callers converge on ONE row per (provider, period)
-- and cannot create conflicting active periods.
--
-- Matches increment_news_provider_quota / increment_odds_api_daily_calls
-- rather than introducing a third pattern.
-- --------------------------------------------------------------------------
create or replace function increment_odds_api_credits(
  p_provider_name text,
  p_period_key text,
  p_credits integer
)
returns integer
language sql
as $$
  insert into odds_api_credit_ledger (
    provider_name, period_key, credits_used_this_period, period_start, updated_at
  )
  values (
    p_provider_name,
    p_period_key,
    p_credits,
    -- First write of a period anchors period_start to that month's real
    -- start instant, so the column finally means what its name says.
    to_timestamp(p_period_key || '-01', 'YYYY-MM-DD') at time zone 'UTC',
    now()
  )
  on conflict (provider_name, period_key)
  do update set
    credits_used_this_period = odds_api_credit_ledger.credits_used_this_period + p_credits,
    updated_at = now()
  returning credits_used_this_period;
$$;

-- --------------------------------------------------------------------------
-- 5. Record what the provider says, without touching our own count.
--
-- Idempotent and safe to call repeatedly: it only ever overwrites the
-- provider-reported snapshot for the CURRENT period.
-- --------------------------------------------------------------------------
create or replace function reconcile_odds_api_provider_usage(
  p_provider_name text,
  p_period_key text,
  p_used integer,
  p_remaining integer,
  p_last integer,
  p_discrepancy text
)
returns integer
language sql
as $$
  insert into odds_api_credit_ledger (
    provider_name, period_key, credits_used_this_period, period_start,
    provider_reported_used, provider_reported_remaining, provider_reported_last,
    provider_reported_at, last_discrepancy, updated_at
  )
  values (
    p_provider_name, p_period_key, 0,
    to_timestamp(p_period_key || '-01', 'YYYY-MM-DD') at time zone 'UTC',
    p_used, p_remaining, p_last, now(), p_discrepancy, now()
  )
  on conflict (provider_name, period_key)
  do update set
    provider_reported_used = p_used,
    provider_reported_remaining = p_remaining,
    provider_reported_last = p_last,
    provider_reported_at = now(),
    last_discrepancy = p_discrepancy,
    updated_at = now()
  returning provider_reported_used;
$$;
