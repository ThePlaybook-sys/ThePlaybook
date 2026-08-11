# The Playbook — Volume 3
## Database Architecture: Tables, Relationships, Indexes, Triggers, Migrations, RLS

**Version:** v4.3
**Last updated:** 2026-08-10
**Depends on:** Volume 1 (v3.0 — tiers, personas, principles) and Volume 2 (v4.2 — service shape, routing table reference, RLS placeholder, scoped event system, Redis cache layer, Postgame Ingestion Worker)
**v4.0 note:** Normalized multi-sport core added (§4.0) — `sports`/`leagues`/`seasons`/`teams`/`players`/`player_stats`/`team_stats` plus the `player_stats_nfl` extension pattern. `games` gains `sport_id`/`league_id`/`season_id` while the legacy `sport` text field is kept, deprecated, for Phase 0/1 backward compatibility. Data quality metadata convention added to `daily_game_intelligence` (§4.1). See `CHANGELOG.md` v4.0 entry for full reasoning.
**v4.1.1 note (PATCH):** §10 gained a clarification that its RLS scope covers "every table requiring access control," not only tables containing per-user data (Phase 1 Milestone 2). The three tables named in the v2.0 UUIDv7 amendment (`odds_snapshots`, `recommendation_agent_outputs`, `market_monitoring_events`) use a custom `uuid_generate_v7()` function, since the deployed Postgres version predates native `uuidv7()` support. See `CHANGELOG.md` v4.1.1 entry for full reasoning.
**v4.2 note (MINOR):** §3's `user_profiles.jurisdiction_state` relaxed from `not null` to nullable — Phase 2's signup trigger creates the row before onboarding (where jurisdiction is actually collected) ever runs. The `not null` *intent* is now enforced at the application layer. See `CHANGELOG.md` v4.2 entry for full reasoning.
**v4.3 note (MINOR):** §6 gains the Stat Correction ↔ Bet Settlement Policy — Phase 5 grading/outcome policy, documented now so Phase 3's postgame architecture doesn't foreclose it later. No schema changed; one real gap (`verified_bets` has no settlement-history/versioning pattern) identified and explicitly deferred to Phase 5. See `CHANGELOG.md` v4.3 entry for full reasoning.
**Read next:** Volume 4 (AI Intelligence) — the agent, consensus, and orchestration tables defined here are the tables Volume 4's logic reads and writes

---

## 1. Data Architecture Principles

Three requirements from Volumes 1 and 2 drive every schema decision below, so they're worth restating as hard constraints before the tables:

1. **Reproducibility (Time Machine).** Every recommendation must be reconstructible months later — exact odds, injuries, weather, agent outputs, and reasoning at the moment it was made. This means **snapshot tables, not just foreign keys to live data.** If `recommendations` only pointed at `games.current_odds`, that value would drift as odds moved, and the reconstruction would show wrong data. Anywhere reproducibility matters, we store a frozen copy, not a reference.
2. **Tier gating is structural, not just UI-level.** Volume 1 established subscription tiers control feature access. That access needs to be enforceable at the database layer via RLS, not just hidden in the frontend — otherwise a user could hit the API directly and see Elite-only data on a Free plan.
3. **Performance attribution must never mix.** Master spec requirement, carried from Volume 1: AI Performance, Projected User Performance, and Verified User Performance are three separate concepts and need three separate tables — never one table with a "type" column that invites accidental blending in a query.

---

## 2. Schema Overview

```
auth.users (Supabase-managed)
   │
   ├── user_profiles ──── betting_dna
   │        │
   │        └── subscriptions
   │
   ├── conversations ──── conversation_messages
   ├── bet_slips
   └── notifications

games ──── odds_snapshots
   │
   └── recommendations ──── recommendation_agent_outputs ──── agents
            │                                                    │
            ├── consensus_snapshots                    agent_performance_scores
            ├── explainability_payloads
            ├── recommendation_snapshots (Time Machine)
            └── postgame_reviews

verified_bets ──── recommendations (nullable link)
projected_performance ──── recommendations + user_profiles

model_routing_rules (standalone config table, read by Orchestrator)
market_monitoring_events ──── games
audit_log (standalone, append-only)
```

---

## 3. Core User & Account Tables

Supabase provides `auth.users` (id, email, encrypted password, etc.) automatically — we never duplicate auth fields. Everything below extends it via foreign key on `auth.users.id`.

### `user_profiles`
```sql
create table user_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  jurisdiction_state text,                 -- v4.2: nullable — collected at onboarding (Phase 2
                                            -- Milestone 4), not at signup; null until then. The
                                            -- "not null" *intent* (Volume 1 §10's early jurisdiction
                                            -- gating) is enforced at the application layer instead —
                                            -- no bet-relevant action is permitted while this is null.
  persona_classification text check (persona_classification in ('grinder','casual','numbers_person', null)),
  betting_experience text check (betting_experience in ('new','casual','experienced')),
  primary_goal text check (primary_goal in ('fun','disciplined_longterm','edge_seeking')),
  risk_tolerance text check (risk_tolerance in ('conservative','moderate','aggressive')),
  preferred_unit_size numeric(10,2),
  max_parlay_legs integer default 0,        -- 0 = no parlays, per master spec explicit option
  optional_bankroll numeric(12,2),
  onboarding_completed_at timestamptz,
  referral_code text unique,                -- v2.0: cheap to add now, avoids a later migration; program mechanics TBD per Volume 1 §9.1
  deleted_at timestamptz,                   -- v2.0: soft delete, see §10 for RLS filtering
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index idx_user_profiles_persona on user_profiles(persona_classification);
```
**Why `jurisdiction_state` is nullable, not `not null` (revised v4.2):** originally specified `not null` so Volume 1 §10's early jurisdiction gating would be enforced at the schema level. Phase 2 found this couldn't survive contact with the DB-trigger-based signup flow (Mac's chosen implementation for auto-creating `user_profiles` on `auth.users` INSERT, matching Phase 1's DB-enforcement pattern): the trigger fires at signup, before onboarding — where jurisdiction is actually collected — ever runs, so no jurisdiction value exists yet to satisfy a `not null` constraint at that moment. Relaxed to nullable; the gating *intent* is enforced at the application layer instead — every bet-relevant endpoint requires `jurisdiction_state is not null` before proceeding, and the onboarding-completion endpoint (Phase 2 Milestone 4) is the only path that ever sets it. See `CHANGELOG.md` v4.1.1 (cont.) / next entry for full reasoning.

