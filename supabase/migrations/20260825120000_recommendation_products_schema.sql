-- Milestone 5.1 (Recommendation Strategy Engine), Phase 5 product layer
-- (Decisions P/Q/AF, approved 2026-08-25): the new, user-facing layer
-- ABOVE Phase 4's frozen `recommendations` table -- resolves the load-bearing
-- conflict between Volume 4 §9's multi-game/multi-candidate recommendation
-- shapes and Phase 4's one-row-per-game `recommendations` architecture by
-- preserving Phase 4 exactly (zero ALTER statements against any Phase 4
-- table in this migration) and building a distinct product layer with
-- first-class leg provenance -- never opaque JSON -- above it.
--
-- Five new tables: recommendation_products, recommendation_legs,
-- user_recommendation_selections, display_id_counters, conversations.
-- `conversation_messages` is deliberately NOT created here (Decision AH/AL --
-- deferred to Phase 6; the FK path it will need is unaffected by this
-- migration since it targets conversations(id), untouched here).
--
-- Finalized Strategy Engine rules this schema exists to support (Decisions
-- X/Y/Z/AA/AB/AC/AM/AN -- restated here for context, not re-decided):
--   * Qualification: final_aggregate_confidence >= 0.55 AND ev_per_dollar > 0
--     (both gates, never either alone).
--   * Ranking / tie-break / same-market conflict resolution, one hierarchy
--     for both purposes: ev_per_dollar DESC, final_aggregate_confidence DESC,
--     candidate_key ASC (purely for determinism, never a quality signal).
--   * no_bet is per-game (zero eligible candidates for that game).
--   * bankroll_preservation is slate-wide (zero eligible candidates anywhere
--     in the entire slate) -- no arbitrary percentage.
--   * same_game_parlay / multi_game_parlay stay schema-supported but
--     INACTIVE -- no correlation/joint-probability/combined-variance math
--     exists anywhere in this codebase (confirmed by grep, Decision AD/AN);
--     application code never writes these recommendation_type values in 5.1.

-- ============================================================================
-- recommendation_products
-- ============================================================================

create table recommendation_products (
  id uuid primary key default uuid_generate_v7(),
  display_id text not null unique,

  recommendation_type text not null check (recommendation_type in
    ('single','player_prop','multiple_singles','no_bet','bankroll_preservation',
     'same_game_parlay','multi_game_parlay')),
  scope text not null check (scope in ('game','slate')),

  -- game-scope: single/player_prop/no_bet/same_game_parlay -- anchored to
  -- exactly one game and one Phase 4 analysis cycle.
  -- slate-scope: multiple_singles/bankroll_preservation/multi_game_parlay --
  -- spans (or, for bankroll_preservation, rejects the whole of) one slate;
  -- no single game_id/recommendation_id applies.
  game_id uuid references games(id),
  recommendation_id uuid references recommendations(id),

  -- Always populated, both scopes -- first-class FK to the run that produced
  -- this product, rather than parsing recommendations.correlation_id
  -- (which string-encodes "run_id:game_id" but is not itself a reference).
  master_refresh_run_id uuid not null references master_refresh_runs(id),

  min_required_tier text not null default 'free',
  status text not null default 'active' check (status in ('active','withdrawn')),
  withdrawn_at timestamptz,
  withdrawal_reason text,
  deleted_at timestamptz,

  created_at timestamptz not null default now(),

  check (
    (scope = 'game'  and game_id is not null and recommendation_id is not null)
    or
    (scope = 'slate' and game_id is null     and recommendation_id is null)
  ),
  check (
    (recommendation_type in ('single','player_prop','no_bet','same_game_parlay') and scope = 'game')
    or
    (recommendation_type in ('multiple_singles','bankroll_preservation','multi_game_parlay') and scope = 'slate')
  ),
  check (status = 'active' or withdrawn_at is not null)
);

create index idx_recommendation_products_game on recommendation_products(game_id) where game_id is not null;
create index idx_recommendation_products_recommendation on recommendation_products(recommendation_id) where recommendation_id is not null;
create index idx_recommendation_products_run on recommendation_products(master_refresh_run_id);
create index idx_recommendation_products_status on recommendation_products(status) where status = 'active';
create index idx_recommendation_products_created on recommendation_products(created_at desc);

