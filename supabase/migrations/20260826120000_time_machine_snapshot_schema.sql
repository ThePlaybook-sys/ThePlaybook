-- Milestone 5.3 (Time Machine / Recommendation Snapshots), Decisions AO-BE
-- (approved 2026-08-25): the legacy `recommendation_snapshots` (Phase 1,
-- Volume 3 §5) is left completely untouched -- one row per Phase 4
-- `recommendations.id`, giant JSONB blobs, zero rows, zero code, unfit
-- for the Phase 5 product/leg layer -- exactly the same "leave as legacy"
-- treatment already given to `explainability_payloads` in Milestone 5.2.
--
-- This migration instead adds a MANIFEST, not another duplicate-blob
-- snapshot table: `recommendation_activation_snapshots` composes
-- already-frozen Milestone 5.1/5.2 rows by reference (FK), never
-- duplicating odds/EV/confidence/explanation content a second time.
--
-- Also closes two real, live-verified provenance gaps found during the
-- Milestone 5.3 inspection (Decisions AT/AV): `consensus_snapshots` had
-- no DB-level append-only enforcement at all (convention-only, unlike
-- every sibling table), and no `recommendation_agent_outputs` row could
-- ever record which model/provider ACTUALLY produced it (only requested
-- routing configuration was knowable, never the real fallback outcome).

-- ============================================================================
-- 1. Activation snapshot manifest (Decision AO/AP) -- one row per
--    recommendation_products row, ever (UNIQUE + append-only).
-- ============================================================================

create table recommendation_activation_snapshots (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null unique references recommendation_products(id) on delete cascade,
  activated_at timestamptz not null default now(),
  -- Frozen at creation time (Decision AW) -- which Strategy Engine logic
  -- version decided this product's shape. Never inferred later.
  strategy_version text not null,
  -- Nullable -- a no_bet/bankroll_preservation product's own explanation
  -- always exists (Milestone 5.2 generates one for every product type),
  -- but this stays nullable rather than not-null so a future explanation
  -- failure (already isolated per-unit, Milestone 5.2) never blocks
  -- activation-snapshot creation for the underlying Strategy decision.
  recommendation_product_explanation_id uuid references recommendation_product_explanations(id),
  created_at timestamptz not null default now()
);

create or replace function block_activation_snapshot_updates()
returns trigger as $$
begin
  raise exception 'recommendation_activation_snapshots is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_activation_snapshot_update
  before update on recommendation_activation_snapshots
  for each row execute function block_activation_snapshot_updates();

-- ============================================================================
-- 2. Leg membership (Decision AO/AQ) -- normalized join table, never an
--    array/JSON column, preserving activation-time presentation order.
-- ============================================================================

create table recommendation_activation_snapshot_legs (
  id uuid primary key default uuid_generate_v7(),
  activation_snapshot_id uuid not null references recommendation_activation_snapshots(id) on delete cascade,
  recommendation_leg_id uuid not null references recommendation_legs(id),
  leg_order integer not null check (leg_order > 0),
  created_at timestamptz not null default now(),
  unique (activation_snapshot_id, recommendation_leg_id),
  unique (activation_snapshot_id, leg_order)
);

create or replace function block_activation_snapshot_leg_updates()
returns trigger as $$
begin
  raise exception 'recommendation_activation_snapshot_legs is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_activation_snapshot_leg_update
  before update on recommendation_activation_snapshot_legs
  for each row execute function block_activation_snapshot_leg_updates();

-- ============================================================================
-- 3. bankroll_preservation source-product membership (Decision AR) --
--    freezes the exact per-game no_bet products that constituted a
--    slate-level bankroll_preservation decision, rather than requiring a
--    future reader to rediscover them via master_refresh_run_id (which
--    could become ambiguous if more products are later associated with
--    the same run).
-- ============================================================================

create table recommendation_activation_snapshot_source_products (
  id uuid primary key default uuid_generate_v7(),
  activation_snapshot_id uuid not null references recommendation_activation_snapshots(id) on delete cascade,
  source_recommendation_product_id uuid not null references recommendation_products(id),
  created_at timestamptz not null default now(),
  unique (activation_snapshot_id, source_recommendation_product_id)
);

create or replace function block_activation_snapshot_source_product_updates()
returns trigger as $$
begin
  raise exception 'recommendation_activation_snapshot_source_products is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_activation_snapshot_source_product_update
  before update on recommendation_activation_snapshot_source_products
  for each row execute function block_activation_snapshot_source_product_updates();

