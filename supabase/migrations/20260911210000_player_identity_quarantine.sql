-- Automatic MSF Player Identity Activation + Quarantine (2026-09-11,
-- HQ-authorized). Durable record of identity cases the automatic
-- activation wrapper (app.persistence.player_identity_activation)
-- refuses to resolve automatically -- exactly the schema named (not
-- yet applied) in the accepted Sunday ingestion design, Section 3,
-- extended with the specific evidence fields this pass's directive
-- requires.
--
-- Design mirrors game_postgame_ingestion_state's own "RLS enabled, no
-- policy" internal-bookkeeping convention -- this table is audit
-- evidence for a human/future process to review, not user-facing data.
--
-- conflict_type enumerates every quarantine trigger the activation
-- wrapper can raise:
--   id_collision      -- provider_player_id resolved to nothing on the
--                        initial check, but creating its mapping hit a
--                        real uniqueness conflict (a genuine race or
--                        data-integrity anomaly) -- never silently
--                        adopted, always quarantined.
--   team_unresolved   -- provider_team_id missing, or has no
--                        team_provider_ids mapping for this provider.
--   ambiguous_match   -- an existing canonical player on the resolved
--                        team, without a mapping for this provider yet,
--                        has a name similar enough to be a plausible
--                        duplicate. Name similarity is a SAFETY SIGNAL
--                        here, never an identity mechanism -- this
--                        table exists specifically so that signal
--                        never silently becomes a merge.
--   malformed_identity -- the provider payload itself lacks a usable
--                        provider_player_id.
--
-- Duplicate-row prevention: a partial unique index (below) keyed on
-- (game_id, provider_name, identity_key) WHERE status = 'open' --
-- identity_key is provider_player_id when present, or a disclosed
-- name-based fallback when the case is itself malformed (the one
-- scenario with no provider_player_id to key on at all -- using name
-- here is solely to prevent duplicate BOOKKEEPING rows across
-- retries/redeploys, a different purpose from establishing player
-- identity, which this table and the activation wrapper never do from
-- name alone). A resolved case can be re-quarantined later under a new
-- row if the same identity genuinely recurs unresolved -- only OPEN
-- duplicates are prevented.
create table player_identity_quarantine (
  id uuid primary key default gen_random_uuid(),
  game_id uuid references games(id) on delete cascade,
  provider_name text not null check (provider_name in ('mysportsfeeds')),
  provider_player_id text,
  provider_team_id text,
  raw_player_name text,
  raw_position text,
  conflict_type text not null check (conflict_type in (
    'id_collision',
    'team_unresolved',
    'ambiguous_match',
    'malformed_identity'
  )),
  candidate_player_id uuid references players(id),
  raw_capture_id uuid references game_events(id),
  status text not null default 'open' check (status in ('open', 'resolved')),
  resolution_note text,
  detected_at timestamptz not null default now(),
  resolved_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint player_identity_quarantine_resolution_consistency
    check (
      (status = 'open' and resolved_at is null)
      or (status = 'resolved' and resolved_at is not null)
    )
);

create trigger trg_player_identity_quarantine_updated
  before update on player_identity_quarantine
  for each row execute function set_updated_at();

create unique index idx_player_identity_quarantine_open_identity
  on player_identity_quarantine (
    game_id,
    provider_name,
    (coalesce(provider_player_id, '~malformed~' || coalesce(raw_player_name, 'unknown')))
  )
  where status = 'open';

-- Supporting index for the future review workflow ("show me every open
-- case"), same partial-index shape as game_postgame_ingestion_state's
-- own eligible-rows index.
create index idx_player_identity_quarantine_open
  on player_identity_quarantine (detected_at)
  where status = 'open';

alter table player_identity_quarantine enable row level security;