-- Deliberately NOT a full append-only block (unlike recommendation_legs
-- below): withdrawal is a legitimate, expected mutation, exactly mirroring
-- recommendations.withdrawn_at/withdrawal_reason's existing Phase 4 pattern.
-- Every OTHER column is frozen -- this trigger proves that at the DB level
-- rather than trusting the application layer.
create or replace function block_recommendation_product_mutation()
returns trigger as $$
begin
  if (new.recommendation_type, new.scope, new.game_id, new.recommendation_id,
      new.master_refresh_run_id, new.min_required_tier, new.display_id, new.created_at)
     is distinct from
     (old.recommendation_type, old.scope, old.game_id, old.recommendation_id,
      old.master_refresh_run_id, old.min_required_tier, old.display_id, old.created_at)
  then
    raise exception 'recommendation_products: only status/withdrawn_at/withdrawal_reason/deleted_at may be updated';
  end if;
  return new;
end;
$$ language plpgsql;

create trigger trg_block_recommendation_product_mutation
  before update on recommendation_products
  for each row execute function block_recommendation_product_mutation();

-- ============================================================================
-- recommendation_legs
-- ============================================================================
--
-- Represents ONLY actually-selected wager legs (explicit correction, approved
-- 2026-08-25): no candidate_key=NULL placeholder rows for "considered but
-- not selected" candidates. no_bet/bankroll_preservation products have ZERO
-- rows here -- their provenance is recommendation_products.recommendation_id
-- / .master_refresh_run_id directly (see above), never a fake leg.

create table recommendation_legs (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id) on delete cascade,

  -- The exact frozen candidate evaluation this leg was selected from.
  -- consensus_snapshots has NO uniqueness on (recommendation_id,
  -- candidate_key) -- an Elite second-pass writes a NEW row rather than
  -- updating -- so anchoring to the specific snapshot id (not the pair) is
  -- required to unambiguously identify which pass's numbers a leg claims.
  consensus_snapshot_id uuid not null references consensus_snapshots(id),

  -- Denormalized from the consensus_snapshot's own chain, so a leg listing
  -- never needs a join to know which game/analysis-cycle it belongs to.
  game_id uuid not null references games(id),
  recommendation_id uuid not null references recommendations(id),
  candidate_key text not null,

  -- Frozen copies (Invariant 7) -- never live references that could change
  -- out from under a historical leg.
  market_type text not null check (market_type in ('moneyline','spread','total','prop')),
  selection text not null,
  sportsbook text not null,
  american_odds integer not null,
  point numeric(6,2),
  decimal_odds numeric(8,4) not null,
  ev_per_dollar numeric(8,4) not null check (ev_per_dollar > 0),
  final_aggregate_confidence numeric(5,4) not null check (final_aggregate_confidence >= 0.55),

  leg_order integer not null default 1 check (leg_order > 0),
  created_at timestamptz not null default now(),

  -- Supports the composite FK from user_recommendation_selections, so a
  -- personalization row's (leg, product) pair is DB-verified consistent.
  unique (id, recommendation_product_id),
  unique (recommendation_product_id, leg_order),
  unique (recommendation_product_id, candidate_key)
);

-- Decision AC, DB-enforced: at most one leg per (product, game, directional
-- market) -- home ML and away ML can never both appear in the same product.
-- Player props are excluded on purpose: distinct props on the same game are
-- not "opposing sides" of one market, so multiple are legitimately allowed.
create unique index idx_recommendation_legs_one_per_market
  on recommendation_legs (recommendation_product_id, game_id, market_type)
  where market_type in ('moneyline','spread','total');

create index idx_recommendation_legs_product on recommendation_legs(recommendation_product_id);
create index idx_recommendation_legs_game on recommendation_legs(game_id);
create index idx_recommendation_legs_consensus_snapshot on recommendation_legs(consensus_snapshot_id);
create index idx_recommendation_legs_candidate_key on recommendation_legs(candidate_key);

-- No legitimate mutable field exists on a leg at all -- full block, exactly
-- mirroring recommendation_agent_outputs' own block_agent_output_updates.
create or replace function block_recommendation_leg_updates()
returns trigger as $$
begin
  raise exception 'recommendation_legs is append-only and cannot be modified';
