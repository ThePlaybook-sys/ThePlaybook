-- Milestone 5.2 (Explainability Engine), Schema Option A (approved 2026-08-25):
-- additive only -- `explainability_payloads` (Phase 1, Volume 3 §5) is left
-- completely untouched (not repointed, not retrofitted, not deleted, its
-- existing row not migrated) because its sole FK target (`recommendations.id`,
-- the Phase 4 per-game container) has no path to the Phase 5 product layer
-- (`recommendation_products` can be slate-scoped; `recommendation_legs` are
-- leg-granular) and it has no append-only protection at all. Two new tables
-- instead, both FK'd first-class into the Milestone 5.1 layer, both
-- append-only -- the same pattern already used for the Phase 4 -> Phase 5.1
-- boundary itself.
--
-- Exactly one explanation row per product/leg, ever (UNIQUE + full-block
-- UPDATE trigger) -- not an open-ended version history. Every other
-- Time-Machine-relevant table in this schema that allows multiple rows per
-- parent does so because the underlying computation can legitimately differ
-- on a retry (an Elite second pass genuinely recomputes `consensus_snapshots`
-- differently). Explainability in Milestone 5.2 is 100% deterministic over
-- already-frozen Phase 4/5.1 facts -- the same product/leg can only ever
-- produce the same explanation, so a second row would never represent new
-- information, only a re-run. If a bug is later found in the deterministic
-- logic, the historical row stays wrong forever (same discipline already
-- applied to `recommendation_agent_outputs`/`recommendation_legs` -- never
-- patched in place); a fix changes what a NEW product's explanation looks
-- like, never rewrites history.

create table recommendation_product_explanations (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null unique references recommendation_products(id) on delete cascade,

  -- Always populated -- every product has a shape decision to explain.
  why_this_shape text not null,
  -- Nullable -- not every shape has an equally rich "why not X" story.
  why_not_other_shapes text,
  -- Structured backing for why_not_other_shapes on a no_bet product: every
  -- candidate evaluated for that game plus its RejectionReason(s)
  -- (app.features.strategy.RejectedCandidate). Empty '[]' for single/
  -- multiple_singles (their rejection story lives per-leg, see below) and
  -- for bankroll_preservation (its per-game detail already lives on each
  -- sibling no_bet product reachable via the same master_refresh_run_id --
  -- never duplicated here).
  rejected_alternatives jsonb not null default '[]'::jsonb,
  -- Nullable -- the two categorically-unavailable data sources (Sharp
  -- Money/Public Betting/referee, per Volume 3 §4.1) plus this cycle's
  -- committee-participation completeness, when computable.
  data_limitations text,
  -- Reserved for a future LLM narrative layer (NOT built in Milestone 5.2
  -- -- see Volume 4 §8's own narrative-vs-deterministic split). Populated,
  -- if ever, only at row-creation time by a future narrative-aware version
  -- of this pipeline -- never via a later UPDATE, since this table is
  -- append-only. A historical row generated before that layer existed
  -- keeps this NULL forever, honestly, rather than being retroactively
  -- enriched.
  narrative_summary text,

  created_at timestamptz not null default now()
);

create or replace function block_recommendation_product_explanation_updates()
returns trigger as $$
begin
  raise exception 'recommendation_product_explanations is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_recommendation_product_explanation_update
  before update on recommendation_product_explanations
  for each row execute function block_recommendation_product_explanation_updates();

create table recommendation_leg_explanations (
  id uuid primary key default uuid_generate_v7(),
  recommendation_leg_id uuid not null unique references recommendation_legs(id) on delete cascade,

  -- Always populated -- a leg exists only because it qualified; the
  -- qualification/ranking/conflict-resolution story is always computable.
  why_selected text not null,
  -- Always populated -- a qualifying leg always has at least the frozen
  -- EV/confidence facts to report, even if the supporting-agent list (see
  -- contributing_agents) happens to be thin.
  strongest_evidence text not null,
  -- Every VOTING game-level committee agent for this leg's candidate
  -- direction (app.features.consensus's own three-state lean_factor rule)
  -- -- never a configured-but-failed/deferred/non-participating agent,
  -- since those never produce a row in recommendation_agent_outputs at
  -- all. A rendered, frozen-at-write snapshot of already-first-class rows
  -- (recommendation_agent_outputs), exactly the same denormalization
  -- discipline already approved for `recommendation_snapshots.
  -- agent_outputs_snapshot` (Volume 3 §5) -- not a substitute for that
  -- first-class provenance, a point-in-time render of it.
  contributing_agents jsonb not null default '[]'::jsonb,
  -- Always populated -- includes the permanent historical_bet_type_variance
  -- unavailability disclosure (Milestone 4.6) unconditionally.
  biggest_risks text not null,
  -- The same-market candidate(s) this leg beat via the Decision AM ranking
  -- hierarchy (Decision AC conflict resolution) -- typically 0-1 entries.
  -- Same shape as the product-level column above.
  rejected_alternatives jsonb not null default '[]'::jsonb,
  -- NULL when no defensible deterministic condition exists (per Mac's
  -- explicit instruction: NULL is preferable to invented intelligence).
  -- When populated, verbatim-quotes the highest-weighted supporting
  -- committee agent's own `would_change_mind_if` field -- already-frozen
  -- agent output captured for exactly this purpose since Milestone 4.2,
  -- never synthesized by Explainability itself.
  would_change_mind_if text,
  -- Same reservation as the product-level column above.
  narrative_summary text,

  created_at timestamptz not null default now()
);

create or replace function block_recommendation_leg_explanation_updates()
returns trigger as $$
begin
  raise exception 'recommendation_leg_explanations is append-only and cannot be modified';
end;
$$ language plpgsql set search_path = public;

create trigger trg_block_recommendation_leg_explanation_update
  before update on recommendation_leg_explanations
  for each row execute function block_recommendation_leg_explanation_updates();

-- Shared data, not per-user -- same "RLS enabled, no select policy,
-- service-role only, consumed through the API Gateway" convention already
-- applied to recommendation_agent_outputs/consensus_snapshots/
-- recommendation_legs.
alter table recommendation_product_explanations enable row level security;
alter table recommendation_leg_explanations enable row level security;