**Why `referral_code` exists with no referral program logic behind it yet (v2.0):** per Volume 1 §9.1, the field is added now specifically to avoid a schema migration later, while the actual incentive mechanics wait for real Persona A retention data. Adding the column costs nothing; adding it retroactively after users exist would require a backfill.

### `subscriptions`
```sql
create table subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  tier text not null check (tier in ('free','pro','elite','syndicate')),
  status text not null check (status in ('active','past_due','canceled','trialing')),
  billing_period text check (billing_period in ('monthly','annual')),
  current_period_start timestamptz,
  current_period_end timestamptz,
  external_billing_id text,                 -- Stripe subscription ID
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index idx_subscriptions_user on subscriptions(user_id);
create index idx_subscriptions_status on subscriptions(status) where status = 'active';
```
**Why a separate table instead of a `tier` column on `user_profiles`:** subscriptions have their own lifecycle (trialing → active → past_due → canceled) independent of the profile, and a user could theoretically have subscription history worth preserving. Keeping it separate also means Volume 2's rate-limiting logic can query this table alone without touching profile data.

### `betting_dna`
```sql
create table betting_dna (
  user_id uuid primary key references auth.users(id) on delete cascade,
  favorite_sportsbooks text[],
  observed_bet_types text[],
  observed_avg_odds numeric(6,2),
  observed_risk_tendency text,
  observed_frequency text,                  -- e.g. 'daily','weekly','game-day-only'
  favorite_sports text[],
  last_recalculated_at timestamptz default now()
);
```
This table is written to by a background worker (Volume 2, Section 4.4), never directly by user input — onboarding answers live in `user_profiles`; **observed** behavior lives here, and per Volume 1 Section 6, observed behavior should gradually outweigh onboarding assumptions. Keeping them in separate tables makes that blending logic explicit in application code rather than ambiguous in one shared table.

---

## 4. Sports Data Tables (Sports Intelligence Layer's Storage)

### 4.0 Normalized Multi-Sport Core (v4.0)

Added ahead of Phase 1 starting, specifically because this is the last point where introducing it is cheap — per the master spec's own multi-sport scalability requirement (NBA, MLB, NHL, etc. are named future launches in Volume 1), building on a single hardcoded `sport` field now would mean a much more expensive migration later, once real data and RLS policies depend on it.

```sql
create table sports (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,          -- 'nfl', 'nba', 'mlb', etc.
  name text not null
);

create table leagues (
  id uuid primary key default gen_random_uuid(),
  sport_id uuid not null references sports(id),
  code text not null,
  name text not null
);

create table seasons (
  id uuid primary key default gen_random_uuid(),
  league_id uuid not null references leagues(id),
  year integer not null,
  start_date date,
  end_date date
);

create table teams (
  id uuid primary key default gen_random_uuid(),
  league_id uuid not null references leagues(id),
  name text not null,
  external_provider_id text
);

create table players (
  id uuid primary key default gen_random_uuid(),
  team_id uuid references teams(id),
  name text not null,
  position text,
  external_provider_id text
);

create table player_stats (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references players(id),
  game_id uuid not null references games(id),
  stats jsonb not null,               -- common cross-sport fields only
  created_at timestamptz default now()
);

create table team_stats (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references teams(id),
  game_id uuid not null references games(id),
  stats jsonb not null,
  created_at timestamptz default now()
);

-- Sport-specific extension pattern (NFL only at launch, per Volume 1's NFL-only scope —
-- NBA/MLB extension tables get added when those sports actually enter planning, not before)
create table player_stats_nfl (
  player_stat_id uuid primary key references player_stats(id) on delete cascade,
  passing_yards integer,
  receiving_yards integer,
  rushing_yards integer,
  interceptions integer,
  sacks integer
);
```

**Why extension tables instead of one wide table with every sport's columns:** a `player_stats` row with 40 mostly-null columns (passing yards for a basketball player, rebounds for a quarterback) is exactly the maintenance problem Section 1's principles warn against — every new sport would mean altering one increasingly unwieldy shared table. The extension pattern means adding NBA later is a new table (`player_stats_nba`) and zero changes to the existing NFL data or code path.