end;
$$ language plpgsql;

create trigger trg_block_recommendation_leg_update
  before update on recommendation_legs
  for each row execute function block_recommendation_leg_updates();

-- ============================================================================
-- user_recommendation_selections
-- ============================================================================
--
-- Decision AK (approved 2026-08-25): append-only, never overwritten -- but
-- must not create a new row for an unchanged repeat view/refresh. The
-- materiality gate below is a genuinely atomic Postgres mechanism (advisory
-- transaction lock + compare-against-latest, both inside one BEFORE INSERT
-- trigger invocation), not an application-level read-then-write race.
--
-- recommendation_leg_id is nullable: NULL represents product-level-only
-- personalization (no_bet/bankroll_preservation's session-preference /
-- exclusion state, no Kelly math applies); set, it represents one leg's
-- personalized stake within a (possibly multi-leg) product.

create table user_recommendation_selections (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id) on delete cascade,
  recommendation_leg_id uuid references recommendation_legs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,

  -- Frozen copies of the user's state AT COMPUTATION TIME (Invariant 7's
  -- same discipline applied to personalization) -- never a live join back to
  -- user_profiles that could silently change history.
  risk_tolerance text not null check (risk_tolerance in ('conservative','moderate','aggressive')),
  bankroll_at_computation numeric(12,2),
  excluded_by_session_preferences boolean not null default false,

  full_kelly_fraction numeric(8,6),
  quarter_kelly_fraction numeric(8,6),
  risk_tolerance_multiplier numeric(5,4),
  stake numeric(10,2),

  created_at timestamptz not null default now(),

  foreign key (recommendation_leg_id, recommendation_product_id)
    references recommendation_legs(id, recommendation_product_id) on delete cascade,

  check (
    recommendation_leg_id is not null
    or (full_kelly_fraction is null and quarter_kelly_fraction is null
        and risk_tolerance_multiplier is null and stake is null)
  )
);

create index idx_urs_latest_lookup
  on user_recommendation_selections (user_id, recommendation_product_id, recommendation_leg_id, created_at desc);

-- Materiality gate. pg_advisory_xact_lock serializes concurrent writers for
-- the SAME (user, product, leg) key for the duration of the transaction --
-- a second writer for that key only runs its own comparison after the first
-- commits or rolls back, so it always compares against the true latest row,
-- never a stale snapshot captured before blocking. Writers for DIFFERENT
-- keys never contend. Returning NULL from a BEFORE INSERT trigger silently
-- suppresses the insert entirely -- the standard Postgres primitive for
-- exactly this "no-op on no-change" pattern.
--
-- Compares only against the LATEST row for the key, not "any row ever" --
-- required for correct Time Machine reconstruction. A user going
-- moderate -> aggressive -> moderate must record that second "moderate" as
-- a genuine new observation even though identical content existed earlier;
-- a plain content-based uniqueness constraint would wrongly suppress it and
-- corrupt "what was true as of time T" for every T after the real revert.
create or replace function enforce_urs_materiality()
returns trigger as $$
declare
  latest record;
begin
  perform pg_advisory_xact_lock(
    hashtextextended(new.user_id::text || ':' || new.recommendation_product_id::text
                      || ':' || coalesce(new.recommendation_leg_id::text, 'none'), 0)
  );

  select risk_tolerance, bankroll_at_computation, excluded_by_session_preferences, stake
    into latest
    from user_recommendation_selections
   where user_id = new.user_id
     and recommendation_product_id = new.recommendation_product_id
     and recommendation_leg_id is not distinct from new.recommendation_leg_id
   order by created_at desc
   limit 1;

  if found
     and latest.risk_tolerance = new.risk_tolerance
     and latest.bankroll_at_computation is not distinct from new.bankroll_at_computation
     and latest.excluded_by_session_preferences = new.excluded_by_session_preferences
     and latest.stake is not distinct from new.stake
  then
    return null;
  end if;

  return new;
end;
$$ language plpgsql;

create trigger trg_enforce_urs_materiality
  before insert on user_recommendation_selections
  for each row execute function enforce_urs_materiality();

