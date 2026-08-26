-- Milestone 5.4 (Postgame Review), Decisions BG-BZ (approved 2026-08-26).
--
-- Narrow schema inspection conclusion (required before this migration):
-- the legacy `postgame_reviews` table (Phase 4, Volume 3 §5) is left
-- completely untouched -- FK'd to the legacy `recommendations` cycle row,
-- no product/leg awareness, no append-only trigger, no deterministic
-- outcome column -- exactly the same "leave as legacy" treatment already
-- given to `explainability_payloads` (5.2) and `recommendation_snapshots`
-- (5.3). Its FK is not repointed, it is not deleted, and its existing
-- fixture row is not migrated (Decision BG).
--
-- Three new, additive, first-class-FK tables, not four and not one
-- polymorphic table:
--   1. recommendation_leg_grade_events    -- deterministic, per-leg
--   2. recommendation_product_grade_events -- deterministic, per-product rollup
--   3. recommendation_product_postgame_reviews -- narrative, per-product
--
-- Leg-scope and product-scope were kept as separate tables rather than
-- one grade_events table with nullable leg_id/product_id columns: a
-- single table would need a CHECK ensuring exactly one of two nullable
-- parent FKs is set, plus a rollup-only column (leg_outcome_counts) that
-- is meaningless for leg-scoped rows -- exactly the "ambiguous
-- nullable-parent design" the inspection was told to avoid. Two narrow,
-- fully-NOT-NULL-FK tables are cleaner. A separate `recommendation_leg_
-- postgame_reviews` narrative table was considered and rejected: nothing
-- in Volume 4's nine-question Explainability spec or this milestone's
-- approved decisions calls for a per-leg narrative (weather/injury/
-- agent-correctness narrative is naturally slate-of-legs-level, matching
-- the legacy `postgame_reviews` shape), so a fourth table would have had
-- no real consumer -- fewest tables that cleanly preserve the required
-- properties, not four because four names were listed.
--
-- Idempotent-retry vs. legitimate-regrade (Decision BQ) is solved at the
-- database level, not in application memory: a partial unique index on
-- (parent_id, grading_version) WHERE is_correction = false means a
-- worker's create-or-get for the ORIGINAL grade of a given version is
-- DB-enforced -- a crashed-and-retried worker hits this index and finds
-- the existing row rather than inserting a duplicate. A genuine
-- correction is a SEPARATE row with is_correction = true and
-- corrects_grade_event_id pointing at the row it supersedes, which the
-- partial index does not block -- so a legitimate regrade can always be
-- inserted, and a bare retry never can, all without the persistence
-- layer needing to remember anything between calls.
--
-- Time Machine integration (Decision BZ): `recommendation_legs`/
-- `recommendation_products` have no UPDATE path anywhere in this
-- codebase (grep-confirmed before writing this migration) -- every
-- bet-defining field (market_type/selection/point/decimal_odds/
-- ev_per_dollar/final_aggregate_confidence) is written once at creation
-- and never touched again. Grading therefore reads them directly as an
-- already-frozen source of truth; it does not need its own duplicate
-- copy of those fields. What grading DOES freeze, on the grade event
-- itself, is `authoritative_result` -- the exact final-score/stat facts
-- the grade was computed against -- so a stat correction landing after
-- this row exists can never retroactively change what this historical
-- grade "saw"; it can only ever be superseded by a new correction row.

-- ============================================================================
-- 1. Per-leg deterministic grade events (Decisions BI/BJ/BK/BP/BQ).
-- ============================================================================

create table recommendation_leg_grade_events (
  id uuid primary key default uuid_generate_v7(),
  recommendation_leg_id uuid not null references recommendation_legs(id),
  -- Denormalized from recommendation_legs.game_id (itself immutable, see
  -- above) purely for query ergonomics -- "find gradeable legs for game
  -- X" without a join -- matching this schema's existing convention of
  -- denormalizing frequently-joined FKs (recommendation_legs itself
  -- already carries both game_id and recommendation_id).
  game_id uuid not null references games(id),
  grading_version text not null,
  outcome text not null check (outcome in ('WIN', 'LOSS', 'PUSH', 'VOID_NO_ACTION', 'PENDING_MISSING_DATA')),
  -- Frozen copy of exactly the final-result facts this grade was computed
  -- against (e.g. {"final_score": {...}} for moneyline/spread/total, or
  -- the specific stat line for a player_prop) -- never a live pointer to
  -- mutable games.final_score/team_stats/player_stats.
  authoritative_result jsonb not null,
  graded_at timestamptz not null default now(),
  is_correction boolean not null default false,
  corrects_grade_event_id uuid references recommendation_leg_grade_events(id),
  correction_source text check (correction_source in ('stat_correction', 'grading_rule_change', 'manual_review')),
  correction_reason text,
  created_at timestamptz not null default now(),
  check (is_correction = false or corrects_grade_event_id is not null)
);

