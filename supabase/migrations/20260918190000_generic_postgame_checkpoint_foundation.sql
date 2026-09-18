-- Persistent Postgame Checkpoint Foundation (2026-09-18, HQ-authorized
-- "PERSISTENT CHECKPOINT FOUNDATION" directive). Provider-independent,
-- purely ADDITIVE: no column is dropped, no row is rewritten, no existing
-- caller changes behaviour.
--
-- WHY THIS EXISTS. The SportsDataIO postgame audit
-- (docs/ops/phase-8-postgame-finalization-sportsdataio-audit-2026-09-18.md)
-- found a defect that is not SportsDataIO's: `app.workers.postgame_worker`
-- holds its reconciliation checkpoint progress in a caller-supplied
-- in-process dict, and says so in its own docstring ("no worker-run-history
-- persistence layer exists yet"). A cron tick is a fresh process, so the set
-- of completed checks is empty on every invocation, the schedule never reads
-- as complete, and at least one checkpoint is always due -- roughly 12,000
-- provider calls for one NFL week against a design figure of 192.
--
-- That is a persistence-layer defect wearing a worker's clothes. Any
-- final-score provider driven by a stateless cron has it. So it is fixed
-- here, once, rather than per provider.
--
-- WHY THIS TABLE. `game_postgame_ingestion_state` already carries every
-- other piece of the contract -- (game_id, provider_name) identity with a
-- UNIQUE key, attempt_count, next_eligible_attempt_at, error_classification,
-- a ten-value state machine, and the atomic-claim shape its own creating
-- migration specifies. Two things were missing, and only two:
--
--   1. It is provider-SHAPED but provider-LOCKED. `check (provider_name in
--      ('mysportsfeeds'))` pins a generic table to one vendor. That is
--      exactly the "do not hardcode one provider's semantics into generic
--      persistence" rule, and it was already broken here.
--   2. There is nowhere to record WHICH checkpoints a game has completed --
--      only whether a single capture finished. A corrections schedule
--      (initial, +10m, +30m, +2h, +24h, +72h) needs the set, not a boolean.
--
-- Both are addressed below, and nothing else is touched.

-- 1. UNLOCK THE PROVIDER COLUMN -- to a closed allow-list, not to free text.
-- An open text column would let a typo ('balldontlie ', 'BallDontLie') mint
-- a ghost provider whose rows no worker ever claims, and the row would look
-- perfectly healthy while its game silently never finalizes. The allow-list
-- keeps that impossible while making the table mean what its column names
-- already claimed it meant.
alter table game_postgame_ingestion_state
  drop constraint game_postgame_ingestion_state_provider_name_check;

alter table game_postgame_ingestion_state
  add constraint game_postgame_ingestion_state_provider_name_check
  check (provider_name in ('mysportsfeeds', 'sportsdataio', 'balldontlie'));

-- 2. CHECKPOINT PROGRESS. A set of completed checkpoint LABELS, not a count
-- and not a timestamp. The labels are the provider-independent vocabulary
-- `app.workers.reconciliation.CHECKPOINT_OFFSETS` already defines
-- ('initial', '+10m', '+30m', '+2h', '+24h', '+72h'), and that module stays
-- the single place the schedule itself lives -- this column stores which of
-- them are done, never what they mean or when they are due.
--
-- Defaulted and NOT NULL so every pre-existing MSF row reads as '{}' -- no
-- checkpoints done -- which is both true and harmless: the MSF path is a
-- single-shot capture that never consults this column.
alter table game_postgame_ingestion_state
  add column checkpoints_done text[] not null default '{}';

-- 3. MONOTONICITY, ENFORCED BY THE DATABASE RATHER THAN BY CONVENTION.
-- Volume 3's standing rule for anything whose integrity the product depends
-- on: append-only via trigger, not via everyone remembering. A checkpoint
-- set that can shrink is the same defect as the in-process dict, just slower
-- to notice -- a worker that writes ['+72h'] where ['initial','+10m'] stood
-- would silently re-buy the two it dropped.
--
-- Also blocks the other direction of the same mistake: once a row reaches
-- 'confirmed_complete' it cannot return to a working state. Terminal means
-- terminal, so a restart, a duplicate tick, or a careless generic UPDATE
-- cannot reopen a finalized game and spend provider calls on it again.
create or replace function enforce_postgame_checkpoint_monotonicity()
returns trigger
language plpgsql
as $$
begin
  -- Checkpoint sets only ever grow. `@>` is "contains"; the new set must
  -- contain every label the old set had.
  if not (new.checkpoints_done @> old.checkpoints_done) then
    raise exception
      'checkpoints_done may not lose labels (game %, provider %): % -> %',
      old.game_id, old.provider_name, old.checkpoints_done, new.checkpoints_done
      using errcode = 'check_violation';
  end if;

  -- Terminal completion never reopens.
  if old.state = 'confirmed_complete' and new.state <> 'confirmed_complete' then
    raise exception
      'confirmed_complete is terminal and may not reopen (game %, provider %): -> %',
      old.game_id, old.provider_name, new.state
      using errcode = 'check_violation';
  end if;

  -- An attempt budget is not a thing a restart gets to hand back. Bounded
  -- retry is only bounded if the count that bounds it cannot be lowered.
  if new.attempt_count < old.attempt_count then
    raise exception
      'attempt_count may not decrease (game %, provider %): % -> %',
      old.game_id, old.provider_name, old.attempt_count, new.attempt_count
      using errcode = 'check_violation';
  end if;

  return new;
end;
$$;

create trigger trg_game_postgame_ingestion_state_monotonic
  before update on game_postgame_ingestion_state
  for each row execute function enforce_postgame_checkpoint_monotonicity();

-- 4. CLAIM INDEX, GENERALIZED. The existing partial index covers only
-- `state = 'eligible_for_postgame_check'` and does not include
-- provider_name, so a multi-provider claim scan would filter the other
-- providers' rows in the executor rather than the index. Additive: the
-- original index is left exactly as it is, since the MSF path still uses it.
create index idx_game_postgame_ingestion_state_provider_due
  on game_postgame_ingestion_state (provider_name, next_eligible_attempt_at)
  where state in ('scheduled', 'eligible_for_postgame_check');