create or replace function block_urs_updates()
returns trigger as $$
begin
  raise exception 'user_recommendation_selections is append-only and cannot be modified';
end;
$$ language plpgsql;

create trigger trg_block_urs_update
  before update on user_recommendation_selections
  for each row execute function block_urs_updates();

-- ============================================================================
-- display_id_counters
-- ============================================================================
--
-- Proven atomic generation (not the read-then-write proposal this replaces):
-- a single `INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING` statement,
-- issued by application code with no separate prior read. The row lock
-- backing the ON CONFLICT/DO UPDATE path is acquired as an intrinsic part of
-- executing that one statement -- there is no gap between "observe the
-- current counter" and "commit the increment" for a second transaction to
-- land in. A second concurrent caller for the same bucket_key blocks on that
-- row's lock, then (Postgres's standard read-committed UPDATE re-check
-- semantics) re-evaluates `counter + 1` against the value the FIRST
-- transaction actually committed, never a value cached before blocking.
-- Two simultaneous activations for the same bucket therefore cannot receive
-- the same counter value. A crash between the increment and the product
-- insert leaves a gap, never a collision -- no-gaps was never a requirement.
--
--   insert into display_id_counters (bucket_key, counter, updated_at)
--   values ($1, 1, now())
--   on conflict (bucket_key)
--   do update set counter = display_id_counters.counter + 1, updated_at = now()
--   returning counter;
--
-- bucket_key is application-supplied (currently the 4-digit activation
-- year, e.g. '2026') -- a policy choice, deliberately decoupled from the
-- atomicity mechanism above so the bucketing convention can evolve later
-- without touching this proof.

create table display_id_counters (
  bucket_key text primary key,
  counter integer not null default 0,
  updated_at timestamptz not null default now()
);

-- ============================================================================
-- conversations
-- ============================================================================
--
-- Decision AH/AL (approved 2026-08-25): minimal shape now, built exactly to
-- Volume 4 §7's / the v3.0 amendment's own SQL (session_preferences is a
-- COLUMN on conversations, not a separate table -- correcting my own prior
-- "conversations/session_preferences" phrasing). conversation_messages is
-- deliberately NOT created here -- deferred to Phase 6 -- but nothing here
-- forecloses or complicates adding it later: its FK will simply target
-- conversations(id), untouched by this migration.
--
-- What Milestone 5.1 actually needs this for: the Strategy Engine may read
-- session_preferences from a user's most recent conversation (if any) and
-- fold an exclusion into user_recommendation_selections
-- .excluded_by_session_preferences. No NL Engine, no intent classification,
-- no chat UI is built as part of this migration or this milestone.

create table conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_preferences jsonb not null default '{}',
  created_at timestamptz not null default now()
);
create index idx_conversations_user on conversations(user_id, created_at desc);

-- ============================================================================
-- Row Level Security
-- ============================================================================

alter table recommendation_products enable row level security;
create policy "recommendation_products_tier_gated_select" on recommendation_products
  for select using (
    deleted_at is null
    and (
      min_required_tier = 'free'
      or exists (
        select 1 from subscriptions s
        where s.user_id = auth.uid() and s.status = 'active'
          and ((min_required_tier = 'pro' and s.tier in ('pro','elite','syndicate'))
            or (min_required_tier = 'elite' and s.tier in ('elite','syndicate')))
      )
    )
  );

-- recommendation_legs: shared candidate data, not itself a per-user object --
-- same "RLS enabled, no select policy, service-role only, consumed through
-- API Gateway" convention already applied to recommendation_agent_outputs /
-- consensus_snapshots / explainability_payloads / recommendation_snapshots.
-- The frontend reads legs through recommendation_products.
alter table recommendation_legs enable row level security;

alter table user_recommendation_selections enable row level security;
create policy "own_recommendation_selections_select" on user_recommendation_selections
  for select using (auth.uid() = user_id);

-- display_id_counters: internal counter, not user data -- same
-- enabled-no-policy convention.
alter table display_id_counters enable row level security;

alter table conversations enable row level security;
create policy "own_conversations_select" on conversations
  for select using (auth.uid() = user_id);