### `games` (updated, v4.0 — backward-compatible transition)
```sql
create table games (
  id uuid primary key default gen_random_uuid(),
  external_provider_id text not null,       -- ID from the provider adapter, for traceability
  sport_id uuid references sports(id),      -- v4.0: normalized reference
  league_id uuid references leagues(id),    -- v4.0
  season_id uuid references seasons(id),    -- v4.0
  sport text not null default 'nfl',        -- LEGACY — deprecated, kept for Phase 0 backward compatibility
  home_team text not null,
  away_team text not null,
  scheduled_start timestamptz not null,
  stadium text,
  status text check (status in ('scheduled','live','final','postponed','canceled')),
  final_score jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index idx_games_scheduled on games(scheduled_start);
create index idx_games_status on games(status) where status in ('scheduled','live');
create index idx_games_sport on games(sport_id);
```
**Migration policy (approved with this modification):** the legacy `sport` text field is *not* removed now. Both fields coexist through Phase 0 and Phase 1 — new code paths should populate and read `sport_id`, but nothing currently depending on the `sport` text column breaks. `sport` is formally marked deprecated here, scheduled for removal once the NFL migration to the normalized model is verified complete (a Phase 1 acceptance criterion, not a later cleanup task left to drift). This trades a small amount of temporary duplication for zero Phase-0 disruption — the same reasoning that's governed every other schema decision in this document.

### `odds_snapshots`
```sql
create table odds_snapshots (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  sportsbook text not null,
  market_type text not null,                -- 'moneyline','spread','total','prop'
  line_data jsonb not null,                 -- full odds payload, normalized shape from adapter
  captured_at timestamptz not null default now()
);
create index idx_odds_game_time on odds_snapshots(game_id, captured_at desc);
```
**Append-only by design.** We never update an odds row — every line movement is a new row. This is what makes Closing Line Value calculation and the Market Monitoring Engine's "did anything change since we recommended this" check possible without any extra tracking logic.

Additional supporting tables follow the same append-only-snapshot pattern and are listed rather than fully specified here (each mirrors the shape of `odds_snapshots`, keyed to `game_id`, with a `captured_at` timestamp): `injury_reports`, `weather_snapshots`, `depth_chart_snapshots`, `referee_assignments`.

### 4.1 `daily_game_intelligence` — Master Working Table (v3.0)

A pre-assembled, denormalized table built by the Master Refresh worker (Volume 2 §8) each morning, combining that day's games with all currently-known intelligence into one row per game — the single place every agent (Volume 4 §2) looks first before separately querying the supporting tables above.

```sql
create table daily_game_intelligence (
  game_id uuid primary key references games(id) on delete cascade,
  teams jsonb,
  players jsonb,
  odds jsonb,
  props jsonb,
  weather jsonb,
  injuries jsonb,
  news jsonb,
  travel jsonb,
  rest jsonb,
  stadium jsonb,
  public_betting jsonb,
  sharp_money jsonb,
  ai_scores jsonb,                -- references the derived score tables below
  momentum jsonb,
  matchup_ratings jsonb,
  ev_calculations jsonb,
  confidence_scores jsonb,
  recommendation_candidates jsonb,
  last_updated timestamptz default now()
);
```

**Why this doesn't undermine the Time Machine principle from §1, even though it looks like it might at first glance:** this is explicitly a *working* table, continuously overwritten as the day's data refreshes — it is **not** a source of truth for historical reconstruction. When a recommendation is created, `recommendation_snapshots` (§5 below) still freezes a copy of everything relevant at that exact moment, exactly as before this addition. `daily_game_intelligence` exists purely so agents don't have to separately query eight tables on every single request — a performance optimization sitting *upstream* of the reproducibility architecture, not a replacement for it. Months later, reconstructing a recommendation still reads `recommendation_snapshots`, never this table, which by then has long since been overwritten with unrelated days' data.

**Data quality metadata convention (v4.0).** Every jsonb category above (`weather`, `injuries`, `odds`, etc.) follows the same embedded metadata shape rather than storing a bare value:
```json
{
  "value": { "...category-specific fields..." },
  "source": "WeatherAPI",
  "confidence": 0.99,
  "last_updated": "2026-08-06T10:03:00Z",
  "status": "fresh"          // fresh | needs_refresh | stale
}
```
`status` is computed against the cadence table in Volume 2 §8 — e.g. weather is `needs_refresh` once it exceeds its 15-minute cadence without a successful update. This is what makes the AI Transparency Meter's `data_quality` dimension (Volume 5 §5) a real, per-category number instead of one vague freshness score for the whole recommendation, and it's what lets an agent (or the Meta Agent, Volume 4 §2.6) reason explicitly about *which specific inputs* were stale rather than treating the whole packet as uniformly trustworthy or not.

### 4.2 Derived Intelligence Score Tables (v3.0)

Feed the `ai_scores` field above. Each follows the same simple shape, keyed to `game_id`, refreshed alongside the Master Refresh worker:
```sql
create table weather_scores (
  game_id uuid references games(id) on delete cascade,
  score numeric(5,4),
  calculated_at timestamptz default now(),
  primary key (game_id, calculated_at)
);
-- identical shape repeated for: injury_scores, travel_scores, rest_scores,
-- momentum_scores, matchup_scores, line_value_scores, sharp_money_scores,
-- schedule_difficulty_scores, offensive_matchup_scores, defensive_matchup_scores,
-- coaching_edge_scores, public_sentiment_scores
```
Deliberately kept as separate tables rather than folded directly into `daily_game_intelligence` alone, so each score's calculation can be independently tested, versioned, and eventually fed into the Continuous Learning Engine's evaluation of which score types actually correlate with agent accuracy (Volume 4 §10) — a question that's only answerable if each score has its own queryable history.

---

## 5. AI Intelligence Tables

### `agents`
```sql
create table agents (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,                -- e.g. 'injury_intelligence_agent'
  category text,
  active boolean default true,
  current_weight numeric(5,4) default 1.0,  -- adaptive weighting, Volume 4 owns the algorithm
  created_at timestamptz default now()
);
```

