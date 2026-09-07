-- Phase 7 Controlled Real Odds Activation, safety fix (2026-09-07).
--
-- A real incident: 3 manually-seeded `games` rows that never
-- corresponded to any real Odds API event triggered a paid bulk
-- `/odds` call on every single 15-minute cron tick, indefinitely --
-- `app.persistence.odds_snapshots.read_last_polled_at()` derives
-- cadence purely from `odds_snapshots.captured_at` history, so a game
-- that can never accrue a snapshot (because it never links to a real
-- event) reads as "never polled" forever, and `should_poll` never
-- stops returning True for it.
--
-- `manual_seed` marks a `games` row created by a manual seeding process
-- (not Schedule/Master Refresh) -- default false, so this protection
-- never touches the existing, correct "keep retrying a real but
-- temporarily-unresolved game" behavior for normal production rows.
-- `unresolved_poll_attempts` counts consecutive due-but-uncaptured
-- cycles for a manual-seed row only; `app.workers.odds_worker` excludes
-- a manual-seed row from `due_games` once this reaches
-- MANUAL_SEED_MAX_ATTEMPTS, capping the paid-call exposure of an
-- incorrect manual seed to a small, bounded number of attempts instead
-- of an unbounded one.
alter table games
  add column manual_seed boolean not null default false,
  add column unresolved_poll_attempts integer not null default 0;

comment on column games.manual_seed is
  'True only for a games row created by a manual seeding process (never Schedule/Master Refresh) -- gates the unresolved_poll_attempts cap in app.workers.odds_worker. Normal Schedule-sourced rows are unaffected by this protection.';
comment on column games.unresolved_poll_attempts is
  'Consecutive due-but-uncaptured cron cycles for a manual_seed=true row. Once this reaches app.workers.odds_worker.MANUAL_SEED_MAX_ATTEMPTS, the row is excluded from future due-game consideration -- bounded protection against an incorrect manual seed triggering unbounded paid calls.';
