-- Phase 8.0.5 Pass 2.2 (2026-09-07): real, durable safety state for News
-- Worker, closing the two gaps Pass 2.1 diagnosed but deliberately did not
-- fix without HQ sign-off (the main.py call site never passed a real
-- last_polled_at, and no persisted daily quota guard existed for GNews).
--
-- Two independent tables, not a reuse of odds_api_credit_ledger:
-- that ledger is a MONTHLY figure with no automatic rollover logic, and
-- retrofitting daily-rollover onto a shared table already trusted for
-- Odds' own real financial safety was explicitly flagged in Pass 2.1 as
-- carrying blast radius beyond News. A day-keyed table sidesteps rollover
-- entirely: each UTC day is its own row, so a new day simply has no row
-- yet (reads as zero) rather than needing any reset logic at all.

create table news_provider_daily_quota (
  id uuid primary key default gen_random_uuid(),
  provider_name text not null,
  quota_date date not null,
  requests_used integer not null default 0,
  updated_at timestamptz not null default now()
);
create unique index idx_news_provider_daily_quota_identity on news_provider_daily_quota(provider_name, quota_date);

alter table news_provider_daily_quota enable row level security;
create policy "public_read" on news_provider_daily_quota for select using (true);

-- Atomic increment, not read-then-write: HQ's directive explicitly
-- requires "concurrency-safe" this pass (unlike odds_api_credit_ledger's
-- accepted single-writer read-then-write risk) -- a single UPSERT with an
-- expression-based increment is atomic under Postgres's own MVCC/row-lock
-- semantics, with no read-modify-write race window at all.
create or replace function increment_news_provider_quota(p_provider_name text, p_quota_date date)
returns integer
language sql
as $$
  insert into news_provider_daily_quota (provider_name, quota_date, requests_used, updated_at)
  values (p_provider_name, p_quota_date, 1, now())
  on conflict (provider_name, quota_date)
  do update set requests_used = news_provider_daily_quota.requests_used + 1, updated_at = now()
  returning requests_used;
$$;

-- Real per-team last-poll state. news_article_history (2026-09-04) cannot
-- serve this purpose despite carrying an ingested_at column: it is
-- insert-once-per-(provider_name, article_url) (first-sighting only), so
-- a team whose fetch succeeds with zero NEW articles writes no row at
-- all -- indistinguishable from "never polled." This table instead
-- records "a real fetch was attempted for this team," independent of
-- whether that fetch found anything new.
create table news_worker_poll_state (
  team_id uuid primary key,
  last_polled_at timestamptz not null,
  updated_at timestamptz not null default now()
);

alter table news_worker_poll_state enable row level security;
create policy "public_read" on news_worker_poll_state for select using (true);