### `agent_performance_scores`
```sql
create table agent_performance_scores (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references agents(id),
  evaluation_window_start date not null,
  evaluation_window_end date not null,
  roi numeric(8,4),
  ev numeric(8,4),
  clv numeric(8,4),
  confidence_calibration_score numeric(5,4),
  sample_size integer not null,             -- required: Volume 1 principle — never reweight on isolated wins
  created_at timestamptz default now()
);
create index idx_agent_perf_agent_window on agent_performance_scores(agent_id, evaluation_window_end desc);
```
**Why `sample_size` is required and not optional:** the master spec explicitly requires "sustained statistical evidence" before adjusting agent influence. Making `sample_size` a required field forces the weighting algorithm (Volume 4) to always have this number available and gives us a place to enforce a minimum-sample-size check before any weight update — this is a schema-level guardrail against overfitting, not just a policy.

### `recommendations`
```sql
create table recommendations (
  id uuid primary key default gen_random_uuid(),
  game_id uuid references games(id),
  user_facing boolean default true,          -- false = internal/test recommendation
  recommendation_type text check (recommendation_type in
    ('single','player_prop','same_game_parlay','multi_game_parlay','multiple_singles','no_bet')),
  bet_details jsonb,                         -- null when type = 'no_bet'
  confidence_score numeric(5,4),
  expected_value numeric(8,4),
  risk_level text check (risk_level in ('low','moderate','high')),
  status text check (status in ('active','withdrawn','settled_win','settled_loss','settled_push')),
  min_required_tier text default 'free',     -- ties to Volume 1 tier gating, enforced via RLS below
  ai_version text not null default 'v1',     -- v2.0: which AI architecture version produced this
  prompt_version text,                       -- v2.0: FK-conceptual reference to prompt_registry
  agent_version text,                        -- v2.0
  consensus_version text,                    -- v2.0
  weight_version text,                       -- v2.0
  deleted_at timestamptz,                    -- v2.0: soft delete, see §10
  display_id text unique,                    -- v3.0: human-readable, e.g. PB-2026-NFL-000234
  created_at timestamptz default now(),
  withdrawn_at timestamptz,
  withdrawal_reason text
);
create index idx_recs_game on recommendations(game_id);
create index idx_recs_status on recommendations(status) where status = 'active';
create index idx_recs_created on recommendations(created_at desc);
```
**`recommendation_type` includes `'no_bet'` as a first-class value, not an absence of a row.** This matters more than it looks like it should: Volume 1's core principle is that "No Bet Today" is a celebrated, trackable output. If a no-bet day simply meant no row existed, we'd have no way to show a user "here's why we didn't recommend anything today" or to measure how often the AI correctly holds back — a metric Volume 1 explicitly wants tracked (Section 8, Elite upgrade rate after a no-bet day).

**Why five separate versioning columns instead of one `version` field (v2.0):** the AI architecture doesn't move as one unit — a prompt can change without the consensus math changing, agent weights recalculate on their own schedule independent of either. Collapsing these into a single version number would hide exactly the kind of information the Time Machine principle exists to preserve: months later, "what changed" needs to be answerable at the level of *which specific thing* changed, not just "something changed." `prompt_version` and `agent_version` are populated by the Orchestrator at the moment of creation from whatever `prompt_registry` and `agents.current_weight` state was actually in effect — frozen at write time, same pattern as `weight_applied` on `recommendation_agent_outputs` below.

**`display_id` (v3.0):** generated at creation time by a simple sequence-per-sport-per-year function, format `PB-{year}-{sport}-{sequence}`. Purely a UX/support convenience — `id` (the UUID) remains the actual primary key and foreign key target everywhere; `display_id` is what a user sees and what support references, so nobody's pasting UUIDs into a support ticket.

### `recommendation_agent_outputs`
```sql
create table recommendation_agent_outputs (
  id uuid primary key default gen_random_uuid(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  agent_id uuid not null references agents(id),
  raw_output jsonb not null,
  agent_confidence numeric(5,4),
  weight_applied numeric(5,4) not null,      -- snapshot of the agent's weight AT THIS MOMENT
  created_at timestamptz default now()
);
create index idx_rao_recommendation on recommendation_agent_outputs(recommendation_id);
```
**`weight_applied` is a frozen copy of `agents.current_weight`, not a join.** This is a direct Time Machine requirement: if we only stored a reference to `agents.current_weight`, reconstructing a recommendation from three months ago would show *today's* weight, not the weight that was actually used to compute the consensus at the time — silently rewriting history. Every place this pattern applies (odds, weights, anything mutable) uses the same frozen-copy approach.

### `consensus_snapshots`
```sql
create table consensus_snapshots (
  id uuid primary key default gen_random_uuid(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  aggregate_confidence numeric(5,4) not null,
  agreement_variance numeric(5,4),           -- feeds the Elite-tier reconciliation threshold, Volume 2 §7
  model_routing_used jsonb,                  -- which models handled which agents this run
  second_pass_triggered boolean default false,
  created_at timestamptz default now()
);
```

### `explainability_payloads`
```sql
create table explainability_payloads (
  id uuid primary key default gen_random_uuid(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  why_this_recommendation text,
  why_this_bet_type text,
  why_now text,
  why_not_alternatives text,
  strongest_evidence text,
  biggest_risks text,
  invalidating_conditions text,
  contributing_agents uuid[],
  persona_fit_explanation text,
  created_at timestamptz default now()
);
```
Field names mirror the master spec's explainability question list directly — this is intentional, so there's a 1:1 traceability between the product requirement and the schema, useful when Volume 4 or Volume 5 need to confirm nothing on that list got dropped.