-- ============================================================================
-- 4. Product lifecycle history (Decision AZ) -- append-only event log,
--    not a "current state only" column set. Only the lifecycle states
--    that already exist in the current product model (ACTIVATED,
--    WITHDRAWN, SOFT_DELETED) -- explicitly NOT the future BET NOW/WAIT/
--    PASS/LINE LOST execution states (Decision BE), which belong to the
--    not-yet-implemented Bet Timing & Execution Intelligence capability.
-- ============================================================================

create table recommendation_product_lifecycle_events (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id) on delete cascade,
  event_type text not null check (event_type in ('ACTIVATED', 'WITHDRAWN', 'SOFT_DELETED')),
  event_timestamp timestamptz not null default now(),
  reason text,
  created_at timestamptz not null default now()
);

create index idx_recommendation_product_lifecycle_events_product
  on recommendation_product_lifecycle_events (recommendation_product_id, event_timestamp);

create or replace function block_lifecycle_event_updates()
returns trigger as $$
begin
  raise exception 'recommendation_product_lifecycle_events is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_lifecycle_event_update
  before update on recommendation_product_lifecycle_events
  for each row execute function block_lifecycle_event_updates();

-- ============================================================================
-- 5. Per-agent-output model provenance (Decision AV) -- additive,
--    nullable columns, matching the `prompt_name`/`prompt_version`
--    (Milestone 4.8) precedent exactly. Historical rows written before
--    this migration remain NULL forever (backward-compatibility, per
--    Mac's explicit instruction) -- never backfilled with a guess.
--    `used_fallback` distinguishes "the originally requested primary
--    model produced this" from "the primary failed and the fallback
--    actually produced this" -- `model_name`/`provider` alone already
--    identify the ACTUAL producing model, but this makes the fallback
--    fact itself directly queryable without inferring it from routing
--    history that may since have changed.
-- ============================================================================

alter table recommendation_agent_outputs
  add column model_name text,
  add column provider text,
  add column used_fallback boolean;

-- No append-only trigger change needed: `block_agent_output_updates()`
-- already blocks every UPDATE unconditionally (verified live before this
-- migration was written) -- new nullable columns are populated only at
-- INSERT time, exactly like every other column on this table.

-- ============================================================================
-- 6. Explainability version (Decision AX) -- frozen on the actual
--    explanation rows themselves, not a separate/inferred location.
--    NOT NULL with a default: both tables are brand new (0 rows before
--    this migration, confirmed live), so there is no legacy-NULL
--    scenario to accommodate here, unlike the model-provenance columns
--    above. The application always sets this explicitly at insert time
--    regardless of the default (see app.features.explainability); the
--    default exists only as a defensive backstop.
-- ============================================================================

alter table recommendation_product_explanations
  add column explainability_version text not null default 'v1';

alter table recommendation_leg_explanations
  add column explainability_version text not null default 'v1';

-- ============================================================================
-- 7. consensus_snapshots immutability gap (Decision AT) -- closes a real
--    gap found during the Milestone 5.3 inspection: this table had no
--    DB-level append-only enforcement at all, unlike every sibling table
--    in the historical chain (`recommendation_agent_outputs`,
--    `recommendation_legs`, `recommendation_products`,
--    `recommendation_product_explanations`,
--    `recommendation_leg_explanations`). The Time Machine now references
--    `consensus_snapshots` as first-class historical evidence
--    (`recommendation_legs.consensus_snapshot_id`) -- convention alone is
--    no longer sufficient. Exact same trigger pattern as every other
--    append-only table in this schema, no new mechanism invented.
-- ============================================================================

create or replace function block_consensus_snapshot_updates()
returns trigger as $$
begin
  raise exception 'consensus_snapshots is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_consensus_snapshot_update
  before update on consensus_snapshots
  for each row execute function block_consensus_snapshot_updates();

-- ============================================================================
-- RLS -- same "enabled, no select policy, service-role only" convention
-- already applied to every non-user-facing table in this schema.
-- ============================================================================

alter table recommendation_activation_snapshots enable row level security;
alter table recommendation_activation_snapshot_legs enable row level security;
alter table recommendation_activation_snapshot_source_products enable row level security;
alter table recommendation_product_lifecycle_events enable row level security;
