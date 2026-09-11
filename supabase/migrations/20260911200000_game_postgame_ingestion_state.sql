-- Sunday Ingestion Foundation Build (2026-09-11, HQ-authorized): durable
-- per-(game, provider) postgame ingestion state, exactly the schema
-- named (not yet applied) in the accepted Sunday completed-game
-- ingestion design (docs/ops/phase-8-sunday-completed-game-ingestion-
-- design-2026-09-10.md, Section 2) and refined in the preflight
-- correction pass. Foundation only -- no worker reads or writes this
-- table yet; this migration exists so a future, separately-authorized
-- pass has somewhere durable to put state, not to wire anything live.
--
-- State machine (Section 1 of the accepted design): games.status is
-- never authoritative for "is this game over" -- only a provider's own
-- playedStatus is. This table tracks, per (game, provider), where a
-- postgame capture attempt currently stands, independent of and never
-- overwriting games.status itself.
--
--   scheduled -> eligible_for_postgame_check -> capture_in_progress
--     -> captured -> validated -> confirmed_complete
--   side states (terminal or awaiting manual review, never silent):
--     capture_failed_transient, capture_failed_permanent,
--     validation_failed, partially_confirmed
--
-- Claim semantics (Section 2 of the design): a future worker claims a
-- row via `UPDATE ... SET state = 'capture_in_progress', ...
-- WHERE state = 'eligible_for_postgame_check' AND
-- next_eligible_attempt_at <= now() RETURNING id`. Postgres's own
-- row-level locking on UPDATE already makes this atomic across
-- concurrent workers/redeploys -- two concurrent claims on the same row
-- serialize automatically, and the loser's WHERE clause no longer
-- matches once the winner commits. No additional mechanism (advisory
-- locks, SELECT FOR UPDATE) is needed beyond the unique constraint
-- below plus this UPDATE shape, which is why none is added here.
--
-- error_classification is a distinct column from state/last_error
-- deliberately -- HQ's Sunday preflight correction explicitly separated
-- "not-completed-yet" (real information, not a failure), "transient
-- network failure" (short, bounded local retry), and "genuine provider
-- failure" (stop and escalate, never silently retried on the same
-- cadence) as three different signals with three different responses.
-- A future worker sets this only on capture_failed_transient/
-- capture_failed_permanent rows; it stays null for every other state,
-- including the normal "not ready yet" case (which is not a failure).
create table game_postgame_ingestion_state (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  provider_name text not null check (provider_name in ('mysportsfeeds')),
  state text not null default 'scheduled' check (state in (
    'scheduled',
    'eligible_for_postgame_check',
    'capture_in_progress',
    'captured',
    'validated',
    'confirmed_complete',
    'capture_failed_transient',
    'capture_failed_permanent',
    'validation_failed',
    'partially_confirmed'
  )),
  attempt_count integer not null default 0,
  last_attempt_at timestamptz,
  next_eligible_attempt_at timestamptz,
  last_http_status integer,
  last_error text,
  error_classification text check (error_classification in ('transient', 'permanent')),
  raw_capture_id uuid references game_events(id),
  captured_at timestamptz,
  quarantine_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (game_id, provider_name)
);

create trigger trg_game_postgame_ingestion_state_updated
  before update on game_postgame_ingestion_state
  for each row execute function set_updated_at();

-- Supporting index for the worker's own claim query shape (Section
-- "Sunday Operating Plan" of the design): find every row eligible for
-- a check right now. Partial -- only the one state this index actually
-- needs to serve is included, keeping it small.
create index idx_game_postgame_ingestion_state_eligible
  on game_postgame_ingestion_state (next_eligible_attempt_at)
  where state = 'eligible_for_postgame_check';

-- Internal ingestion-accounting table, not user data -- same "RLS
-- enabled, no policy" convention already established for
-- activation_run_markers/odds_api_credit_ledger/display_id_counters
-- (service-role access only, via the service key's RLS bypass). No
-- public_read policy, unlike game_provider_ids/team_provider_ids --
-- this table's own rows are operational bookkeeping, not identity data
-- any client has a reason to read.
alter table game_postgame_ingestion_state enable row level security;