### `recommendation_snapshots` (Time Machine)
```sql
create table recommendation_snapshots (
  recommendation_id uuid primary key references recommendations(id) on delete cascade,
  full_environment_snapshot jsonb not null,  -- odds, weather, injuries, market state, all frozen
  agent_outputs_snapshot jsonb not null,     -- redundant with recommendation_agent_outputs, stored flat for fast reconstruction
  consensus_snapshot jsonb not null,
  created_at timestamptz default now()
);
```
**Why this table duplicates data that already exists in normalized form elsewhere:** reconstructing a recommendation by joining across `odds_snapshots`, `recommendation_agent_outputs`, `consensus_snapshots`, and `explainability_payloads` works, but it's slow and fragile — a future schema change to any of those tables risks silently breaking historical reconstruction. This table is a deliberate denormalization: one flat JSON blob captured at creation time, guaranteed never to change, that the `/v1/recommendations/{id}/snapshot` endpoint (Volume 2, Section 6) can read directly without joins. Storage cost is cheap; reproducibility risk is not.

---

## 6. Bet Verification & Performance Attribution

### `bet_slips`
```sql
create table bet_slips (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  image_storage_path text,                   -- Supabase Storage reference
  ocr_extracted_data jsonb,
  linked_recommendation_id uuid references recommendations(id),
  created_at timestamptz default now()
);
```

### `verified_bets`
```sql
create table verified_bets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  bet_slip_id uuid references bet_slips(id),
  recommendation_id uuid references recommendations(id),  -- nullable: user may bet outside recommendations
  stake numeric(10,2),
  odds numeric(8,2),
  outcome text check (outcome in ('win','loss','push','pending')),
  payout numeric(10,2),
  created_at timestamptz default now()
);
```

### Performance attribution — three tables, deliberately never merged

```sql
create table ai_performance (
  id uuid primary key default gen_random_uuid(),
  evaluation_window_start date,
  evaluation_window_end date,
  roi numeric(8,4), ev numeric(8,4), clv numeric(8,4), units numeric(10,2),
  sport text, bet_type text,
  created_at timestamptz default now()
);

create table projected_user_performance (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  recommendation_id uuid not null references recommendations(id),
  projected_units numeric(10,4) not null,   -- (recommendation outcome × user's preferred_unit_size)
  created_at timestamptz default now()
);

create table verified_user_performance (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  verified_bet_id uuid not null references verified_bets(id),
  actual_units numeric(10,4) not null,
  created_at timestamptz default now()
);
```
**Why three tables instead of one `performance` table with a `type` enum column:** the master spec is explicit — "Never mix these." A single table with a type column makes it trivially easy to write a query (deliberately or by accident) that averages projected and verified performance together, which would misrepresent real user results as AI-validated fact. Separate tables make that mistake require deliberately joining three tables — a much higher bar than forgetting a `WHERE type = 'verified'` clause.

### Stat Correction ↔ Bet Settlement Policy (v4.3)

**This is policy for Phase 5's grading/outcome implementation, not a Phase 3 build item.** Phase 3 does not implement bet-grading logic. It is documented here, now, because Phase 3's ingestion/provenance/postgame-reconciliation architecture (Volume 2 §8's Postgame Ingestion Worker, and the Milestone F provenance work referenced below) has to be built in a way that doesn't foreclose this policy later — history preserved, nothing destructively overwritten — even though nothing here gets implemented until Phase 5.

**1. Sportsbook settlement and sports-stat truth are separate, related records.** A wager's graded outcome (`verified_bets.outcome`) and the underlying sports statistics (`player_stats`, `team_stats`, `games.final_score`) are not the same thing and must never be treated as automatically equivalent. A later correction to sports statistics is never, by itself, a change to a wager's official settlement.

**2. A wager's graded outcome comes from the official settlement/result source used for grading — never inferred solely from corrected statistics.** `verified_user_performance` and `ai_performance` must read the *effective sportsbook-settled outcome*, not independently recalculate win/loss/push from the latest `player_stats`/`team_stats`/`final_score` row. (This is already the schema's structural default — `verified_user_performance` references `verified_bets`, not the stats tables, directly — Phase 5 must not add a path that bypasses this.)

**3. When a provider issues a postgame statistical correction:** update or supersede the underlying stat record, but preserve the previous version; record explicitly that a correction occurred (not just infer it from row order); preserve when The Playbook learned of the correction; and never let a stat correction silently overwrite an already-settled wager outcome. Historical evidence stays reconstructable, never destructively replaced — the same append-only philosophy `odds_snapshots` already uses.

**4. If the official sportsbook/result source itself later regrades a wager:** preserve the original settlement, record the regrade as a new historical event/version (not an in-place update), update the wager's current effective outcome, preserve when The Playbook learned of the regrade, and retain enough history to reconstruct both the original and the revised settlement.

**5. Performance analytics use the effective sportsbook-settled outcome, never `player_stats`/`team_stats`/`final_score` directly**, when an authoritative settlement record exists — keeping recommendation performance aligned with what the bettor actually experienced, not a recalculation from raw stats.