create unique index idx_leg_grade_events_original_per_version
  on recommendation_leg_grade_events (recommendation_leg_id, grading_version)
  where is_correction = false;

create index idx_leg_grade_events_game on recommendation_leg_grade_events (game_id);
create index idx_leg_grade_events_leg on recommendation_leg_grade_events (recommendation_leg_id);

create or replace function block_leg_grade_event_updates()
returns trigger as $$
begin
  raise exception 'recommendation_leg_grade_events is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_leg_grade_event_update
  before update on recommendation_leg_grade_events
  for each row execute function block_leg_grade_event_updates();

-- ============================================================================
-- 2. Per-product deterministic grade rollup (Decisions BI/BK/BL/BM/BP/BQ).
-- ============================================================================

create table recommendation_product_grade_events (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id),
  grading_version text not null,
  -- WIN/LOSS/PUSH/VOID_NO_ACTION/PENDING_MISSING_DATA mirror the single
  -- leg's own grade for a `single` product. NOT_APPLICABLE is the only
  -- legal outcome for no_bet/bankroll_preservation (Decisions BL/BM) --
  -- never a fabricated win/loss. MIXED_SETTLED is `multiple_singles`
  -- once every leg has a terminal grade; PENDING_MISSING_DATA also covers
  -- `multiple_singles` while any leg is still ungraded.
  outcome text not null check (
    outcome in ('WIN', 'LOSS', 'PUSH', 'VOID_NO_ACTION', 'PENDING_MISSING_DATA', 'NOT_APPLICABLE', 'MIXED_SETTLED')
  ),
  -- Derived/cached summary only (e.g. {"WIN": 3, "LOSS": 1}), meaningful
  -- only for multiple_singles -- always re-derivable by joining
  -- recommendation_legs.recommendation_product_id to the latest
  -- non-superseded row per leg in recommendation_leg_grade_events. Never
  -- the sole record of a leg's outcome -- that first-class identity lives
  -- in recommendation_leg_grade_events, not here.
  leg_outcome_counts jsonb,
  computed_at timestamptz not null default now(),
  is_correction boolean not null default false,
  corrects_grade_event_id uuid references recommendation_product_grade_events(id),
  correction_source text check (correction_source in ('stat_correction', 'grading_rule_change', 'manual_review')),
  correction_reason text,
  created_at timestamptz not null default now(),
  check (is_correction = false or corrects_grade_event_id is not null)
);

create unique index idx_product_grade_events_original_per_version
  on recommendation_product_grade_events (recommendation_product_id, grading_version)
  where is_correction = false;

create index idx_product_grade_events_product on recommendation_product_grade_events (recommendation_product_id);

create or replace function block_product_grade_event_updates()
returns trigger as $$
begin
  raise exception 'recommendation_product_grade_events is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_product_grade_event_update
  before update on recommendation_product_grade_events
  for each row execute function block_product_grade_event_updates();

-- ============================================================================
-- 3. Postgame Review narrative layer (Decisions BO/BS/BT/BU) -- strictly
--    downstream of a specific product_grade_event; the LLM never decides
--    or alters the grade it narrates.
-- ============================================================================

create table recommendation_product_postgame_reviews (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id),
  product_grade_event_id uuid not null references recommendation_product_grade_events(id),
  -- Denormalized from the referenced grade event, so this table's own
  -- append-only/versioning story is self-contained without always
  -- joining back to recommendation_product_grade_events.
  grading_version text not null,
  postgame_review_version text not null,
  outcome_summary text,
  why_it_won_or_lost text,
  -- Factual deltas only (weather/injury/line-movement changes between
  -- activation and kickoff) -- never a causal claim (Decision BS). No
  -- column here is named/shaped to hold an asserted cause.
  factual_deltas jsonb,
  -- Populated only when an agent's actual directional output can be
  -- objectively compared to the graded outcome (Decision BT) -- NULL
  -- when that comparison is unavailable, never a fabricated classification.
  correct_agents text[],
  underperforming_agents text[],
  learning_notes text,
  generated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create unique index idx_postgame_reviews_product_version
  on recommendation_product_postgame_reviews (recommendation_product_id, postgame_review_version);

create index idx_postgame_reviews_grade_event on recommendation_product_postgame_reviews (product_grade_event_id);

create or replace function block_product_postgame_review_updates()
returns trigger as $$
begin
  raise exception 'recommendation_product_postgame_reviews is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_product_postgame_review_update
  before update on recommendation_product_postgame_reviews
  for each row execute function block_product_postgame_review_updates();

-- ============================================================================
-- RLS -- same "enabled, no select policy, service-role only" convention
-- already applied to every non-user-facing table in this schema.
-- ============================================================================

alter table recommendation_leg_grade_events enable row level security;
alter table recommendation_product_grade_events enable row level security;
alter table recommendation_product_postgame_reviews enable row level security;
