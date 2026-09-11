-- Sunday Ingestion Foundation Build (2026-09-11) required test evidence for
-- game_postgame_ingestion_state:
--   1. one durable row per (game, provider) -- duplicate insert rejected.
--   2. valid state transitions -- the state check constraint accepts every
--      named state and rejects an invalid one.
--   3. atomic claim behavior -- the exact UPDATE ... WHERE state =
--      'eligible_for_postgame_check' ... RETURNING shape the accepted
--      Sunday design specifies claims a row and advances attempt_count;
--      a second claim attempt against the now-claimed row affects zero
--      rows (this is what makes concurrent/redeploy-safe claiming work --
--      proven here at the single-connection level, since true concurrent-
--      transaction locking is exercised by Postgres's own MVCC guarantees,
--      not something a single-session pgTAP suite can independently
--      re-prove).
--   4. attempt-budget enforcement foundation -- attempt_count increments
--      monotonically across repeated claims and is queryable, the schema
--      contract a future worker's own budget check will rely on (the
--      budget check itself is explicitly out of scope for this pass).
--   5. RLS default-deny -- no policy exists, so the authenticated role
--      (and, by the same mechanism, anon) sees zero rows, matching the
--      exact pattern already established for activation_run_markers and
--      every other internal accounting table in this project.
-- Run via `supabase test db`, or manually inside a transaction that's
-- rolled back -- same convention as every other file in this directory.

begin;
create extension if not exists pgtap with schema extensions;
select plan(10);

-- games.home_team/away_team are plain text, not FK'd to teams -- no
-- leagues/teams fixture rows are needed for this table's own tests.
insert into games (id, sport, home_team, away_team, scheduled_start, status)
values ('e1000000-0000-0000-0000-000000000004', 'nfl', 'Test Home', 'Test Away', now() - interval '4 hours', 'scheduled');

-- ----------------------------------------------------------------------------
-- Proof 1: one durable row per (game, provider) -- unique constraint enforced.
-- ----------------------------------------------------------------------------
insert into game_postgame_ingestion_state (game_id, provider_name, state)
values ('e1000000-0000-0000-0000-000000000004', 'mysportsfeeds', 'eligible_for_postgame_check');

select throws_ok(
  $$ insert into game_postgame_ingestion_state (game_id, provider_name, state)
     values ('e1000000-0000-0000-0000-000000000004', 'mysportsfeeds', 'scheduled') $$,
  '23505',
  null,
  'a second row for the same (game_id, provider_name) is rejected -- one durable row per game+provider'
);

-- ----------------------------------------------------------------------------
-- Proof 2: valid state transitions -- every named state is accepted, an
-- invalid one is rejected.
-- ----------------------------------------------------------------------------
select lives_ok(
  $$ update game_postgame_ingestion_state set state = 'captured'
     where game_id = 'e1000000-0000-0000-0000-000000000004' $$,
  'a named state (captured) is accepted by the check constraint'
);
select lives_ok(
  $$ update game_postgame_ingestion_state set state = 'confirmed_complete'
     where game_id = 'e1000000-0000-0000-0000-000000000004' $$,
  'a named terminal state (confirmed_complete) is accepted'
);
select throws_ok(
  $$ update game_postgame_ingestion_state set state = 'not_a_real_state'
     where game_id = 'e1000000-0000-0000-0000-000000000004' $$,
  '23514',
  null,
  'an unrecognized state is rejected by the check constraint'
);

-- reset to the eligible state for the claim proofs below
update game_postgame_ingestion_state set state = 'eligible_for_postgame_check', attempt_count = 0
where game_id = 'e1000000-0000-0000-0000-000000000004';

-- ----------------------------------------------------------------------------
-- Proof 3: atomic claim behavior -- the exact claim shape from the accepted
-- design (Section 2) advances state + attempt_count and is only ever
-- satisfiable while the row is actually eligible. Each claim attempt is run
-- as a bare top-level UPDATE (a data-modifying CTE cannot be nested inside
-- a pgTAP assertion's argument expression -- Postgres requires it at the
-- statement's top level), then asserted on via the row's resulting values --
-- an UPDATE whose WHERE clause matches nothing is a silent no-op, which is
-- exactly the "second claim attempt affects zero rows" behavior this proves.
-- ----------------------------------------------------------------------------
update game_postgame_ingestion_state
set state = 'capture_in_progress', last_attempt_at = now(), attempt_count = attempt_count + 1
where game_id = 'e1000000-0000-0000-0000-000000000004'
  and provider_name = 'mysportsfeeds'
  and state = 'eligible_for_postgame_check';

select is(
  (select state from game_postgame_ingestion_state where game_id = 'e1000000-0000-0000-0000-000000000004'),
  'capture_in_progress',
  'the claim UPDATE advances state to capture_in_progress when the row was eligible'
);
select is(
  (select attempt_count from game_postgame_ingestion_state where game_id = 'e1000000-0000-0000-0000-000000000004'),
  1,
  'attempt_count advanced to 1 after the first claim'
);

-- Re-run the identical claim UPDATE. The row is no longer in
-- 'eligible_for_postgame_check' (it's 'capture_in_progress' now), so the
-- WHERE clause matches zero rows -- a silent no-op, proven by attempt_count
-- staying unchanged at 1 rather than advancing to 2.
update game_postgame_ingestion_state
set state = 'capture_in_progress', last_attempt_at = now(), attempt_count = attempt_count + 1
where game_id = 'e1000000-0000-0000-0000-000000000004'
  and provider_name = 'mysportsfeeds'
  and state = 'eligible_for_postgame_check';

select is(
  (select attempt_count from game_postgame_ingestion_state where game_id = 'e1000000-0000-0000-0000-000000000004'),
  1,
  'a second claim attempt against the now-claimed row is a no-op -- attempt_count unchanged, no double-claim'
);

-- ----------------------------------------------------------------------------
-- Proof 4: attempt-budget enforcement foundation -- attempt_count keeps
-- incrementing monotonically and stays queryable across repeated
-- eligible/claim cycles, the exact contract a future worker's own budget
-- check (not built this pass) will read.
-- ----------------------------------------------------------------------------
update game_postgame_ingestion_state set state = 'eligible_for_postgame_check'
where game_id = 'e1000000-0000-0000-0000-000000000004';
update game_postgame_ingestion_state
set state = 'capture_in_progress', attempt_count = attempt_count + 1
where game_id = 'e1000000-0000-0000-0000-000000000004' and state = 'eligible_for_postgame_check';

select is(
  (select attempt_count from game_postgame_ingestion_state where game_id = 'e1000000-0000-0000-0000-000000000004'),
  2,
  'attempt_count is monotonically queryable across repeated claim cycles (foundation for a future budget check)'
);

-- ----------------------------------------------------------------------------
-- Proof 5: RLS default-deny -- no policy exists on this table, matching the
-- activation_run_markers/odds_api_credit_ledger convention exactly. No JWT
-- claim needed (unlike the owner-vs-non-owner checks elsewhere in this test
-- suite) -- this table has zero policies of any kind, so no role can read
-- it regardless of identity.
-- ----------------------------------------------------------------------------
set local role authenticated;
select is(
  (select count(*) from game_postgame_ingestion_state)::int, 0,
  'game_postgame_ingestion_state: default-deny holds for authenticated role'
);
reset role;

set local role anon;
select is(
  (select count(*) from game_postgame_ingestion_state)::int, 0,
  'game_postgame_ingestion_state: default-deny holds for anon role'
);
reset role;

select * from finish();
rollback;