**6. Time Machine reconstruction must be able to distinguish, for any historical recommendation:** what was known at recommendation time (`recommendation_snapshots`, already satisfies this); the initial postgame stats/results (Postgame Ingestion Worker's first fetch, Volume 2 §8); any later provider stat corrections and when they became known (Milestone F provenance work, below); the original sportsbook settlement; any subsequent regrade; and the current effective settlement outcome. "What did The Playbook know at that time" must never be rewritten by a later correction or regrade.

**Schema gap check against the six requirements above (per Mac's explicit instruction to verify before changing anything):**
- Rules 1, 2, 5 are already structurally satisfied — `verified_bets`/`verified_user_performance`/`ai_performance` have never been coupled to the stats tables; nothing today would need to change for Phase 5 to honor them.
- Rule 3's version-preservation half is already structurally possible without a migration: `team_stats`/`player_stats` carry no uniqueness constraint on `(team_id/player_id, game_id)`, so a correction can already be inserted as a new row rather than an overwrite. What's *not* yet present is an explicit "this row is a correction" marker (today it would only be inferable from row order) — a refinement to fold into the Milestone F provenance migration already proposed in `PROGRESS.md` (2026-08-10), not a new table.
- **Rule 4 is a real, unclosed gap.** `verified_bets` is a single mutable row per wager with no history/versioning pattern — unlike `odds_snapshots`, it has no append-only structure today. An in-place `update ... set outcome = ...` on a regrade would destructively overwrite the original settlement with no record it ever changed. Closing this requires a genuine schema addition (most likely an append-only `verified_bet_settlements`-style history table, mirroring the `odds_snapshots` pattern, plus a way to mark which row is currently effective) — **explicitly not built now.** This is Phase 5's schema work, flagged here so it isn't rediscovered as a surprise when Phase 5 begins.
- Rule 6 depends on rules 3 and 4 above: satisfied for the recommendation-time and initial-postgame-stat legs today; the correction-marker refinement (rule 3) and the settlement-history gap (rule 4) are exactly what's still missing, and are the same two items already named above — nothing additional.

**Phase 3's actual obligation:** don't destructively overwrite provider data or correction evidence, and don't build anything that assumes a stat correction updates a wager's settlement. Both are already true of the current Phase 3 design (Volume 2 §8's Postgame Ingestion Worker inserts new rows rather than overwriting, and nothing in Phase 3 touches `verified_bets` at all) — no Phase 3 architecture change is required by this policy.

---

## 7. Postgame Review & Market Monitoring

### `postgame_reviews`
```sql
create table postgame_reviews (
  id uuid primary key default gen_random_uuid(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  outcome_summary text,
  why_it_won_or_lost text,
  weather_impact_assessment text,
  injury_impact_assessment text,
  line_movement_impact_assessment text,
  correct_agents uuid[],
  underperforming_agents uuid[],
  learning_notes text,
  created_at timestamptz default now()
);
```
Generated automatically by the scheduled worker (Volume 2, Section 4.4) once `games.status = 'final'`. This table is what feeds the "correct_agents / underperforming_agents" data back into `agent_performance_scores` — the Continuous Learning Engine loop, fully specified in Volume 4, closes here at the schema level. **`outcome_summary` narrates recommendation performance, not wager settlement** — it must not be treated as, or conflated with, a graded bet outcome. See §6's Stat Correction ↔ Bet Settlement Policy (v4.3) for the full separation requirement; that policy is Phase 5 scope, not built here.

### `market_monitoring_events`
```sql
create table market_monitoring_events (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id),
  event_type text check (event_type in
    ('line_movement','injury_update','weather_change','lineup_change','breaking_news')),
  event_data jsonb,
  affected_recommendation_ids uuid[],
  action_taken text check (action_taken in ('none','updated','withdrawn')),
  created_at timestamptz default now()
);
create index idx_mme_game on market_monitoring_events(game_id);
```

---

## 8. AI Orchestration Config Table

### `model_routing_rules`
```sql
create table model_routing_rules (
  id uuid primary key default gen_random_uuid(),
  task_type text not null,                   -- e.g. 'injury_analysis','consensus_reconciliation'
  primary_model text not null,               -- e.g. 'claude-sonnet-4-6'
  fallback_model text,
  min_tier_for_second_pass text default 'elite',
  active boolean default true,
  updated_at timestamptz default now()
);
```
This directly resolves the open item flagged at the end of Volume 2: model routing is data, read by the Orchestrator at request time, not hardcoded logic — updating this table changes behavior without a deploy, satisfying the master spec's "swap models without redesign" requirement at the schema level.

### `prompt_registry` (v2.0)
```sql
create table prompt_registry (
  id uuid primary key default gen_random_uuid(),
  prompt_name text not null,
  version integer not null,
  prompt_text text not null,
  status text check (status in ('draft','active','deprecated')),
  owner text,
  updated_at timestamptz default now(),
  unique(prompt_name, version)
);
```
Every agent (Volume 4 §2) loads its prompt from this table by `(prompt_name, status='active')` rather than embedding prompt text in code. This is the mechanism that makes `prompt_version` on `recommendations` (§5 above) meaningful — without a registry, "prompt version" would have nothing to point to.

### `model_registry` (v2.0)
```sql
create table model_registry (
  id uuid primary key default gen_random_uuid(),
  model_name text not null unique,
  strengths text,
  weaknesses text,
  cost_per_1k_tokens numeric(10,6),
  avg_latency_ms integer,
  preferred_tasks text[],
  capabilities text[],
  status text check (status in ('active','retired')),
  updated_at timestamptz default now()
);
```
`model_routing_rules.primary_model` / `fallback_model` above now conceptually reference `model_registry.model_name` — not a hard foreign key (routing rules should still function if a model is mid-migration), but the Orchestrator's routing decision (Volume 4 §3.2) should factor in this table's `cost_per_1k_tokens` and `avg_latency_ms`, not just task-type mapping alone.

### `feature_flags` (v2.0)
```sql
create table feature_flags (
  id uuid primary key default gen_random_uuid(),
  flag_key text not null unique,
  description text,
  enabled boolean default false,
  audience_tier text[],                    -- e.g. ARRAY['elite']
  rollout_percentage integer default 0 check (rollout_percentage between 0 and 100),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
```
Consumed by the Orchestrator (new consensus algorithms, experimental agents) and the frontend (beta dashboard features) alike, read at request time — same "data not code" principle as `model_routing_rules`.

### `recommendation_costs` (v2.0)
```sql
create table recommendation_costs (
  id uuid primary key default gen_random_uuid(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  provider text check (provider in ('openai','anthropic','ocr','sports_api')),
  cost_usd numeric(10,6),
  created_at timestamptz default now()
);
create index idx_reccosts_recommendation on recommendation_costs(recommendation_id);
```
Feeds directly into Volume 1 §8's business metrics — "average cost per recommendation," "average cost by tier" become real queries against this table joined with `subscriptions`, closing a gap where Volume 1 committed to data-driven pricing decisions without a table to make that possible.

### `audit_log` (v2.0, expanded scope)
```sql
create table audit_log (
  id uuid primary key default gen_random_uuid(),
  actor text,                               -- 'system', a user_id, or an admin identifier
  action_type text check (action_type in
    ('prompt_change','weight_change','routing_change','model_swap',
     'consensus_change','admin_action','feature_flag_change')),
  target_id uuid,
  before_state jsonb,
  after_state jsonb,
  created_at timestamptz default now()
);
```
This is the audit trail for changes *to the system itself* — distinct from `recommendation_agent_outputs` and other tables that audit what the system *produced*. Every write to `prompt_registry`, `agents.current_weight`, `model_routing_rules`, or `feature_flags` should insert a corresponding `audit_log` row via database trigger (§11), not application-layer discipline, for the same reason the append-only trigger on `recommendation_agent_outputs` is enforced at the database level rather than trusted to every future code path.

### UUIDv7 for high-insert append-only tables (v2.0)
`odds_snapshots`, `recommendation_agent_outputs`, and `market_monitoring_events` (all defined above) should generate primary keys via UUIDv7 rather than `gen_random_uuid()`'s UUIDv4 default. UUIDv7's time-ordered structure improves index locality specifically on the tables that accumulate fastest — these three are the highest-insert-volume tables in the schema. Lower-volume tables (`subscriptions`, `user_profiles`) stay on standard `gen_random_uuid()`; the benefit doesn't justify a migration there.

---

## 9. Indexing Strategy Summary

General rule applied throughout: index every foreign key used in a hot-path query, and index every `status`/`active` boolean-like column with a **partial index** (`where status = 'active'`) rather than a full index, since most queries only care about the active subset and a partial index keeps it small and fast as historical data accumulates. `odds_snapshots` and other append-only tables are indexed on `(foreign_key, captured_at desc)` composite indexes specifically to make "give me the latest snapshot" and "give me everything since X" both fast, since both query patterns are common (live dashboard vs. Time Machine reconstruction).

---

## 10. Row Level Security (RLS) Policies

RLS is enabled on every table containing user data. Two representative examples — the pattern repeats across the schema:

**Clarification (added 2026-08-07, Phase 1 Milestone 2):** this section's opening line should be read as "every table requiring access control," not narrowly as "every table containing per-user rows." Some tables outside this section's scope — the normalized multi-sport core and derived intelligence tables in §4 — hold no user-specific data but are read directly by the frontend via Supabase Realtime (Volume 2) rather than exclusively through the API Gateway, so RLS is the only enforcement layer standing in front of those reads. RLS applies to them too, via permissive public-read policies rather than the `auth.uid() = user_id` pattern used elsewhere in this section — this data was always meant to be public-facing (Volume 1/5: no subscription tier gates raw sports data, only recommendations).

```sql
-- Users can only read their own profile
alter table user_profiles enable row level security;
create policy "own_profile_select" on user_profiles
  for select using (auth.uid() = id);
create policy "own_profile_update" on user_profiles
  for update using (auth.uid() = id);

-- Recommendations: tier-gated read access
alter table recommendations enable row level security;
create policy "recommendations_tier_gated_select" on recommendations
  for select using (
    min_required_tier = 'free'
    or exists (
      select 1 from subscriptions s
      where s.user_id = auth.uid()
        and s.status = 'active'
        and (
          (min_required_tier = 'pro' and s.tier in ('pro','elite','syndicate'))
          or (min_required_tier = 'elite' and s.tier in ('elite','syndicate'))
        )
    )
  );
```
**This is the schema-level enforcement Volume 2 flagged as needed:** tier gating now can't be bypassed by hitting the API directly, because Postgres itself won't return rows a user's subscription doesn't entitle them to, independent of any application-layer check.

`verified_bets`, `bet_slips`, `projected_user_performance`, `verified_user_performance`, `betting_dna`, and `conversations`/`conversation_messages` (Volume 4/5 own the NL Engine's message schema) all follow the same `auth.uid() = user_id` pattern as the baseline policy, with service-role bypass reserved for the background workers described in Volume 2.

**Admin/service role:** background workers and the Orchestrator connect via Supabase's service role key, which bypasses RLS by design — this is safe specifically because Volume 2, Section 10 keeps that credential internal-only, never exposed to the frontend or reachable via a user-facing endpoint.

**Soft-delete filtering (v2.0):** every standard `select` policy on a table with a `deleted_at` column (`user_profiles`, `recommendations`, `bet_slips` per §3, §5, §6) adds `and deleted_at is null` to the `using` clause, so soft-deleted rows disappear from normal application queries without being physically destroyed — preserving the history the Time Machine principle depends on. A separate admin-only policy, gated on a service role or admin claim, allows querying including soft-deleted rows for audit purposes:
```sql
create policy "own_profile_select" on user_profiles
  for select using (auth.uid() = id and deleted_at is null);
```

---

## 11. Triggers

Three triggers are worth specifying explicitly because they enforce invariants that would otherwise depend on application code remembering to do the right thing:

```sql
-- Auto-update updated_at on every table that has one
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trg_user_profiles_updated
  before update on user_profiles
  for each row execute function set_updated_at();
-- (repeated per table with an updated_at column)

-- Prevent recommendation_agent_outputs from ever being updated after insert
-- (append-only enforcement at the database level, not just convention)
create or replace function block_agent_output_updates()
returns trigger as $$
begin
  raise exception 'recommendation_agent_outputs is append-only and cannot be modified';
end;
$$ language plpgsql;

create trigger trg_block_rao_update
  before update on recommendation_agent_outputs
  for each row execute function block_agent_output_updates();

-- v2.0: auto-populate audit_log on writes to system-config tables
create or replace function log_config_change()
returns trigger as $$
begin
  insert into audit_log (actor, action_type, target_id, before_state, after_state)
  values (
    coalesce(current_setting('request.jwt.claim.sub', true), 'system'),
    case TG_TABLE_NAME
      when 'prompt_registry' then 'prompt_change'
      when 'agents' then 'weight_change'
      when 'model_routing_rules' then 'routing_change'
      when 'feature_flags' then 'feature_flag_change'
    end,
    coalesce(new.id, old.id),
    to_jsonb(old),
    to_jsonb(new)
  );
  return new;
end;
$$ language plpgsql;

create trigger trg_prompt_registry_audit
  after insert or update on prompt_registry
  for each row execute function log_config_change();
-- (repeated for agents.current_weight changes, model_routing_rules, feature_flags)
```
The second trigger is the important one: it turns "this table should be append-only" from a convention every future developer needs to remember into something the database physically refuses to violate — directly protecting the Time Machine guarantee at the lowest possible level. The third (v2.0) does the same job for system-configuration changes that the review's expanded audit logging asked for: writing to `audit_log` happens automatically on the write itself, not as a step a future migration or admin panel has to remember to also do.

---

## 12. Migration Strategy

Supabase CLI-managed migrations, one SQL file per change, sequentially numbered, committed to the same repo as the application code (not managed by hand in the Supabase dashboard, which leaves no history). Migration flow follows Volume 2's environment structure directly: a migration is written and applied to `dev` first, promoted to `staging` for integration testing against real (non-production) provider data, then promoted to `production` only after both pass — never applied directly to production first, for the same reproducibility-protection reason `dev`/`staging`/`production` are fully separate Supabase projects, not just schemas within one.

**Backward-compatible migrations preferred.** Additive changes (new nullable column, new table) ship independently of application code deploys. Breaking changes (column removal, type changes, `not null` additions to existing tables) require a two-step migration: add new alongside old, migrate application code to the new field, then remove old in a follow-up migration — this avoids any window where a mid-deploy mismatch between API code and schema causes write failures during a live game window, which is the single worst time for a database error on this product.

---

## 13. Open Decisions Carried to Later Volumes

- **Conversation/chat message schema** for the Natural Language Engine is referenced (Section 10's RLS pattern) but not fully specified — Volume 4/5 should finalize `conversations` and `conversation_messages` table shapes jointly, since both the NL Engine (Volume 4) and the chat UI (Volume 5) depend on the exact shape.
- **Agent weighting algorithm** that writes to `agents.current_weight` and reads `agent_performance_scores` is fully owned by Volume 4 — this volume only guarantees the storage shape and the minimum-sample-size guardrail exists.
- **Notification table schema** (referenced in Volume 2's worker list) needs a dedicated pass, likely small enough to fold into Volume 5 alongside the Notification dashboard component.
- **Deferred schema (v3.0):** a supplementary ~150-table proposal was reviewed alongside this version's additions. Most was declined as either duplicative of existing tables under different names or premature for MLP scope (ML training tables, sentiment tables, extensive historical-data duplication beyond what the existing append-only snapshot tables already provide). Full reasoning in `v3.0-amendments-conversational-intelligence.md` §11 — worth a fresh look post-MLP once there's real usage data to justify the additional surface area.

---

## Changelog Entry for This Version

See `CHANGELOG.md` — v1.0, 2026-08-05, Volume 3 added. Updated to v2.0, 2026-08-05, per external architecture review — `feature_flags`, `prompt_registry`, `model_registry`, `recommendation_costs`, expanded `audit_log`, AI versioning columns, soft-delete columns, UUIDv7 guidance, and the `referral_code` field integrated into §3, §5, §8, §10, and §11 above, not just noted in the version header. Updated to v3.0, 2026-08-05 — `daily_game_intelligence`, derived score tables (§4.1–§4.2), and `display_id` (§5) integrated directly. Updated to v4.0, 2026-08-06 — normalized multi-sport core (§4.0) and data quality metadata convention (§4.1) integrated directly, per the internal markdown-consistency review.
