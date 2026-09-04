# The Playbook — Volume 3
## Database Architecture: Tables, Relationships, Indexes, Triggers, Migrations, RLS

**Version:** v4.27
**Last updated:** 2026-09-04

**v4.27 note (MINOR, HQ directive, planning only):** New §5G, Recommendation Lifecycle & Change Events — architecture reservation only, nothing built. HQ directed formally defining what happens when MANSA changes its view after a recommendation has already been activated (`docs/ops/recommendation-lifecycle-spec-2026-09-04.md`). Proposes a four-value extension to `recommendation_product_lifecycle_events.event_type` (`STRENGTHENED`/`WEAKENED`/`NO_LONGER_QUALIFIES`/`REPLACED`), reusing `market_monitoring_events.event_type` almost verbatim for a new `trigger_type` column plus two genuinely new trigger categories (`contextual_intelligence_change`/`model_refresh`), a `related_recommendation_product_id` linkage for reversals, and a new standalone `user_recommendation_placements` table for user-asserted "I placed this" tracking (deliberately not an extension of `user_recommendation_selections`, whose materiality-suppression trigger has different semantics). Also makes explicit, as a proposed ratified policy rather than a code change, a real finding from direct code inspection this pass: no query in the grading pipeline (`apps/ai-orchestrator/app/{persistence,orchestration}/postgame_grading.py`) filters by `recommendation_products.status` today — a withdrawn product's legs are already graded on their frozen activation-time terms, by omission rather than documented policy. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v4.26 note (MINOR, HQ decision):** §4.3 (`game_events`) and §4.4 (`news_article_history`) — proposed in v4.25 the same day — are now IMPLEMENTED IN DEV: both migrations applied and live-verified (append-only triggers proven by real rejected `UPDATE`s; `news_article_history`'s insert-once dedup proven by a real rollback-wrapped insert-twice test). `app.workers.news_worker` now writes to `news_article_history` alongside its existing `daily_game_intelligence.news` upsert. `game_events` normalization, real provider wiring, and any live invocation remain explicitly deferred to after the 2026-09-09/10 MySportsFeeds live-game validation — this entry adds the raw-capture persistence path only, per `docs/ops/2026-data-preservation-readiness-plan-2026-09-04.md`'s own pre-9/9 minimum scope. Staging and production untouched. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v4.25 note (MINOR, HQ decision):** New §4.3 (Game Events / Play-by-Play) and §4.4 (News History) — both architecture reservations only, mirroring Volume 4 §8.5/§8.6's identical "nothing described exists yet" treatment, prepared ahead of the 2026-09-09 NFL regular-season opener per the 2026 Data Preservation Readiness Plan (`docs/ops/2026-data-preservation-readiness-plan-2026-09-04.md`). §4.3 proposes a provider-neutral `game_events` table (raw provider payload as the load-bearing column, typed fields as best-effort normalization only) deliberately without locking any MySportsFeeds-specific field names ahead of that provider's still-pending live-game validation. §4.4 proposes an append-only `news_article_history` table (insert-once-per-article, not per-poll) closing the News-has-no-history gap both the Phase 7 and Phase 8 audits already found. Neither table is created by this entry — no migration applied. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v4.24 note (PATCH):** §10's named list of tables following the `auth.uid() = user_id` RLS pattern extended to explicitly include `subscriptions` and `user_recommendation_selections` — both already carry that exact live policy, but the list omitted them (a self-acknowledged gap flagged in the `20260825120000_recommendation_products_schema.sql` migration's own comment for `subscriptions` at the time it was written, never corrected here until now). Found during Phase 6 Product/UX planning (Pass 3 §14 backend research). No schema or policy change. See `CHANGELOG.md` v4.24 entry for full reasoning.
**v4.21 note (MINOR):** §5B gains a new §5C — `recommendation_activation_snapshots`/`_legs`/`_source_products` + `recommendation_product_lifecycle_events` (Phase 5 Milestone 5.3, Time Machine) — an additive activation manifest that composes already-frozen Milestone 5.1/5.2 rows by FK, never duplicating odds/EV/confidence/explanation content a second time. The legacy `recommendation_snapshots` (§5, Phase 1) is confirmed unfit for the Phase 5 product/leg layer and is left completely untouched. Two real, live-verified provenance gaps found during the Milestone 5.3 inspection are also closed: `consensus_snapshots` gains the append-only `BEFORE UPDATE` trigger every sibling table already had; `recommendation_agent_outputs` gains nullable `model_name`/`provider`/`used_fallback` columns recording the ACTUAL model/provider that produced each output (never the requested routing rule). `recommendation_product_explanations`/`recommendation_leg_explanations` gain `explainability_version`. See `CHANGELOG.md` v4.21 entry for full reasoning.
**v4.20 note (MINOR):** §5A gains a new §5B — `recommendation_product_explanations`/`recommendation_leg_explanations` (Phase 5 Milestone 5.2, Deterministic V1) — two new additive tables giving every `recommendation_products`/`recommendation_legs` row exactly one, ever, append-only explanation. `explainability_payloads` (§5, Phase 1) is left completely untouched: not repointed, not retrofitted, not deleted, its existing row not migrated — its sole FK target (`recommendations.id`) has no path to the Phase 5 product layer, and it carries no append-only protection at all. See `CHANGELOG.md` v4.20 entry for full reasoning.
**v4.17 note (MINOR):** New table `master_refresh_runs` (Milestone 4.9, 2026-08-25) — the durable bridge between "Master Refresh completed" and "the Recommendation Worker may safely process this slate," created before work begins and finalized once with the actual outcome (`running`/`success`/`partial`/`failed`, mirroring `MasterRefreshResult.status` exactly). `recommendations` gains `correlation_id text unique`, nullable and backward-compatible — the crash-safe idempotency identity flagged as an open gap since Milestone 4.5, now resolved: a retried Recommendation Worker call against the same `(master_refresh_run_id, game_id)` pair recovers the same row via upsert rather than creating a duplicate. See `CHANGELOG.md` v4.17 entry for full reasoning.
**v4.16 note (MINOR):** `recommendation_agent_outputs` gains two nullable columns, `prompt_name`/`prompt_version` (Milestone 4.8, Phase 4 Closeout Remediation, 2026-08-24), plus a composite FK to `prompt_registry(prompt_name, version)` — the canonical per-agent-output prompt provenance, since `recommendations.prompt_version` (§5) cannot truthfully represent independently-versioned per-agent prompts once `prompt_registry` became the production source of agent system prompts. `recommendations.prompt_version` itself is unchanged in shape but is now documented as legacy/non-authoritative for per-agent reconstruction — see both sections below. `prompt_registry` also gains a partial unique index enforcing at most one active version per `prompt_name`. See `CHANGELOG.md` v4.16 entry for full reasoning.
**v4.15 note (MINOR):** `consensus_snapshots` gains four nullable columns (Milestone 4.7, 2026-08-22): `candidate_key` (mirrors `recommendation_agent_outputs.candidate_key`, v4.14, exactly), `final_aggregate_confidence` (distinct from the existing `aggregate_confidence`), `below_confidence_floor` (the internal 0.55-threshold result, never a Phase-5 recommendation decision), and `participation_metadata` (the only durable record of what was attempted/failed/deferred for a historical run, since a failed/deferred agent leaves no row elsewhere). See `CHANGELOG.md` v4.15 entry for full reasoning.
**v4.14 note (MINOR):** `recommendation_agent_outputs` gains a nullable `candidate_key text` column + partial index (Milestone 4.6, Decision G, 2026-08-22) — makes the identity of a specific evaluated wager (e.g. "KC moneyline -125") a first-class, queryable part of a row, instead of existing only inside `raw_output` JSON. `NULL` for every existing game-level fan-out output; populated only for the new sequential Decision & Advisory chain's candidate-level outputs. Deliberately no uniqueness constraint. See `CHANGELOG.md` v4.14 entry for full reasoning.
**v4.13 note (MINOR):** §8's `model_registry` gains a `provider text not null` column (Milestone 4.4 pre-check, 2026-08-21) — closes a real gap Milestone 4.3 found: neither `model_registry` nor `model_routing_rules` stored explicit vendor identity, forcing `ModelRouter` to infer provider from model-name string prefixes. Deliberately not a `check (provider in ('openai','anthropic'))` constraint, unlike `game_provider_ids`/`team_provider_ids`/`player_provider_ids.provider_name`'s existing rigid-CHECK convention — adding a future model provider is a plain data insert, never a schema migration. Validated at the application layer instead (`app.models.router`'s adapter registry). Dev's 2 existing rows backfilled `'anthropic'` (both Anthropic-family models, confirmed before migrating). See `CHANGELOG.md` v4.13 (Volume 3) entry for full reasoning.
**Depends on:** Volume 1 (v3.0 — tiers, personas, principles) and Volume 2 (v4.2 — service shape, routing table reference, RLS placeholder, scoped event system, Redis cache layer, Postgame Ingestion Worker)
**v4.0 note:** Normalized multi-sport core added (§4.0) — `sports`/`leagues`/`seasons`/`teams`/`players`/`player_stats`/`team_stats` plus the `player_stats_nfl` extension pattern. `games` gains `sport_id`/`league_id`/`season_id` while the legacy `sport` text field is kept, deprecated, for Phase 0/1 backward compatibility. Data quality metadata convention added to `daily_game_intelligence` (§4.1). See `CHANGELOG.md` v4.0 entry for full reasoning.
**v4.1.1 note (PATCH):** §10 gained a clarification that its RLS scope covers "every table requiring access control," not only tables containing per-user data (Phase 1 Milestone 2). The three tables named in the v2.0 UUIDv7 amendment (`odds_snapshots`, `recommendation_agent_outputs`, `market_monitoring_events`) use a custom `uuid_generate_v7()` function, since the deployed Postgres version predates native `uuidv7()` support. See `CHANGELOG.md` v4.1.1 entry for full reasoning.
**v4.2 note (MINOR):** §3's `user_profiles.jurisdiction_state` relaxed from `not null` to nullable — Phase 2's signup trigger creates the row before onboarding (where jurisdiction is actually collected) ever runs. The `not null` *intent* is now enforced at the application layer. See `CHANGELOG.md` v4.2 entry for full reasoning.
**v4.3 note (MINOR):** §6 gains the Stat Correction ↔ Bet Settlement Policy — Phase 5 grading/outcome policy, documented now so Phase 3's postgame architecture doesn't foreclose it later. No schema changed; one real gap (`verified_bets` has no settlement-history/versioning pattern) identified and explicitly deferred to Phase 5. See `CHANGELOG.md` v4.3 entry for full reasoning.
**v4.4 note (MINOR):** §4.0 gains `game_provider_ids` — the authoritative multi-provider game identity mechanism (Phase 3E-1, Decision 2), replacing `games.external_provider_id`'s hidden single-vendor assumption. `games` gains nullable `season_type`/`week` (Decision 1) and `external_provider_id` becomes nullable/deprecated rather than dropped. See `CHANGELOG.md` v4.4 entry for full reasoning.
**v4.5 note (MINOR):** §4.1 gains documented semantics for `daily_game_intelligence.rest`/`.travel` (Phase 3E-2, Decisions 2/3) — `rest` is buildable and implemented now; `travel` is defined but deliberately left null/unavailable pending a venue-coordinate schema decision, tracked as a follow-up rather than solved by fabricating data. No schema changed. See `CHANGELOG.md` v4.5 entry for full reasoning.
**v4.6 note (MINOR):** §4.0 gains `team_provider_ids` — the authoritative multi-provider team identity mechanism (Phase 3E-3), mirroring `game_provider_ids`. Backfilled for the six seeded dev teams via an explicit, documented mapping table; `teams.external_provider_id` deprecated (no NOT NULL relaxation needed, unlike `games`, since nothing read it and it was already nullable). See `CHANGELOG.md` v4.6 entry for full reasoning.
**v4.7 note (MINOR):** §4.0's `teams` expanded from the original 6 seed teams to all 32 current NFL teams (Phase 3E-4A); `team_provider_ids` sportsdataio coverage expanded from 4 to 13 of 32, each new mapping confirmed against this repository's own fixtures. A retroactive provenance correction is disclosed: two of 3E-3's original six `team_provider_ids` entries (Dallas Cowboys/Philadelphia Eagles, `sportsdataio`) were not actually fixture-confirmed at the time, only caught under 3E-4A's stricter audit — see `CHANGELOG.md` v4.7 entry for the full finding and why those two rows were left in place rather than unilaterally dropped. No schema change.
**v4.8 note (MINOR):** §4.0's `team_provider_ids` `sportsdataio` coverage taken to 32/32 (from 13/32) via a single-purpose live capture of `/v3/nfl/scores/json/Teams` (11th of 12 Free Trial calls; the 12th/final call intentionally not spent) — deterministically reconciled against `teams.name` (exact match, zero fuzzy matching, zero conflicts). This also resolves v4.7's disclosed provenance gap: Dallas Cowboys/Philadelphia Eagles' `sportsdataio` rows (`DAL`/`PHI`) are now CONFIRMED CORRECT, not merely left in place. `the_odds_api` coverage is unchanged at 6/32. No schema change. See `CHANGELOG.md` v4.8 entry for full reasoning.
**v4.9 note (MINOR):** §4.0's `games` gains three nullable columns — `venue_lat`, `venue_long`, `venue_type` (Phase 3E-6, Option A) — preserving SportsDataIO Schedule's `StadiumDetails.GeoLat`/`.GeoLong`/`.Type` instead of discarding them during normalization, closing the exact gap v4.5's travel-semantics note flagged and deferred. Built for Weather Worker's location resolution and dome/indoor optimization (Volume 2 §8); also the durable coordinate storage that note's deferred travel-distance computation can build on later, still not built here. See `CHANGELOG.md` v4.9 entry for full reasoning, including the alternative (a dedicated `stadiums` reference table) considered and why the smaller additive columns were chosen instead.
**v4.10 note (MINOR):** §4.0 gains `player_provider_ids` — the authoritative multi-provider player identity mechanism (Phase 3E-8, Decision 1, Option B), mirroring `game_provider_ids`/`team_provider_ids` exactly. `players.external_provider_id` deprecated, same convention as the other two tables. `games` gains one nullable column, `finalized_at` — the stable anchor Postgame Worker's bounded reconciliation schedule (Volume 2 §8) measures elapsed time against. `players` itself is populated via a small, fixture-backed backfill (`app.persistence.player_backfill`, exactly four real captured players) rather than a live provider call — coverage gaps are real and reported, not hidden. See `CHANGELOG.md` v4.10 entry for full reasoning.
**v4.11 note (MINOR):** §4.0 gains `roster_memberships` — the historical record of player-team membership over time (Phase 3F-1, Decision 1, Option B), separate from `players.team_id`'s fast current-team lookup. `depth_chart_snapshots` is corrected from its original `game_id`-keyed shape (never exercised by any code) to `team_id`-keyed (Decision 2), matching SportsDataIO's confirmed team-scoped DepthCharts payload. Both tables live-proven against real dev Supabase (append-only trigger rejection, full first-observation/team-change lifecycle) via controlled insert/verify/delete. See `CHANGELOG.md` v4.11 entry for full reasoning.
**v4.12 note (MINOR):** §4.0's `team_stats`/`player_stats` gain the `block_snapshot_updates()` append-only trigger (Phase 3F-3), closing the gap flagged since 3E-8 — application-layer correction-aware logic was already correct, this makes "no UPDATE, only INSERT" authoritative at the database level too, live-proven against real dev Supabase. §4.1's `daily_game_intelligence.stadium` gains a documented shape (`name`/`latitude`/`longitude`/`venue_type`), surfacing `games.venue_lat`/`.venue_long`/`.venue_type` (stored since v4.9) into the working table for the first time. No new tables, no column additions. See `CHANGELOG.md` v4.12 entry for full reasoning.
**v4.12.1 note (PATCH):** §4.0's `player_stats_nfl` gains an explicit "Status" note (below its existing "Why extension tables" paragraph) recording Mac's confirmed decision: the table stays unwired/deferred, `player_stats.stats` jsonb is the source of truth, and the concrete conditions that would justify revisiting it. This was an orphaned gap surfaced by the 2026-08-18 Data Dictionary reconciliation (the table has existed, unwritten, since v4.0) — no schema or code changed, this closes the documentation gap. See `CHANGELOG.md` v4.12.1 entry for full reasoning.
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
   ├── conversations (v5.0, §5A) ──── conversation_messages (Phase 6, not yet built)
   ├── bet_slips
   └── notifications

games ──── odds_snapshots
   │
   └── recommendations ──── recommendation_agent_outputs ──── agents
            │                                                    │
            ├── consensus_snapshots ──── recommendation_legs   agent_performance_scores
            │                                   │
            │                        recommendation_products (v5.0, §5A)
            │                                   │
            │                        user_recommendation_selections
            ├── explainability_payloads
            ├── recommendation_snapshots (Time Machine)
            └── postgame_reviews

display_id_counters (standalone counter, §5A)
master_refresh_runs ──── recommendation_products (v5.0, §5A)

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
  team_id uuid references teams(id),  -- current/latest team only; see roster_memberships for history
  name text not null,
  position text,
  external_provider_id text  -- DEPRECATED, see player_provider_ids
);

-- roster_memberships (Phase 3F-1, v4.11): players.team_id is the fast
-- current-team lookup; this table is the historical record of which team
-- a player belonged to and when. Insert-on-change/latest-row convention
-- (mirroring team_stats/player_stats, Phase 3E-8): a row is inserted only
-- when the observed team differs from the player's latest known team --
-- first observation, a team change, and a rejoin are all the same case at
-- the persistence layer ("observed != latest"). Append-only at the DB
-- level (block_snapshot_updates() trigger) from creation. Release/free-
-- agent state is NOT representable: RosterAdapter.fetch_roster only ever
-- returns players currently on a roster, never an explicit release event,
-- and this schema does not infer one from absence in a later fetch.
create table roster_memberships (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references players(id) on delete cascade,
  team_id uuid not null references teams(id),
  observed_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index idx_roster_memberships_player_time on roster_memberships(player_id, observed_at desc);

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

-- Phase 3F-3, v4.12: DB-level append-only hardening. team_stats/player_stats
-- carry no uniqueness constraint (correction rows are a second, later row for
-- the same (game,team)/(game,player) pair, by design -- a uniqueness
-- constraint would block them) -- only UPDATE is blocked, INSERT is
-- unrestricted. Reuses block_snapshot_updates() verbatim, the same function
-- odds_snapshots/injury_reports/weather_snapshots/depth_chart_snapshots/
-- referee_assignments already use. Live-proven against real dev Supabase:
-- an UPDATE attempt is rejected, a correction INSERT still succeeds, the
-- original row is left untouched.
create trigger trg_block_team_stats_update
  before update on team_stats
  for each row execute function block_snapshot_updates();
create trigger trg_block_player_stats_update
  before update on player_stats
  for each row execute function block_snapshot_updates();

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

**Status (v4.12.1, confirmed by Mac, 2026-08-18): UNWIRED, DEFERRED.** No code anywhere in this codebase writes to `player_stats_nfl` — the 2026-08-18 Data Dictionary reconciliation surfaced this as a real, previously-undocumented Blueprint-vs-reality gap and Mac's explicit decision resolves it, rather than leaving it silently orphaned. **`player_stats.stats` jsonb is the source of truth**, not this table. Rationale: (1) `player_stats.stats` jsonb preserves the complete provider stat payload, while `player_stats_nfl` only ever covered 5 of SportsDataIO's ~100+ real `PlayerGameStatsByWeek` fields (`passing_yards`/`receiving_yards`/`rushing_yards`/`interceptions`/`sacks`) — jsonb remains necessary regardless of whether the typed table is populated; (2) no currently documented downstream consumer (Volume 4 or Volume 5) requires the typed extension table — the Continuous Learning Engine's real consumer is `postgame_reviews`/`agent_performance_scores` (§6's Stat Correction ↔ Bet Settlement Policy), not raw `player_stats` fields; (3) wiring both now would create unnecessary dual-write/duplicate-source-of-truth risk for a currently undemonstrated benefit; jsonb already supports the query patterns (`->>` with casts, GIN indexing) a typed column would offer. **Revisit only when** multi-sport expansion actually begins (the table's own original rationale), a concrete downstream consumer is documented that needs typed/indexed access jsonb can't reasonably provide, or a demonstrated query-performance requirement emerges — not preemptively. The table itself is left in place (schema unchanged, not dropped), since a future NFL-specific typed need remains plausible even though none exists today.

### `games` (updated, v4.4 — Phase 3E-1 additions)
```sql
create table games (
  id uuid primary key default gen_random_uuid(),
  external_provider_id text,                -- DEPRECATED (v4.4): see game_provider_ids below.
                                             -- Nullable since v4.4; retained read-only for
                                             -- pre-3E-1 rows.
  sport_id uuid references sports(id),      -- v4.0: normalized reference
  league_id uuid references leagues(id),    -- v4.0
  season_id uuid references seasons(id),    -- v4.0
  sport text not null default 'nfl',        -- LEGACY — deprecated, kept for Phase 0 backward compatibility
  home_team text not null,
  away_team text not null,
  scheduled_start timestamptz not null,
  stadium text,
  status text check (status in ('scheduled','live','final','postponed','canceled')),
  season_type text check (season_type in ('preseason','regular','postseason')),  -- v4.4, nullable
  week integer,                             -- v4.4, nullable — NFL week number at launch
  venue_lat double precision,               -- v4.9, nullable — see below
  venue_long double precision,              -- v4.9, nullable
  venue_type text check (venue_type in ('outdoor','dome','retractable_dome')),  -- v4.9, nullable
  finalized_at timestamptz,                 -- v4.10, nullable — see below
  final_score jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index idx_games_scheduled on games(scheduled_start);
create index idx_games_status on games(status) where status in ('scheduled','live');
create index idx_games_sport on games(sport_id);
```
**Migration policy (approved with this modification):** the legacy `sport` text field is *not* removed now. Both fields coexist through Phase 0 and Phase 1 — new code paths should populate and read `sport_id`, but nothing currently depending on the `sport` text column breaks. `sport` is formally marked deprecated here, scheduled for removal once the NFL migration to the normalized model is verified complete (a Phase 1 acceptance criterion, not a later cleanup task left to drift). This trades a small amount of temporary duplication for zero Phase-0 disruption — the same reasoning that's governed every other schema decision in this document.

**`venue_lat`/`venue_long`/`venue_type` (v4.9, Phase 3E-6, Option A, 2026-08-18):** preserves SportsDataIO Schedule's `StadiumDetails.GeoLat`/`.GeoLong`/`.Type` (CONFIRMED present in this project's own live-captured fixture) instead of discarding them during normalization — the exact gap v4.5's travel-semantics note flagged. `venue_type` is normalized internal vocabulary (`outdoor`/`dome`/`retractable_dome`), never SportsDataIO's raw wording, same discipline as `season_type`'s own check constraint — an unrecognized raw value raises rather than being silently mapped (`app.adapters.providers.sportsdataio._VENUE_TYPE_MAP`). All three nullable: not every provider response carries venue metadata, and `venue_type` being `null` (or `retractable_dome`) is a real, distinct "unknown" state Weather Worker (Volume 2 §8) must never coerce to either `outdoor` or `dome`. **Option A chosen over a dedicated `stadiums` reference table** (the more normalized alternative, also considered) — smallest additive change, matching the `season_type`/`week` precedent of direct nullable columns rather than a new table, judged sufficient given the league's small (~30) venue count.

**`season_type`/`week` (v4.4, Phase 3E-1, 2026-08-13):** normalized internal vocabulary — `preseason`/`regular`/`postseason` — never a single provider's raw terminology (e.g. SportsDataIO's own numeric `SeasonType` 1/2/3). Checked before adding: no existing internal season-phase vocabulary existed anywhere in this codebase to reuse. Both columns are nullable: `season_type` because not every future sport/provider supplies a season phase, `week` because it's an NFL-specific concept, matching the `player_stats_nfl` extension-table precedent of not forcing one sport's shape onto a shared table. At launch, only `SeasonType == 1` (regular season) has been CONFIRMED FROM LIVE DATA against the SportsDataIO Free Trial and is normalized (`SportsDataIOScheduleAdapter._SEASON_TYPE_MAP`); preseason/postseason mapping is a known gap, not yet wired, pending a live Schedule call against those season types.

### `game_provider_ids` (new, v4.4 — Phase 3E-1, Decision 2, 2026-08-13)

The authoritative multi-provider game identity mechanism, replacing `games.external_provider_id`'s hidden single-vendor assumption. `odds_snapshots.py` used to resolve every game by matching `external_provider_id` directly against The Odds API's own event id — a hidden assumption with no way for a second vendor's id (e.g. SportsDataIO's `GameKey`) to ever coexist on the same game. This table makes that mapping explicit and general: one internal game can carry many `(provider_name, provider_game_id)` pairs.

```sql
create table game_provider_ids (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  provider_name text not null check (provider_name in ('the_odds_api', 'sportsdataio')),
  provider_game_id text not null,
  created_at timestamptz not null default now(),
  unique (provider_name, provider_game_id),  -- a provider's id resolves to exactly one game
  unique (game_id, provider_name)            -- a game has at most one id per provider
);
```

**Constraint design:** the two unique constraints are the actual proof, at the database level and not just in application code, of the two properties Mac's architecture checkpoint required: a SportsDataIO id and a The Odds API id can both resolve to the same `games.id` without creating a duplicate game (they're independent rows sharing one `game_id`), and a provider id cannot silently map to two different games (`unique(provider_name, provider_game_id)` rejects it). `provider_name` is constrained to the providers this codebase actually integrates with today; adding a new vendor is a small follow-up migration, matching the existing convention for `games.status`'s own check-in list. Both unique constraints create their own covering index, which is exactly the pair of lookup paths this table needs — no separate index required. RLS: public-read, service-role-only writes, same as every other sports data table in this section.

**Do not add further provider-specific columns to `games`.** New vendor identity goes into `game_provider_ids`, not a new column.

### `team_provider_ids` (new, v4.6 — Phase 3E-3, 2026-08-13)

The team-identity equivalent of `game_provider_ids`, built for the same reason and mirroring its exact shape deliberately rather than re-deriving one. SportsDataIO identifies teams by abbreviation (`"KC"`, `"SEA"`); The Odds API identifies them by full name (`"Kansas City Chiefs"`, `"Seattle Seahawks"`) — confirmed directly from this project's own already-captured fixtures, surfaced while auditing what the Odds/Player Props Worker (3E-4) will need. `teams.external_provider_id` had the same single-column limitation `games.external_provider_id` had before 3E-1, but with one difference: no code anywhere in this codebase ever read `teams.external_provider_id` (confirmed before writing this migration), and the column was already nullable from its original Phase 1 definition — so unlike `games`, no follow-up NOT NULL relaxation was needed here.

```sql
create table team_provider_ids (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references teams(id) on delete cascade,
  provider_name text not null check (provider_name in ('the_odds_api', 'sportsdataio')),
  provider_team_id text not null,
  created_at timestamptz not null default now(),
  unique (provider_name, provider_team_id),  -- a provider's team id resolves to exactly one team
  unique (team_id, provider_name)            -- a team has at most one id per provider
);
```

**Constraint design and RLS:** identical reasoning to `game_provider_ids` — both unique constraints proven live against dev via `begin`/`rollback` transactions (a SportsDataIO abbreviation and a The Odds API full name both resolve to the same `teams.id`; a provider team id rejected from mapping to a second team; a team rejected from getting a second id from the same provider). Public-read, service-role-only writes.

**Backfill:** the six teams already seeded in dev were backfilled with genuinely correct provider representations (public, standard NFL naming — not fabricated, and not preserved from `teams.external_provider_id`'s synthetic seed values like `"seed-kc"`, which were never real provider ids for any actual vendor). The mapping is the single explicit, documented, tested table `app/persistence/team_backfill.py`'s `TEAM_BACKFILL` — not scattered string normalization across worker code.

**Coverage expanded to the full 32-team league (v4.7 — Phase 3E-4A, 2026-08-14):** `teams` now has all 32 current NFL teams (standard public naming, not provider-specific data). Of those, 13 have a confirmed `sportsdataio` mapping (up from 4) and 6 have a confirmed `the_odds_api` mapping (unchanged) — every new mapping traced to a direct grep of this repository's own fixture files, never filled in from general/public NFL knowledge even where reliable. **19 teams have zero SportsDataIO fixture evidence; 26 teams have zero The Odds API fixture evidence** — a real, standing gap, not silently treated as resolved; `resolve_team_ids` correctly returns "absent" for any of these, and no code may assume every `teams` row has a provider mapping. **Provenance correction, disclosed rather than silently fixed:** auditing against this stricter fixture-only bar found that 2 of the original six `team_provider_ids` rows (Dallas Cowboys/Philadelphia Eagles, `sportsdataio`) were not actually fixture-confirmed when added in 3E-3 — removed from `TEAM_BACKFILL` going forward; the already-applied database rows are deliberately left in place rather than unilaterally dropped (an already-accepted phase's committed data is not silently rewritten), flagged here for Mac's review.

**`sportsdataio` coverage taken to 32/32, provenance gap resolved (v4.8, 2026-08-18):** a single-purpose, single-endpoint live capture of `/v3/nfl/scores/json/Teams` (the 11th of the 12-call Free Trial budget; the 12th/final call intentionally not spent) allowed a deterministic reconciliation of all 32 `teams` rows against the live response — exact `FullName`-to-`teams.name` match, zero fuzzy matching, zero conflicts (`tests/fixtures/sportsdataio/teams_active_normal.json` and `PROVENANCE.md`). All 13 previously-confirmed mappings matched exactly; Dallas Cowboys/Philadelphia Eagles' `DAL`/`PHI` rows are now **CONFIRMED CORRECT** rather than merely left in place; the remaining 17 teams gained a live-confirmed mapping (`20260818040000_team_provider_ids_sportsdataio_full_coverage.sql`). `the_odds_api` coverage is unchanged at 6/32 — this round captured no Odds API evidence, and `resolve_team_ids` still correctly returns "absent" for the 26 teams with no `the_odds_api` mapping.

**Do not add further provider-specific columns to `teams`.** New vendor identity goes into `team_provider_ids`, not a new column.

### `player_provider_ids` (new, v4.10 — Phase 3E-8, Decision 1/Option B, 2026-08-18)

The player-identity equivalent of `game_provider_ids`/`team_provider_ids`, built for the same reason and mirroring their exact shape. Unlike `teams`, `players` had never been populated by any existing code before this phase — Roster data only ever landed in `daily_game_intelligence.players` (a jsonb working field), never as normalized rows — so `player_provider_ids` is the *first* mechanism that gives `players` real, identifiable rows at all, not just a fix to an existing population's identity scheme.

```sql
create table player_provider_ids (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references players(id) on delete cascade,
  provider_name text not null check (provider_name in ('the_odds_api', 'sportsdataio')),
  provider_player_id text not null,
  created_at timestamptz not null default now(),
  unique (provider_name, provider_player_id),  -- a provider's player id resolves to exactly one player
  unique (player_id, provider_name)            -- a player has at most one id per provider
);
```

**Constraint design and RLS:** identical to `game_provider_ids`/`team_provider_ids` — public-read, service-role-only writes.

**Population — fixture-backed, not fabricated, coverage explicitly incomplete.** `app/persistence/player_backfill.py`'s `PLAYER_BACKFILL` contains exactly four real players — the entire universe of player identity evidence (`PlayerID`/`Name`/`Team`/`Position`) this project has ever captured, across two fixtures (`rosters_normal.json`'s 2 rows, `player_stats_week_bulk_normal.json`'s 2 rows). No live provider call was made or authorized to expand this. A `PlayerGameStatsByWeek` row whose player has no `player_provider_ids` mapping is a real, reported gap (`unresolved_players`) — `app/persistence/player_stats.py` never guesses by name-matching and never auto-creates a player opportunistically from live response data (considered and rejected — see `CHANGELOG.md` v4.10 entry).

**Do not add further provider-specific columns to `players`.** New vendor identity goes into `player_provider_ids`, not a new column.

**`games.finalized_at` (new nullable column, v4.10 — Phase 3E-8, Decision 2).** Set once, the first time a game's `status` is observed to transition to `'final'` — the stable anchor Postgame Ingestion Worker's bounded reconciliation schedule (Volume 2 §8, `app.workers.reconciliation`) measures elapsed time against. Deliberately not derived from `games.updated_at`, since a later Schedule re-poll can legitimately re-PATCH an already-final game's other fields, which would silently drift `updated_at` away from the true finalization moment.

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

Additional supporting tables follow the same append-only-snapshot pattern and are listed rather than fully specified here (each mirrors the shape of `odds_snapshots`, keyed to `game_id`, with a `captured_at` timestamp): `injury_reports`, `weather_snapshots`, `referee_assignments`.

`depth_chart_snapshots` is the one exception to the `game_id`-keyed shape above (Phase 3F-1, v4.11, corrected from an original `game_id`-keyed design never exercised by any code): SportsDataIO's DepthCharts payload is genuinely team-scoped, with no game reference at all. It is `team_id`-keyed instead, with the same append-only trigger and `captured_at` timestamp, written unconditionally on every capture (same "every poll is a new row" convention as `odds_snapshots`/`injury_reports`/`weather_snapshots`, not `team_stats`/`player_stats`' insert-on-change one):

```sql
create table depth_chart_snapshots (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references teams(id) on delete cascade,
  depth_chart_data jsonb not null,
  captured_at timestamptz not null default now()
);
```

A future "depth chart as it existed for game X" need should be derived from the latest team snapshot at/before that game's kickoff, not a second, competing game-keyed history table.

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

**`public_betting`/`sharp_money` — DEFERRED, EXTERNAL/VENDOR DEPENDENCY (v4.4, Decision 3, 2026-08-13).** Both columns stay in the schema as approved, but populating them requires a betting-percentage/handle data vendor this project has not selected or purchased — no vendor decision has been made, and no data is fabricated to fill the gap in the meantime. Until that vendor decision happens, both columns are `null`, which is semantically distinct from a computed neutral/zero value — any Phase 4/5 consumer reading `daily_game_intelligence` must treat `null` here as "unavailable," never coerce it to a default. `travel`/`rest`, by contrast, are populated at launch from data this project already has (existing Schedule/game/stadium data), per the same Decision 3.

**`rest` semantics (v4.5, Phase 3E-2, Decision 2, 2026-08-13).** `rest_days` = days between a team's most recent `games.status = 'final'` game and the current game's `scheduled_start`, counted as a UTC calendar-date difference (a documented initial-implementation simplification, not a claim of kickoff-hour precision). Only a finalized game counts as "the previous game" — a still-`scheduled`, `canceled`, or never-finalized `postponed` game is never used. A season opener (no previous final game exists) is `rest_days: null` with `season_opener: true` — the same null-not-neutral principle as `public_betting`/`sharp_money`, never a fabricated `0`. An elevated `rest_days` value (e.g. 14, after a bye) is left as the raw number; no separate `is_bye_week_return` boolean was added, per Mac's explicit instruction not to add speculative schema/fields ahead of an actual downstream consumer needing one.

**`stadium` shape (v4.12, Phase 3F-3, 2026-08-18).** Current-state venue metadata, surfaced from `games.stadium`/`.venue_lat`/`.venue_long`/`.venue_type` (the last three stored since v4.9/Phase 3E-6 but never previously read back into this working table): `{"name": ..., "latitude": ..., "longitude": ..., "venue_type": ...}`. Each field is independently `null` when the underlying `games` column is `null` — never fabricated, never defaulted — and the whole `stadium` value is `null` only when literally none of the four are known, matching every other category's "no data at all → null" convention in this payload. This is `games`' own current-state columns passed through, not a new historical venue system — a `games` row correction (e.g. a Schedule re-poll fixing a bad venue type) is reflected here on the next refresh, same as `teams`/`rest`/etc. Assembled by the single shared `app.master_refresh.game_refresh._build_stadium` helper, used identically by both Master Refresh's daily run and Pregame Worker's targeted T-minus-5 refresh — no duplicate assembly logic.

**`travel` semantics (v4.5, Phase 3E-2, Decision 3, 2026-08-13).** Defined as the distance from the venue of a team's previous `status = 'final'` game to the venue of its current game (game-to-game travel burden) — explicitly not home-city-to-current-stadium distance. **Deliberately left `null`/unavailable in Phase 3E-2's implementation:** SportsDataIO's Schedule response does include venue coordinates (`StadiumDetails.GeoLat`/`GeoLong`, CONFIRMED present in the live-captured fixture), but neither `ScheduleEntry` (the normalized adapter model) nor `games` currently carries them — everything past the stadium *name* is discarded during normalization. Populating `travel` for real requires (a) widening `ScheduleEntry` with venue coordinates and (b) durable coordinate storage (new nullable `games` columns, or a dedicated `stadiums` reference table, given a venue is reused across many games) — a schema decision deliberately deferred out of 3E-2's scope, tracked as a follow-up architecture item rather than solved by fabricating coordinates or adding scattered geo columns ad hoc. **Both (a) and (b) are now built** (v4.9, Phase 3E-6, Option A — `ScheduleEntry.venue_lat`/`.venue_long`, `games.venue_lat`/`.venue_long`), built for Weather Worker's own location needs rather than travel — `travel` itself is still `null`, still not computed anywhere. The durable coordinate storage this note asked for now exists as a foundation a later phase can build the actual distance calculation on; this note is not itself that phase.

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

### 4.3 Game Events / Play-by-Play (v4.26, IMPLEMENTED IN DEV 2026-09-04 — pre-9/9 minimum, raw capture only)

**Status update (v4.26, 2026-09-04): the table below is live in DEV** (migration `20260904160000_game_events_raw_capture.sql`, applied and verified — append-only trigger live-proven by a real rejected `UPDATE`). **What is NOT yet built: any typed-column normalization, any real MySportsFeeds/provider adapter wiring, and any actual invocation on a real game.** `app.persistence.game_events.write_raw_game_events` exists and is tested (respx-mocked and a live rollback-wrapped DEV insert), ready to be called once the 2026-09-09/10 live-game validation (`docs/ops/nfl-provider-decision-record.md`) actually runs — this entry does not itself call MySportsFeeds or any other provider. See `docs/ops/2026-data-preservation-readiness-plan-2026-09-04.md` for the full audit and sequencing this section supports.

**No play-by-play or game-event table has ever existed in this schema** (confirmed by direct search, Phase 8 Milestone 8.0 audit, 2026-09-04) — `player_stats`/`team_stats` are single, final, post-game snapshots with no record of how a final line was produced. This subsection is the minimum, provider-neutral shape needed to start closing that gap, **deliberately without locking any MySportsFeeds-specific (or any other single provider's) field names** — the live MySportsFeeds PBP/box-score response shape is not yet validated against a real, played game (gated on the 2026-09-09/10 opener per `docs/ops/nfl-provider-decision-record.md`), and inventing provider-specific fields ahead of that validation is explicitly out of scope.

```sql
create table game_events (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  provider_name text not null,              -- provenance: which provider this event came from
  provider_event_id text,                   -- provider's own play/event id, where one exists — nullable, unvalidated until a real payload is seen
  sequence_number integer,                  -- MANSA-derived ordering if the provider doesn't supply a clean one; provider's own sequence if it does — nullable pre-validation
  period text,                              -- quarter/half/OT, kept as text (not an enum) until real provider vocabulary is confirmed
  clock text,                               -- raw game-clock string as reported (e.g. "12:45") — kept as text, never parsed/typed ahead of seeing a real payload
  event_type text,                          -- conservative bucket (e.g. 'play'/'score'/'turnover'/'penalty'/'substitution'/'timeout'/'other') — NOT a fabricated fine-grained taxonomy; raw_payload carries the real detail
  description text,                         -- human-readable play description, if the provider supplies one
  score_home integer,                       -- running score after this event, if determinable
  score_away integer,
  involved_team_id uuid references teams(id),      -- nullable — the team "on" this event, if determinable
  involved_player_ids jsonb,                -- nullable array of player_id — populated only once player-identity resolution against a real payload is validated
  raw_payload jsonb not null,               -- the complete, unmodified provider response fragment for this event — the actual "capture first" mechanism; every other column above is a best-effort normalization on top of this, never a replacement for it
  captured_at timestamptz not null default now(),   -- MANSA's own ingestion clock — distinct from the in-game `clock` column
  created_at timestamptz not null default now()
);
create index idx_game_events_game_seq on game_events(game_id, sequence_number);
create index idx_game_events_game_time on game_events(game_id, captured_at desc);
```

**Append-only by design**, reusing `block_snapshot_updates()` verbatim — same trigger every other snapshot table in this document uses. A correction to an already-captured event is a new row, never an UPDATE, matching this document's own non-negotiable historical-integrity principle.

**Why `raw_payload jsonb not null` is the load-bearing column, not a convenience.** Every typed column above (`period`/`clock`/`event_type`/`score_home`/`score_away`/`involved_team_id`/`involved_player_ids`) is a normalization attempt that may legitimately come back `null` for a given event, a given provider, or before that provider's real shape is validated — the raw payload never does. This mirrors `player_stats.stats`'s own precedent exactly (v4.12.1: "jsonb preserves the complete provider stat payload," typed extension columns added only once a real, demonstrated consumer needs them) — **do not add a typed extension table (a hypothetical `game_events_nfl`) until Phase 8 Milestone 8.1+ actually needs one**, per that same precedent.

**What can be built safely before the live MySportsFeeds validation, and what must wait — the actual point of designing this table now:**
- **Safe now:** the table itself, its append-only trigger, and a capture path that writes `game_id`/`provider_name`/`raw_payload`/`captured_at` unconditionally, regardless of what shape `raw_payload` turns out to hold. This requires zero assumption about MySportsFeeds' (or any provider's) real field names.
- **Must wait for the 2026-09-09/10 live-game validation:** any normalization logic populating `period`/`clock`/`event_type`/`score_home`/`score_away`/`involved_team_id`/`involved_player_ids` from a real payload — attempting this before a real payload is seen would be exactly the "fabricate MSF fields" this section's own directive prohibited.

**Identity/idempotency deliberately not fully resolved here.** `provider_event_id` is the natural uniqueness key once a real provider payload confirms one exists and is stable — no uniqueness constraint is added in this reservation, since a premature one risks either rejecting legitimate re-captures (if the provider's own id isn't as stable as assumed) or silently deduplicating genuinely distinct events (if it collides across periods/games). Revisit once real data answers this, per the same "don't invent a constraint ahead of evidence" discipline as the threshold deferrals throughout Volume 4.

### 4.4 News History (v4.26, IMPLEMENTED IN DEV 2026-09-04 — pre-9/9 minimum)

**Status update (v4.26, 2026-09-04): the table below is live in DEV** (migration `20260904161000_news_article_history.sql`, applied and verified — append-only trigger live-proven by a real rejected `UPDATE`, and the insert-once-per-`(provider_name, article_url)` dedup live-proven by a real rollback-wrapped DEV insert-twice test: the second insert correctly contributed zero rows and the original `ingested_at`/`headline` were never touched). `app.workers.news_worker` now calls `app.persistence.news_article_history.write_news_article_history` alongside its existing `write_news` call, on every team fetch. `daily_game_intelligence.news` (§4.1) remains the only place News's *current-state* view lives — a single overwritten jsonb column with no history, re-confirmed by both the Phase 7 Milestone 7.0 audit and the Phase 8 Milestone 8.0 audit. This subsection implements the minimum append-only capture needed to preserve *when* a material news item (an injury, an inactive designation, a suspension, a lineup change, a trade) first became known — a real prerequisite for the News → contextual-intelligence connection Volume 4 §8.6 anticipates, and for News to ever be citable as market-movement evidence per Volume 4 §8.5's own existing finding.

```sql
create table news_article_history (
  id uuid primary key default gen_random_uuid(),
  provider_name text not null,              -- provenance: 'newsapi' | 'gnews' | future providers
  provider_article_id text,                 -- provider's own article id, where one exists (GNews supplies one; NewsAPI's adapter does not use one today)
  article_url text not null,                -- stable identity where available — confirmed stable within the sample tested in the 2026-09-03 GNews validation
  published_at timestamptz,                 -- the article's own claimed publication time, per the provider — nullable, since not every provider/article reliably supplies one
  ingested_at timestamptz not null default now(),  -- MANSA's own first-seen capture clock — THE fact this table exists to preserve; nothing today records this at all
  headline text,
  summary text,                             -- description/summary only by default — see the licensing caution below on full article content
  source_name text,
  related_team_ids jsonb,                   -- nullable array of team_id — team attribution, same resolution discipline `news_worker.py` already applies
  related_player_ids jsonb,                 -- nullable array of player_id — NEW relative to today's `NewsArticle` model, which has no player-level field at all; injury/inactive/trade news is fundamentally player-scoped, not only team-scoped
  raw_payload jsonb,                        -- permitted metadata only by default (see licensing caution) — nullable, since not every capture needs to retain the full response
  created_at timestamptz not null default now()
);
create unique index idx_news_article_history_identity on news_article_history(provider_name, article_url);
create index idx_news_article_history_ingested on news_article_history(ingested_at desc);
```

**Insert-once-per-`(provider_name, article_url)`, not "every poll is a new row."** Unlike `odds_snapshots` (where every poll capturing a *changed* value is a meaningful new row), a news article's own content is typically immutable once published — capturing the same still-unchanged article on every 15-minute News Worker cycle would produce pure duplicate rows, not history. The unique index on `(provider_name, article_url)` enforces "insert only the first time this article is seen," so `ingested_at` reliably answers "when did MANSA first learn this" — the actual fact this table exists to preserve. (Considered and rejected: mirroring `odds_snapshots`' "every poll is a new row" convention verbatim — correct for a value that genuinely changes over time, wrong for a publication that doesn't.)

**Licensing/redistribution caution — explicitly NOT resolved here.** Whether MANSA may store more than headline/summary/description-level metadata (i.e. full article body text) depends on each provider's own commercial-use and redistribution terms, which have not been independently confirmed for either NewsAPI Business or GNews Essential as part of this reservation (the GNews commercial-suitability question is explicitly still open per `docs/ops/news-provider-validation-gnews-2026-09-03.md`, criterion 11). **Default posture: `raw_payload` and `summary` carry metadata-level content only, never full article body text, until this is confirmed** — this is a real open compliance question for whoever eventually implements this table, not something this reservation decides.

**Append-only**, reusing `block_snapshot_updates()`.

**Relationship to `daily_game_intelligence.news` (unchanged by this section):** this table is new, additive history — it does not replace, migrate, or alter `daily_game_intelligence.news`'s existing current-state-only behavior. `app.workers.news_worker` writes to both: its existing upsert into `daily_game_intelligence.news` is unchanged, and it now also calls `write_news_article_history` alongside it, per team, every cycle.

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

**`prompt_version` is legacy/non-authoritative for per-agent reconstruction (v4.16, Milestone 4.8).** This column was written when `prompt_registry` modeled one prompt per recommendation cycle (the `nfl_single_v1.0`/`nfl_parlay_v1.0` recommendation-generation-prompt concept it still refers to) — a concept that predates Milestone 4.6's candidate-anchored architecture and Milestone 4.7's per-agent committee entirely. Once `prompt_registry` became the production source of each of the 12+ real agents' own system prompts (`prompt_name = agent_name`, each independently versioned — e.g. `injury_intelligence_agent → v3`, `weather_agent → v2` legitimately coexisting in the same cycle), a single scalar column on `recommendations` can no longer truthfully represent which prompt produced which finding. **`recommendation_agent_outputs.prompt_name`/`.prompt_version` (below) are the canonical per-agent Time Machine provenance going forward.** This column remains in place, unmodified in shape, for backward compatibility — not repurposed, not removed, per Mac's explicit instruction — but a future reader should not treat it as sufficient to reconstruct which prompt any individual agent used.

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
  candidate_key text,                        -- v4.14: identity of the specific wager evaluated, when applicable
  prompt_name text,                          -- v4.16: canonical per-agent prompt provenance, = agent_name
  prompt_version integer,                    -- v4.16: the exact prompt_registry.version actually used
  created_at timestamptz default now(),
  foreign key (prompt_name, prompt_version) references prompt_registry(prompt_name, version)
);
create index idx_rao_recommendation on recommendation_agent_outputs(recommendation_id);
create index idx_recommendation_agent_outputs_candidate_key on recommendation_agent_outputs(recommendation_id, candidate_key) where candidate_key is not null;
create index idx_recommendation_agent_outputs_prompt on recommendation_agent_outputs(prompt_name, prompt_version) where prompt_name is not null;
```
**`weight_applied` is a frozen copy of `agents.current_weight`, not a join.** This is a direct Time Machine requirement: if we only stored a reference to `agents.current_weight`, reconstructing a recommendation from three months ago would show *today's* weight, not the weight that was actually used to compute the consensus at the time — silently rewriting history. Every place this pattern applies (odds, weights, anything mutable) uses the same frozen-copy approach.

**`candidate_key` (v4.14, Phase 4 Milestone 4.6, Decision G):** a nullable text column identifying *the specific wager being evaluated* (e.g. `"g1:DraftKings:moneyline:Kansas City Chiefs:none"`) — distinct from, and not interchangeable with, `recommendation_id` (the overall recommendation-analysis cycle). Added because the sequential Decision & Advisory chain (Probability Modeling → Expected Value → Risk Manager → Bankroll Coach) evaluates a specific market/selection, not "the game" abstractly — `AgentOutput.directional_lean` can only speak to one side at a time, so one committee run must be scoped to one concrete candidate. `NULL` for every game-level fan-out output (Milestones 4.4/4.5, unchanged); populated only for candidate-level sequential outputs. **Deliberately no uniqueness constraint** — multiple evaluations of the same candidate over time are legitimate history, not an error; retry/versioning semantics for this identity aren't yet designed strongly enough to justify enforcing uniqueness at the database level. The partial index (`where candidate_key is not null`) supports the expected Phase 5 lookup pattern ("every candidate evaluated within this cycle") without indexing the majority of rows that have no candidate at all.

**`prompt_name`/`prompt_version` (v4.16, Phase 4 Milestone 4.8, Prompt Provenance decision):** the canonical, queryable, per-agent-output record of which exact `prompt_registry` row (`prompt_name = agent_name`, its own independently-incrementing `version`) produced this specific output — frozen at persist time, same pattern as `weight_applied`: a later change to which prompt version is currently active can never retroactively alter an already-persisted row. Nullable and backward-compatible — the pre-Milestone-4.8 rows this table already held stay `NULL` on both columns, and remain valid, queryable history exactly as before. Populated from the exact resolved `prompt_registry` row the orchestration layer used to build that agent's system prompt (`app.persistence.model_config.resolve_active_prompt`) — never a caller-supplied guess, never the currently-active prompt read again after the fact, never `agent_name` plus an assumed version, and never copied from `recommendations.prompt_version`. The composite foreign key to `prompt_registry(prompt_name, version)` is `MATCH SIMPLE` (Postgres default): a row with either column `NULL` is never checked against it, so the existing NULL-provenance rows are unaffected; a non-NULL pair must reference a real, once-registered prompt version. `prompt_registry` rows are never deleted by any code path (deprecation is a `status` update, not a `DELETE`), so this FK does not put historical provenance at risk of being orphaned under current application behavior.

### `consensus_snapshots`
```sql
create table consensus_snapshots (
  id uuid primary key default gen_random_uuid(),
  recommendation_id uuid not null references recommendations(id) on delete cascade,
  aggregate_confidence numeric(5,4) not null,
  agreement_variance numeric(5,4),           -- feeds the Elite-tier reconciliation threshold, Volume 2 §7
  model_routing_used jsonb,                  -- which models handled which agents this run
  second_pass_triggered boolean default false,
  candidate_key text,                        -- v4.15: identity of the candidate this consensus was computed for
  final_aggregate_confidence numeric,        -- v4.15: post-Meta/Elite-adjustment number, distinct from aggregate_confidence
  below_confidence_floor boolean,            -- v4.15: internal 0.55-threshold result, never a Phase-5 recommendation_type
  participation_metadata jsonb,              -- v4.15: configured/built/deferred/attempted/successful/failed/fan_out_status/committee_completeness
  created_at timestamptz default now()
);
create index idx_consensus_snapshots_candidate_key on consensus_snapshots(recommendation_id, candidate_key) where candidate_key is not null;
```

**Four columns added, v4.15 (Phase 4 Milestone 4.7, 2026-08-22), mirroring the `recommendation_agent_outputs.candidate_key` pattern (v4.14) exactly:**
- **`candidate_key`** — same identity, same no-uniqueness-constraint reasoning, same partial index — makes candidate identity first-class and queryable rather than buried inside `model_routing_used`.
- **`final_aggregate_confidence`** — the post-Meta-Agent/Elite-reconciliation-adjustment number. Kept as a genuinely separate column from `aggregate_confidence` (the pre-adjustment value, unchanged) rather than overloading one column with two meanings — a future reader must be able to see both the raw committee number and what it became after review.
- **`below_confidence_floor`** — the internal Phase-4 result of the 0.55 threshold check (Volume 4 §4.2) as a raw fact, explicitly NOT the same thing as a Phase-5 `recommendation_type = 'no_bet'` decision. Phase 4 computes and persists this; Phase 5 alone decides recommendation shape.
- **`participation_metadata`** — a full snapshot of `configured_agents`/`built_agents`/`deferred_agents`/`attempted_agents`/`successful_agents`/`failed_agents`/`fan_out_status`/`committee_completeness` for this specific historical run. Required because a failed or deferred agent leaves no row at all in `recommendation_agent_outputs` — this is the only durable record letting a future reader distinguish "0.71 confidence from 17/17 available agents" from "0.71 confidence while only 6/17 intended agents existed."

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

## 5A. Phase 5 Recommendation Product Layer (v5.0, Phase 5 Milestone 5.1, 2026-08-25)

**Resolves the load-bearing conflict between §5's `recommendations` (one row per game, frozen from Phase 4 Milestone 4.5's "Option C") and Volume 4 §9's Recommendation Strategy Engine, which needs shapes `recommendations` was never built to hold** — a `multiple_singles` product spanning several games, or a slate-wide `bankroll_preservation` verdict with no single game at all. Resolution (Mac's explicit decision): **preserve `recommendations`, `recommendation_agent_outputs`, and `consensus_snapshots` exactly as §5 already documents them — zero columns changed, zero semantics changed — and add a distinct product layer above them**, with first-class leg provenance back into that unchanged Phase 4 layer, never opaque JSON.

### `recommendation_products`
```sql
create table recommendation_products (
  id uuid primary key default uuid_generate_v7(),
  display_id text not null unique,           -- "{year}-{counter}", e.g. "2026-00007" — see display_id_counters below
  recommendation_type text not null check (recommendation_type in
    ('single','player_prop','multiple_singles','no_bet','bankroll_preservation',
     'same_game_parlay','multi_game_parlay')),
  scope text not null check (scope in ('game','slate')),
  game_id uuid references games(id),           -- set only when scope = 'game'
  recommendation_id uuid references recommendations(id),  -- set only when scope = 'game'
  master_refresh_run_id uuid not null references master_refresh_runs(id),  -- always set, both scopes
  min_required_tier text not null default 'free',
  status text not null default 'active' check (status in ('active','withdrawn')),
  withdrawn_at timestamptz,
  withdrawal_reason text,
  deleted_at timestamptz,
  created_at timestamptz not null default now()
);
```
**`scope` splits the table into exactly the two grains Volume 4 §9 actually needs:** `single`/`player_prop`/`no_bet`/`same_game_parlay` are `scope='game'`, anchored to one `game_id`/`recommendation_id` pair; `multiple_singles`/`bankroll_preservation`/`multi_game_parlay` are `scope='slate'`, anchored only to the `master_refresh_run_id` that produced them (a CHECK constraint enforces this pairing — see the migration for the exact SQL). `single` vs. `multiple_singles` is decided purely by how many candidates qualified across the WHOLE slate after same-market conflict resolution (one → `single`, two-or-more → `multiple_singles`), not by game count — one game can legitimately contribute more than one leg (e.g. a qualifying moneyline and a qualifying total are different markets).

**`no_bet` and `bankroll_preservation` carry zero `recommendation_legs` rows, by design — an explicit correction to an earlier draft of this schema that would have used fake `candidate_key = NULL` legs to represent "considered but not selected."** Their provenance is the `recommendation_id` (for a per-game `no_bet`) or `master_refresh_run_id` (for a slate-wide `bankroll_preservation`) columns above, directly — Milestone 5.2's Explainability Engine reconstructs "why nothing was recommended" by joining out from there to `recommendation_agent_outputs`/`consensus_snapshots`, never from a manufactured leg.

**`min_required_tier`/`status`/`withdrawn_at`/`withdrawal_reason`/`deleted_at` mirror `recommendations`'s own existing pattern exactly** (see §5 above) — this is the user-facing object, so it needs the same tier-gated RLS shape `recommendations` already has. Unlike `recommendations`, every OTHER column here is DB-enforced immutable after insert via a trigger that permits only `status`/`withdrawn_at`/`withdrawal_reason`/`deleted_at` to change.

**No `ev_per_dollar`/confidence column at this level, on purpose.** A `multiple_singles` product has no single scalar EV or confidence — inventing one would be exactly the "blended score" Mac's Decision Y explicitly forbade. Those numbers live only on `recommendation_legs`, per leg, where they're meaningful.

### `recommendation_legs`
```sql
create table recommendation_legs (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id) on delete cascade,
  consensus_snapshot_id uuid not null references consensus_snapshots(id),  -- the EXACT frozen evaluation this leg came from
  game_id uuid not null references games(id),
  recommendation_id uuid not null references recommendations(id),
  candidate_key text not null,
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
  unique (id, recommendation_product_id),
  unique (recommendation_product_id, leg_order),
  unique (recommendation_product_id, candidate_key)
);
create unique index idx_recommendation_legs_one_per_market
  on recommendation_legs (recommendation_product_id, game_id, market_type)
  where market_type in ('moneyline','spread','total');
```
**Represents only actually-selected wager legs** — never a placeholder for a candidate that was considered but not chosen (see `recommendation_products` above). Every market/odds/confidence field here is a frozen COPY taken directly from the same in-memory objects Phase 4's Recommendation Worker already computed for this exact cycle (never re-read back from persistence, never a live reference that could silently move) — the same Time Machine discipline `weight_applied`/`prompt_name`/`prompt_version` already established in §5. Fully append-only: no column here, including the withdrawal-adjacent ones, is ever legitimately updated after insert.

**`consensus_snapshot_id`, not `(recommendation_id, candidate_key)`, is the provenance anchor** — `consensus_snapshots` (§5) has no uniqueness constraint on that pair, since an Elite second-pass writes a brand-new row rather than updating; anchoring to the specific snapshot row is the only way to unambiguously say which pass's numbers a leg claims.

**`idx_recommendation_legs_one_per_market` is the DB-enforced version of the same-market mutual-exclusion rule** — at most one leg per `(product, game, market_type)` for moneyline/spread/total, since the two possible selections for one of those markets are opposing sides of the same wager and can never both be selected in one product. Player props are exempt: distinct props on the same game are independent markets, not opposing sides of one.

### `user_recommendation_selections`
```sql
create table user_recommendation_selections (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id) on delete cascade,
  recommendation_leg_id uuid references recommendation_legs(id) on delete cascade,  -- null = product-level-only state
  user_id uuid not null references auth.users(id) on delete cascade,
  risk_tolerance text not null check (risk_tolerance in ('conservative','moderate','aggressive')),
  bankroll_at_computation numeric(12,2),
  excluded_by_session_preferences boolean not null default false,
  full_kelly_fraction numeric(8,6),
  quarter_kelly_fraction numeric(8,6),
  risk_tolerance_multiplier numeric(5,4),
  stake numeric(10,2),
  created_at timestamptz not null default now(),
  foreign key (recommendation_leg_id, recommendation_product_id)
    references recommendation_legs(id, recommendation_product_id) on delete cascade
);
```
The per-user personalization layer — Kelly stake and session-preference exclusions, computed against the shared `recommendation_legs` above rather than duplicating any of its frozen candidate data. **Append-only, never overwritten** — but a BEFORE INSERT trigger (`enforce_urs_materiality`) suppresses an insert that's identical to that user's own most-recent row for the same `(product, leg)` key, so a harmless repeat view/refresh never creates an unbounded number of rows. The comparison is against the LATEST row only, not "any row ever" — required so a genuine revert (e.g. `moderate → aggressive → moderate`) is still recorded as a new observation rather than silently suppressed against older history, which would break reconstructing "what was true as of time T" for any T after the real revert. The suppression itself is race-free: the trigger takes a `pg_advisory_xact_lock` scoped to the `(user, product, leg)` key before comparing, so two simultaneous writes for the same key are serialized, never racing against a stale read.

### `display_id_counters`
```sql
create table display_id_counters (
  bucket_key text primary key,   -- currently the 4-digit activation year, e.g. "2026"
  counter integer not null default 0,
  updated_at timestamptz not null default now()
);

create function next_display_id_counter(p_bucket_key text) returns integer as $$
declare v_counter integer;
begin
  insert into display_id_counters (bucket_key, counter, updated_at) values (p_bucket_key, 1, now())
  on conflict (bucket_key) do update set counter = display_id_counters.counter + 1, updated_at = now()
  returning counter into v_counter;
  return v_counter;
end;
$$ language plpgsql;
```
**Genuinely atomic, not a read-then-write race:** `next_display_id_counter` wraps a single `INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING` statement — there is no separate prior read. The row lock backing the `ON CONFLICT`/`DO UPDATE` path is acquired as an intrinsic part of executing that one statement; a second concurrent caller for the same `bucket_key` blocks on that lock, then (Postgres's standard read-committed UPDATE re-check semantics) re-evaluates `counter + 1` against the value the FIRST transaction actually committed, never a value it cached before blocking. Two simultaneous activations therefore cannot receive the same counter. Exposed as an RPC (`/rest/v1/rpc/next_display_id_counter`) because PostgREST's table-level upsert support has no way to express a server-side increment expression — this is a transport wrapper around the same single atomic statement, not a different mechanism. A crash between generating a `display_id` and using it leaves a gap, never a collision — no-gaps was never a requirement.

### `conversations` (v3.0's originally-specified shape, built now per Phase 5 rather than Phase 1)
```sql
create table conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_preferences jsonb not null default '{}',
  created_at timestamptz not null default now()
);
```
Exactly Volume 4 §7's own originally-specified shape (`session_preferences` is a column here, not a separate table). `conversation_messages` is deliberately NOT built yet — deferred to Phase 6 — but nothing here forecloses adding it later; its FK will simply target `conversations(id)`, untouched by this migration. Built now, not in Phase 1 as the roadmap's v3.0 amendment originally scoped it, because Milestone 5.1's Strategy Engine is the first thing that actually needs to read a session-preference exclusion; a schema-only table with nothing reading it yet would have sat unused since Phase 1.

---

## 5B. Phase 5 Explainability Engine (v5.1, Phase 5 Milestone 5.2, 2026-08-25)

**Deterministic V1 only — no LLM narrative layer, no live model calls.** Explains an already-persisted §5A `SlateStrategyResult`; never re-ranks, never re-runs Strategy selection, never changes `recommendation_type`/EV/confidence/eligibility/stake/status. Explaining a decision and making one are structurally different operations — there is no shared code path between them (see `app.orchestration.explainability`'s module docstring). Two new tables, both additive; `explainability_payloads` (§5, Phase 1) is unchanged — its sole FK target (`recommendations.id`) has no path to this product layer, and it was never given append-only protection, so repointing it would both widen its grain incorrectly and quietly relax a guarantee this schema otherwise enforces everywhere.

### `recommendation_product_explanations`
```sql
create table recommendation_product_explanations (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null unique references recommendation_products(id) on delete cascade,
  why_this_shape text not null,
  why_not_other_shapes text,
  rejected_alternatives jsonb not null default '[]'::jsonb,
  data_limitations text,
  narrative_summary text,  -- reserved for a future LLM narrative layer, NOT built in Milestone 5.2
  created_at timestamptz not null default now()
);
```

### `recommendation_leg_explanations`
```sql
create table recommendation_leg_explanations (
  id uuid primary key default uuid_generate_v7(),
  recommendation_leg_id uuid not null unique references recommendation_legs(id) on delete cascade,
  why_selected text not null,
  strongest_evidence text not null,
  contributing_agents jsonb not null default '[]'::jsonb,
  biggest_risks text not null,
  rejected_alternatives jsonb not null default '[]'::jsonb,
  would_change_mind_if text,
  narrative_summary text,  -- same reservation as the product-level column above
  created_at timestamptz not null default now()
);
```
Both tables enforce **exactly one explanation row per product/leg, ever** — `UNIQUE(recommendation_product_id)`/`UNIQUE(recommendation_leg_id)` plus a full-block `BEFORE UPDATE` trigger, not an open-ended version history. This is a deliberate departure from tables like `consensus_snapshots` that legitimately allow multiple rows per parent: those exist because the underlying computation can genuinely differ on a retry (an Elite second pass recomputes `consensus_snapshots` differently); Milestone 5.2's explanation logic is 100% deterministic over already-frozen Phase 4/5.1 facts, so the same product/leg can only ever produce the same explanation. A future bug fix in the deterministic logic changes what a NEW product's explanation looks like — it never rewrites history, the same discipline already applied to `recommendation_agent_outputs`/`recommendation_legs`.

**`contributing_agents`/`rejected_alternatives` stored as `jsonb` are a frozen, point-in-time render of already-first-class rows** (`recommendation_agent_outputs` for the former, `app.features.strategy.RejectedCandidate` for the latter) — exactly the same denormalization discipline already established by `recommendation_snapshots.agent_outputs_snapshot` (§5), not the kind of "opaque JSON hiding a missing FK" this schema otherwise rejects.

**`contributing_agents` is the GAME-LEVEL committee only** (Injury Intelligence, Weather, Vegas Line, Closing Line Movement, Travel & Fatigue, Rest Days) — the same `agent_rows` `app.features.consensus.compute_consensus` already consumes for that leg's candidate. Probability Modeling/EV/Risk Manager/Bankroll Coach are candidate-level sequential agents, never voters, and are read separately (`biggest_risks` reads Risk Manager's own already-frozen `recommendation_agent_outputs` row directly).

**`would_change_mind_if` is NULL unless it can be a verbatim quote.** Populated only from the single highest-weighted supporting agent's own already-frozen `would_change_mind_if` field (captured since Milestone 4.2) — never synthesized by Explainability itself. NULL is preferable to invented intelligence.

**Provenance chain** (Time Machine reconstruction path for one leg's explanation): `recommendation_product_id → recommendation_leg_id → recommendation_legs.recommendation_id → recommendation_legs.candidate_key → recommendation_legs.consensus_snapshot_id → recommendation_agent_outputs (game-level, for contributing_agents; candidate-level, for biggest_risks) → prompt_name/prompt_version → model/version info (§8) → weight_applied → the frozen odds/point/line and modeled probability/EV already on `recommendation_legs` → `final_aggregate_confidence` → participation metadata (`consensus_snapshots.participation_metadata`, v4.15) → the Strategy Engine's own decision trace (`app.features.strategy.RejectedCandidate`/`RejectionReason`)`. No step in this chain is re-derived or re-computed by Explainability — every value is read back from a row Phase 4 or Milestone 5.1 already wrote.

**Shared data, not per-user** — same "RLS enabled, no select policy, service-role only, consumed through the API Gateway" convention already applied to `recommendation_agent_outputs`/`consensus_snapshots`/`recommendation_legs`.

**Known V1 scope boundary, not a fabrication risk:** the approved rejection-reason vocabulary includes `UNSUPPORTED_MARKET_TYPE`/`PARLAY_CAPABILITY_UNAVAILABLE` as future-extensible values, but neither is wired into any explanation output yet — candidate generation already excludes prop markets before they ever reach the Strategy Engine, and parlay candidates are never generated at all, so no candidate currently reaches Strategy that would produce either rejection. Adding those constants without a real code path behind them would be exactly the kind of invented category this module's own docstring forbids; they remain reserved, unused vocabulary until a real condition exists to populate them.

---

## 5C. Phase 5 Time Machine Activation Snapshots (v5.2, Phase 5 Milestone 5.3, 2026-08-25)

**Resolves the same load-bearing conflict §5A resolved for the product layer, one level up: the legacy `recommendation_snapshots` (§5, Phase 1) is one row per Phase 4 `recommendations.id`, giant JSONB blobs, `ON DELETE CASCADE` from a soft-deletable parent, zero rows, zero code — confirmed by direct inspection to be exactly as unbuilt as `explainability_payloads` and structurally unable to represent a slate-scoped `multiple_singles`/`bankroll_preservation` product, a `no_bet` product, multiple legs, or Explainability provenance.** Resolution (Mac's explicit decision, Decisions AO-BE): leave `recommendation_snapshots` completely untouched as legacy, and add a MANIFEST — not another duplicate-blob snapshot table — that composes already-frozen §5A/§5B rows by FK.

### `recommendation_activation_snapshots`
```sql
create table recommendation_activation_snapshots (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null unique references recommendation_products(id) on delete cascade,
  activated_at timestamptz not null default now(),
  strategy_version text not null,
  recommendation_product_explanation_id uuid references recommendation_product_explanations(id),
  created_at timestamptz not null default now()
);
```
One row per `recommendation_products` row, ever (`UNIQUE` + append-only `BEFORE UPDATE` trigger). **Composes, never duplicates** — no odds/EV/confidence/explanation-text value is copied here; those already live, frozen, on `recommendation_legs`/`recommendation_product_explanations`/`recommendation_leg_explanations` since Milestones 5.1/5.2. `strategy_version` (Decision AW) freezes which `app.features.strategy` logic version decided this product's shape — a sixth, independent kind of version alongside `prompt_version`/`agent_version`/`weight_applied`'s own frozen-copy pattern (§5's "five separate versioning columns" principle, extended). `recommendation_product_explanation_id` is nullable — Milestone 5.2's own per-unit explanation-generation failure must never block activation-snapshot creation for the underlying Strategy decision that already succeeded.

### `recommendation_activation_snapshot_legs`
```sql
create table recommendation_activation_snapshot_legs (
  id uuid primary key default uuid_generate_v7(),
  activation_snapshot_id uuid not null references recommendation_activation_snapshots(id) on delete cascade,
  recommendation_leg_id uuid not null references recommendation_legs(id),
  leg_order integer not null check (leg_order > 0),
  created_at timestamptz not null default now(),
  unique (activation_snapshot_id, recommendation_leg_id),
  unique (activation_snapshot_id, leg_order)
);
```
A normalized join table, deliberately never an array/JSON column (Decision AO — this project has consistently rejected array/JSON representations of first-class relational identity) — freezes exactly which legs belonged to a `single`/`multiple_singles` product at activation, and their activation-time presentation order. Reconstruction reads this ordered by `leg_order`; it never re-derives historical ordering by rerunning Strategy's current ranking logic. Append-only.

### `recommendation_activation_snapshot_source_products`
```sql
create table recommendation_activation_snapshot_source_products (
  id uuid primary key default uuid_generate_v7(),
  activation_snapshot_id uuid not null references recommendation_activation_snapshots(id) on delete cascade,
  source_recommendation_product_id uuid not null references recommendation_products(id),
  created_at timestamptz not null default now(),
  unique (activation_snapshot_id, source_recommendation_product_id)
);
```
For a `bankroll_preservation` activation, freezes the exact per-game `no_bet` products that constituted that slate-level decision (Decision AR) — deliberately not left to a future reader to rediscover via `master_refresh_run_id` alone, which could become historically ambiguous if more products are later associated with the same run. This is historical composition/provenance, not betting-leg identity — no fake wager legs are ever created for either `no_bet` or `bankroll_preservation` (unchanged since §5A). Append-only.

### `recommendation_product_lifecycle_events`
```sql
create table recommendation_product_lifecycle_events (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id) on delete cascade,
  event_type text not null check (event_type in ('ACTIVATED', 'WITHDRAWN', 'SOFT_DELETED')),
  event_timestamp timestamptz not null default now(),
  reason text,
  created_at timestamptz not null default now()
);
create index idx_recommendation_product_lifecycle_events_product on recommendation_product_lifecycle_events (recommendation_product_id, event_timestamp);
```
An append-only EVENT LOG, not a "current state only" column set (Decision AZ) — `recommendation_products.status`/`.withdrawn_at`/`.withdrawal_reason` (§5A) already track the current lifecycle state, but preserve only the LATEST value if a product were ever withdrawn more than once; this table preserves the full history of every transition, live-proven to allow multiple events per product without any uniqueness conflict. Only the lifecycle states that already exist in the current product model — explicitly NOT the future `BET NOW`/`WAIT`/`PASS`/`LINE LOST` execution states (Volume 4 §9.5, not yet implemented, Decision BE) — no speculative event values are reserved ahead of that capability's own future implementation. Append-only.

**Two real provenance gaps found during the Milestone 5.3 inspection, closed here rather than knowingly carried into live-model operation (Decisions AT/AV):**
- **`consensus_snapshots` gains the append-only `BEFORE UPDATE` trigger** every sibling table in the historical chain already had (`recommendation_agent_outputs`, `recommendation_legs`, `recommendation_products`, both explanation tables) — a real, live-verified gap: this table had no DB-level append-only enforcement at all, convention-only, despite the Time Machine referencing it as first-class historical evidence (`recommendation_legs.consensus_snapshot_id`).
- **`recommendation_agent_outputs` gains nullable `model_name text`, `provider text`, `used_fallback boolean`** — the ACTUAL model/provider that produced each output (from `ModelResponse.usage`), never merely "the routing rule currently says model X." Historical rows written before this migration remain `NULL` forever — never backfilled with a guess. `apps/ai-orchestrator`'s `consensus_snapshots.model_routing_used` jsonb value shape also corrected from a bare requested-model string to `{"model", "provider", "used_fallback"}` reflecting the actual responding agent call, for the same reason.

**`recommendation_product_explanations`/`recommendation_leg_explanations` (§5B) each gain `explainability_version text not null default 'v1'`** (Decision AX) — frozen directly on the actual explanation rows, distinguishing "same evidence, same explanation algorithm" from "same evidence, the algorithm changed" for any historical explanation. Always set explicitly by the application at insert time; the database default is a defensive backstop only, live-verified to reject an explicit `NULL`.

**A genuine, disclosed architecture gap found but NOT fixed here (out of Milestone 5.3's authorized scope):** `app.models.retry_policy.RetryEngine.execute` is called with a single `ModelRequest` shared by both the primary and fallback attempts — there is no mechanism to swap in the fallback's own model name when a fallback is actually used. Both real adapters send `request.model` literally as the provider API's model parameter, so a real fallback call today would ask the fallback provider to serve the primary's model name. Invisible until Milestone 5.3's own new tests exercised a real fallback scenario for the first time — every model call in this codebase to date has used `FakeModelAdapter`, which never validates the model string it's handed, so this has had zero live impact. `used_fallback` is still correctly recorded (it comes from the retry engine's own bookkeeping); `model_name` in that one scenario is provably wrong. Flagged for a dedicated future fix (Milestone 4.3's `RetryEngine`/`app.orchestration.fanout`/`sequential`/`consensus`'s shared `ModelRequest`-building pattern), not silently worked around.

**Immutability/cascade invariant, documented as a Time Machine assumption rather than changed:** `recommendations` (Phase 4) → `recommendation_agent_outputs`/`consensus_snapshots` remain `ON DELETE CASCADE` (Decision AU, unchanged from Phase 4) — no physical-delete application code path exists anywhere in this codebase (confirmed by a full grep; the one `.delete()` call anywhere is `apps/sports-intel-layer/app/demo/reset.py`, hard-isolated to the `demo` Supabase project and touching none of these tables), and the Phase 5 layer's own `NO ACTION` FKs from `recommendation_products`/`recommendation_legs` to `recommendations` already practically block deleting an analysis cycle a Phase 5 product still references. If future work ever introduces real deletion of a `recommendations` row, this cascade behavior must be re-inspected before that capability is allowed.

---

## 5D. Phase 5 Postgame Review Grading Layer (v5.3, Phase 5 Milestone 5.4, 2026-08-27)

**Resolves the same class of conflict §5A/§5C already resolved, one more time: the legacy `postgame_reviews` (§7) FKs to the legacy Phase 4 `recommendations` cycle row, not the Phase 5 product/leg layer — no product/leg awareness, no append-only trigger, no deterministic outcome column at all, every field is narrative text or an agent-name array.** Resolution (Mac's explicit decision, Decisions BG-BZ): leave `postgame_reviews` completely untouched as legacy (not repointed, not deleted, its fixture row not migrated) — same "leave as legacy, build the correct additive layer above it" pattern as `explainability_payloads` (§5B) and `recommendation_snapshots` (§5C).

**Narrow schema inspection conclusion (performed before this migration, per Mac's explicit instruction): three new tables, not four, not one polymorphic table.** Leg-scope and product-scope were kept separate rather than one `grade_events` table with nullable `leg_id`/`product_id` columns — a single table would need a CHECK ensuring exactly one of two nullable parent FKs is set, plus a rollup-only column meaningless for leg-scoped rows, exactly the "ambiguous nullable-parent design" the inspection was told to avoid. A separate leg-level narrative table was considered and rejected — nothing in Volume 4's nine-question Explainability spec or this milestone's decisions calls for one; weather/injury/agent-correctness narrative is naturally slate-of-legs-level, matching the legacy `postgame_reviews` shape.

### `recommendation_leg_grade_events`
```sql
create table recommendation_leg_grade_events (
  id uuid primary key default uuid_generate_v7(),
  recommendation_leg_id uuid not null references recommendation_legs(id),
  game_id uuid not null references games(id),
  grading_version text not null,
  outcome text not null check (outcome in ('WIN', 'LOSS', 'PUSH', 'VOID_NO_ACTION', 'PENDING_MISSING_DATA')),
  authoritative_result jsonb not null,
  graded_at timestamptz not null default now(),
  is_correction boolean not null default false,
  corrects_grade_event_id uuid references recommendation_leg_grade_events(id),
  correction_source text check (correction_source in ('stat_correction', 'grading_rule_change', 'manual_review')),
  correction_reason text,
  created_at timestamptz not null default now()
);
create unique index idx_leg_grade_events_original_per_version
  on recommendation_leg_grade_events (recommendation_leg_id, grading_version) where is_correction = false;
```
One deterministic grade per leg per `grading_version`, ever, for an ORIGINAL grade (partial unique index) — a correction is a separate row with `is_correction = true` and `corrects_grade_event_id` pointing at what it supersedes, never an UPDATE (append-only `BEFORE UPDATE` trigger, live-proven). `authoritative_result` freezes exactly the final-result facts the grade was computed against — never a live pointer to mutable `games.final_score`/`team_stats`/`player_stats` — so a later stat correction can never retroactively change what a historical grade "saw." **Idempotent-retry vs. legitimate-regrade (Decision BQ) is DB-enforced, not application-memory-only**: a worker's create-or-get for the original grade of a version hits the partial unique index on retry; a genuine correction (different `authoritative_result`) is a new row the index does not block.

### `recommendation_product_grade_events`
```sql
create table recommendation_product_grade_events (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id),
  grading_version text not null,
  outcome text not null check (outcome in ('WIN', 'LOSS', 'PUSH', 'VOID_NO_ACTION', 'PENDING_MISSING_DATA', 'NOT_APPLICABLE', 'MIXED_SETTLED')),
  leg_outcome_counts jsonb,
  computed_at timestamptz not null default now(),
  is_correction boolean not null default false,
  corrects_grade_event_id uuid references recommendation_product_grade_events(id),
  correction_source text check (correction_source in ('stat_correction', 'grading_rule_change', 'manual_review')),
  correction_reason text,
  created_at timestamptz not null default now()
);
```
Mirrors the leg table's append-only/idempotency design exactly. `single` mirrors its one leg's outcome verbatim (`leg_outcome_counts = NULL`). `no_bet`/`bankroll_preservation` are always `NOT_APPLICABLE` (Decisions BL/BM) — no retrospective win/loss is invented for an abstention, since no Blueprint-approved rule for "was passing correct?" exists yet. `multiple_singles` is `PENDING_MISSING_DATA` until every leg has a terminal grade, then `MIXED_SETTLED` with the full per-outcome breakdown in `leg_outcome_counts` (Decision BK) — the rollup is a derived summary; the individual leg results remain the first-class record in `recommendation_leg_grade_events`, never collapsed away.

### `recommendation_product_postgame_reviews`
```sql
create table recommendation_product_postgame_reviews (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id),
  product_grade_event_id uuid not null references recommendation_product_grade_events(id),
  grading_version text not null,
  postgame_review_version text not null,
  outcome_summary text,
  why_it_won_or_lost text,
  factual_deltas jsonb,
  correct_agents text[],
  underperforming_agents text[],
  learning_notes text,
  generated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create unique index idx_postgame_reviews_product_version
  on recommendation_product_postgame_reviews (recommendation_product_id, postgame_review_version);
```
Strictly downstream of an already-persisted `product_grade_event_id` (Decision BU) — the LLM narrative layer has no field capable of representing a grade, EV, confidence, or historical Explainability value, structurally, not just by convention. `GRADING_VERSION` and `POSTGAME_REVIEW_VERSION` are independent (Decision BN/BO) — the deterministic rules and the narrative-generation logic can evolve on separate timelines. `factual_deltas` is deterministic-derivation-only (weather/injury/line-movement changes between activation and kickoff) and conservatively `None` in this milestone (no snapshot-diffing infrastructure was built) — honest absence, never an approximation. `correct_agents`/`underperforming_agents` are populated only when an agent's directional call can be objectively compared to the realized game direction (Decision BT) — `NULL` (not `[]`) when that comparison is impossible (a push/void/pending leg has no "reality was on this side" fact to compare against), never confidence- or majority-based. Append-only.

**Reconciliation-eligibility, the actual grading-readiness condition (Decision BH):** `games.status = 'final'` is necessary but not sufficient — the Postgame Ingestion Worker's own bounded reconciliation window (§4, Volume 2 §8) can still correct `team_stats`/`player_stats`/`final_score` for up to 72 hours after finalization. Grading a `final` game waits until `now >= games.finalized_at + 72h` (the same final checkpoint `app.workers.reconciliation.CHECKPOINT_OFFSETS` already uses, imported rather than duplicated as a new number) before treating its stats as authoritative. `postponed`/`canceled` games grade immediately as `VOID_NO_ACTION` — no reconciliation process exists for them to wait on. **A disclosed, not silently worked-around, limitation:** `is_reconciliation_complete`'s own `checks_done` state is held only in the Postgame Worker's calling process's memory (no DB persistence layer exists for it yet) — a separate service cannot read it directly, so this derived wall-clock condition is used instead. It does not verify every individual checkpoint actually ran successfully, only that enough time has passed for all of them to have had their chance.

**Carry-Forward Gap 1 (from the Milestone 5.4 pre-implementation inspection), closed as a small corrective patch before this milestone's own build began:** `app.models.retry_policy.RetryEngine.execute` previously ran the fallback candidate against the exact same `ModelRequest` built for the primary, so a real fallback call would have asked the fallback provider to serve the primary's model name, and `model_name` provenance would echo the primary's model even when the fallback actually served the response. Fixed (Decision BF) by accepting an explicit `fallback_model` and swapping it into a per-candidate request via `dataclasses.replace` immediately before that candidate's own attempts. `provider`/`used_fallback` were never affected by this bug (both are set by the retry engine itself, never from the request).

---

## 5E. Phase 5 Adaptive Agent Weighting — Propose-Only V1 (v5.4, Phase 5 Milestone 5.5, 2026-08-27)

**V1 is PROPOSE-ONLY.** Nothing in this section, or anywhere in Milestone 5.5, writes `agents.current_weight`. Every table and function here computes and preserves what a weight change WOULD be under Volume 4 §6.1's formula and guardrails — applying one to `agents.current_weight` is a separate, not-yet-authorized future capability. **IMPLEMENTATION VALIDATION vs. EMPIRICAL VALIDATION:** this layer is proven correct against deterministic fixture evidence (the same discipline as every other Phase 5 milestone). As of this milestone, zero real graded recommendations exist anywhere in this system (live-verified: `recommendation_products`/`recommendation_legs`/every grade-event table all had zero rows at inspection time) — a persisted proposal is never a claim of empirical validation, improved betting performance, or a real-world-deserved adjustment.

**"200 recommendations" (§6.1's own guardrail text), reinterpreted for the Phase 5 architecture that didn't exist when §6 was written:** 200 CLASSIFIABLE GRADED-LEG OBSERVATIONS PER AGENT. An observation counts only when the leg has an authoritative deterministic grade (§5D) producing a realized `WIN`/`LOSS` direction, the agent's own game-level output for that leg's cycle succeeded, and the agent's `directional_lean` is on-axis (matches or opposes the realized direction) per §4.1's own `lean_factor` three-state rule. Never counted: failed agents, abstentions, off-axis outputs, `PUSH`/`VOID_NO_ACTION`/`PENDING_MISSING_DATA`/`NOT_APPLICABLE` legs, `no_bet`/`bankroll_preservation` products, or `player_prop` legs (never graded at all, §5D). `multiple_singles` contributes observations independently per leg, never per product.

### `adaptive_weight_proposals`
```sql
create table adaptive_weight_proposals (
  id uuid primary key default uuid_generate_v7(),
  agent_id uuid not null references agents(id),
  previous_weight numeric not null,
  raw_proposed_weight numeric,
  guardrail_adjusted_proposed_weight numeric,
  applied_weight numeric,
  evaluation_window_start date not null,
  evaluation_window_end date not null,
  sample_size integer not null,
  roi numeric,
  committee_average_roi numeric,
  performance_delta numeric,
  learning_rate numeric not null,
  weighting_version text not null,
  status text not null check (status in ('proposed', 'rejected_insufficient_sample')),
  rejection_reason text,
  is_correction boolean not null default false,
  corrects_proposal_id uuid references adaptive_weight_proposals(id),
  created_at timestamptz not null default now()
);
create unique index idx_adaptive_weight_proposals_original_per_window
  on adaptive_weight_proposals (agent_id, evaluation_window_start, evaluation_window_end, weighting_version)
  where is_correction = false;
```
One row per `(agent, window, weighting_version)` evaluation, append-only (`BEFORE UPDATE` trigger, live-proven). `applied_weight` is always `NULL` in V1 — reserved for a future, separately-authorized promotion mechanism; no code path anywhere sets it. `raw_proposed_weight`/`guardrail_adjusted_proposed_weight`/`roi`/`committee_average_roi`/`performance_delta` are `NULL`, never a fabricated zero, whenever `sample_size = 0` makes them undefined. `learning_rate` is frozen per row (Decision 9/28 — `0.25`, an APPROVED V1 DEFAULT, NOT EMPIRICALLY OPTIMIZED, SUBJECT TO FUTURE REVIEW) so a future change to the constant is historically traceable, never silently reinterpreting an old proposal. Idempotent-retry vs. legitimate-correction is DB-enforced via the same partial-unique-index pattern §5D's grade-event tables already established — a worker's create-or-get for the original evaluation of a window hits the index on retry; a genuine correction (new evidence from a Milestone 5.4 grade correction) is a separate `is_correction = true` row the index does not block.

### `adaptive_weight_proposal_observations`
```sql
create table adaptive_weight_proposal_observations (
  id uuid primary key default uuid_generate_v7(),
  proposal_id uuid not null references adaptive_weight_proposals(id) on delete cascade,
  recommendation_leg_grade_event_id uuid not null references recommendation_leg_grade_events(id),
  classification text not null check (classification in ('correct', 'underperforming')),
  directional_lean text not null,
  notional_pnl numeric not null,
  created_at timestamptz not null default now(),
  unique (proposal_id, recommendation_leg_grade_event_id)
);
```
Normalized evidence rows, never opaque JSON — one row per graded leg that actually counted toward a proposal, giving full provenance to reproduce any evaluation's evidence population by querying this table directly. `notional_pnl` uses a disclosed, symmetric pricing approximation (`app.features.adaptive_weighting`'s own module docstring has the full truth table): exact when the classification matches the recommended leg's own realized side (its frozen `decimal_odds`/outcome apply directly), a flat unit-stake proxy otherwise (the opposite side's real price is never known — there is no second, independently-priced line for it anywhere in this system). Append-only.

**Market-type provenance preserved, segmentation NOT built (Decision 3).** Neither table has a `sport`/`market_type` column — V1 keeps the Blueprint's existing global-per-agent weight model exactly. `recommendation_legs.market_type` remains reachable from any `adaptive_weight_proposal_observations` row via its `recommendation_leg_grade_event_id` → `recommendation_leg_id` chain, so a future per-market-type weighting capability could be built without re-deriving lost provenance — this section does not redesign the weighting system around segmentation now, per explicit instruction.

**CLV (Closing Line Value) has zero role here** — it remains unavailable (§5D/Decision BR, reaffirmed, not re-litigated) and is never read, computed, or persisted anywhere in this layer.

**No absolute min/max weight bound, no cross-committee normalization, no cooldown period exist in the Blueprint** — none are invented here (Decisions 11/12/13); V1's only bounds are the ±10% per-evaluation cap and the two guardrails above. Idempotency (Decision 13) substitutes for a cooldown: identical evidence/window/version can never produce a duplicate proposal, but a genuinely new evaluation window or new evidence can always produce a new one.

---

## 5F. Physical Deletion Prohibition — Phase 5 Evidentiary Records (Pre-Phase-6 Operational Readiness Gate, 2026-08-27)

**Physical `DELETE` of any Phase 5 evidentiary/historical row is prohibited, by policy, for every table listed below.** The Phase 5 Closeout Audit found that `UPDATE` immutability on these tables is DB-enforced (`BEFORE UPDATE` block triggers, live-verified on every one), while physical `DELETE` protection is partly structural/incidental rather than an explicit DB-level guarantee: no table here has a `DELETE`-blocking trigger, and one concrete path exists today — `recommendation_legs.recommendation_product_id → recommendation_products(id)` is `ON DELETE CASCADE` — under which an **ungraded** product's legs could cascade-delete if a future code path ever physically deleted a `recommendation_products` row (a graded leg is already protected, since `recommendation_leg_grade_events.recommendation_leg_id → recommendation_legs(id)` is `NO ACTION` and would block the cascade).

**Decision:** no new trigger is added here, and the schema is left unchanged. Volume 5/Phase 6 has no stated requirement for physically deleting a recommendation, product, leg, grade, review, or weighting proposal — every "remove" concept already has a soft-delete mechanism (`recommendation_products.deleted_at`/`.status='withdrawn'`, `recommendation_product_lifecycle_events.event_type='SOFT_DELETED'`, Volume 3 §5A/§5C). Phase 6 is expected to remain soft-delete-only for all of the tables below; this section makes that expectation explicit and binding rather than assumed. If a future phase's API genuinely requires physical deletion of any of these tables, the correct sequence is: STOP, return a specific DB-level preservation proposal (e.g. an explicit `block_*_deletes()` trigger mirroring the existing `block_*_updates()` pattern, or converting the one `ON DELETE CASCADE` above to `NO ACTION`), and get it approved before that API is built — never add the capability first and reconcile the schema after.

**Tables this prohibition covers:** `recommendation_products`, `recommendation_legs`, `recommendation_product_explanations`, `recommendation_leg_explanations`, `recommendation_activation_snapshots`, `recommendation_activation_snapshot_legs`, `recommendation_activation_snapshot_source_products`, `recommendation_product_lifecycle_events`, `recommendation_leg_grade_events`, `recommendation_product_grade_events`, `recommendation_product_postgame_reviews`, `adaptive_weight_proposals`, `adaptive_weight_proposal_observations`, and the pre-existing `consensus_snapshots`/`recommendation_agent_outputs`. (`user_recommendation_selections` is deliberately excluded from this list — its `ON DELETE CASCADE` from `auth.users` is an intentional, already-approved account-deletion behavior, Volume 3 §5A, a different category of concern than committee/grading/weighting evidentiary history.)

---

## 5G. Recommendation Lifecycle & Change Events (v4.27, ARCHITECTURE RESERVATION ONLY, proposed 2026-09-04 — nothing described in this section exists in code today)

**HQ directive (2026-09-04): formally define what happens when MANSA changes its view after a recommendation has already been activated.** Full report: `docs/ops/recommendation-lifecycle-spec-2026-09-04.md`. This section proposes the minimum additive schema such a policy needs; none of it is authorized to build yet — **PLANNING ONLY**, same discipline as §4.3/§4.4 before their own later implementation entries.

**Core principle carried over verbatim from HQ's directive:** once a `recommendation_products` row is activated, MANSA must never rewrite or erase what it originally recommended. `recommendation_legs` already guarantees this at the leg-data level (100% immutable, zero UPDATE path anywhere in this codebase — confirmed by direct inspection during this pass). This section closes the one remaining gap: there is today no vocabulary for recording **that something changed and why**, short of an outright `WITHDRAWN`.

**Three axes already exist in this Blueprint and must not be collapsed into one during this design — confirmed still valid, restated for this section's own scope:**
- **STRATEGY** (§5A above; Volume 4 §9) — does the candidate still qualify at all? Binary, `recommendation_products.status`.
- **EXECUTION TIMING** (Volume 4 §9.5, future, unimplemented) — is the *current price* right to act on *now*? (`BET NOW`/`WAIT`/`PASS`/`LINE LOST`.)
- **ANALYTICAL VALIDITY / CHANGE COMMUNICATION** (this section, new) — has new information made the ORIGINAL activated call stronger, weaker, or obsolete — independent of whether the user has already acted on it? This is the axis HQ's directive actually asks for: it answers "should a user who saw this at 10:00 AM know something changed by 11:30 AM," not "is the price still good" (§9.5) and not "did we already flip the switch" (§5A's `status` alone).

**No speculative reservation of §9.5's own execution states is made here** — exactly the same discipline `recommendation_product_lifecycle_events`'s original v4.21 note already applied to itself (Decision AZ/BE: "explicitly NOT the future `BET NOW`/`WAIT`/`PASS`/`LINE LOST` execution states... no speculative event values are reserved ahead of that capability's own future implementation"). This section's new vocabulary is additive to that same table, not a redesign of it, and stays strictly on the analytical-validity axis.

### `recommendation_product_lifecycle_events` — proposed `event_type` extension

Current (live, Milestone 5.3): `check (event_type in ('ACTIVATED', 'WITHDRAWN', 'SOFT_DELETED'))`.

**Proposed addition, four new values, none built:**
```sql
-- proposed, NOT applied:
check (event_type in (
  'ACTIVATED', 'WITHDRAWN', 'SOFT_DELETED',           -- unchanged, live since v4.21
  'STRENGTHENED', 'WEAKENED', 'NO_LONGER_QUALIFIES', 'REPLACED'   -- proposed
))
```
- **`STRENGTHENED`** — new evidence increased confidence in the original call; the product remains `active`; no status change.
- **`WEAKENED`** — new evidence reduced confidence in the original call, but the product has not (yet) failed Strategy's qualification bar; remains `active`. The HQ example's 11:30 AM moment (WR1 ruled out, before a formal withdrawal decision is made) is a `WEAKENED` event, not yet a `WITHDRAWN` one.
- **`NO_LONGER_QUALIFIES`** — a re-check against Volume 4 §9's own frozen qualification rule (`final_aggregate_confidence >= 0.55` AND `ev_per_dollar > 0`) found the candidate would not qualify under current information. This event explains WHY a `WITHDRAWN` event is about to fire (or, per HQ's own example, already has) — it is the reason, not a replacement for the existing `WITHDRAWN` event, which still fires separately and still flips `recommendation_products.status`.
- **`REPLACED`** — this product has been superseded by a NEW, separately-activated `recommendation_products` row for the same market (e.g. Team A -3 → Team B +3, or → `no_bet`). Fires on the OLD product, alongside its own `WITHDRAWN` event, and carries the new proposed `related_recommendation_product_id` column (below) pointing at the NEW product. **A `REPLACED` event never represents a same-row state change — it always means a second, independent activation occurred.** This preserves `recommendation_products`' existing "one row = one immutable decision, ever" invariant untouched; MANSA's "later updated decision" is always a new row, never a mutation of the old one.

### Proposed new columns on `recommendation_product_lifecycle_events`

```sql
-- proposed, NOT applied:
alter table recommendation_product_lifecycle_events
  add column trigger_type text check (trigger_type in
    ('line_movement','injury_update','weather_change','lineup_change','breaking_news',
     'contextual_intelligence_change','model_refresh')),
  add column trigger_event_data jsonb,
  add column related_recommendation_product_id uuid references recommendation_products(id);
```
- **`trigger_type`** reuses `market_monitoring_events.event_type` (§7 below) **verbatim** for its first five values — per HQ's own explicit "do not invent terminology if current schema already implies better names" instruction, this is the closest existing controlled vocabulary and it already anticipates exactly this use. Two values are new, because HQ's directive names two trigger categories `market_monitoring_events` was never designed to cover: `contextual_intelligence_change` (Volume 4 §8.6, Phase 8, not yet built) and `model_refresh` (a routine Strategy/consensus recompute — e.g. an Elite second-pass reconciliation, §4.3 — surfacing a materially different result on the same evidence). Nullable — an `ACTIVATED` event has no trigger; only `STRENGTHENED`/`WEAKENED`/`NO_LONGER_QUALIFIES`/`WITHDRAWN`/`REPLACED` are expected to populate it.
- **`trigger_event_data`** is the qualitative, factual "what changed" payload (e.g. `{"player": "WR1 name", "status": "OUT", "previously": "QUESTIONABLE"}` or `{"line_from": -3, "line_to": -5.5, "sportsbook": "..."}`) — same discipline as `market_monitoring_events.event_data` and `recommendation_leg_explanations`'s existing frozen-fact-not-invented-number principle. **This column must never carry a new `ev_per_dollar`/`final_aggregate_confidence` number** — no re-evaluation numeric engine exists yet (Volume 4 §9.5's automatic re-evaluation loop is explicitly future/unscheduled), and inventing one here would be exactly the kind of fabricated intelligence this Blueprint has repeatedly refused elsewhere (`would_change_mind_if`, `narrative_summary`, CLV). If a genuine re-evaluation numeric engine is ever built, it produces a NEW `recommendation_product`/`recommendation_legs` row (an `ACTIVATED` + `REPLACED` pair), never a retrofit number on the old one.
- **`related_recommendation_product_id`** is nullable, populated only for `REPLACED` (pointing forward to the new product) and optionally back-referenced from the new product's own `ACTIVATED` event (pointing backward to the old one) — a normalized FK, not the array/JSON linkage pattern already rejected elsewhere in this schema (Decision AO).

**Still append-only, no other change.** `recommendation_products.status`/`.withdrawn_at`/`.withdrawal_reason` remain the only mutable columns anywhere in the product/leg layer; every event above is a new INSERT into an already-append-only table, never an UPDATE.

### Grading/Track Record policy — made explicit, not newly invented

**Direct code inspection during this pass (`apps/ai-orchestrator/app/persistence/postgame_grading.py`, `apps/ai-orchestrator/app/orchestration/postgame_grading.py`) confirms: no query in the grading pipeline filters by `recommendation_products.status` today.** `read_recommendation_legs_by_game`/`read_recommendation_legs_by_product`/`read_no_bet_products_by_game`/`grade_game`/`_maybe_rollup_product` all read by `game_id`/`recommendation_product_id`/`recommendation_type` only. **A withdrawn product's legs are graded exactly like an active product's, on their frozen activation-time terms.** This is currently true by omission, not by a documented, tested policy — **proposed as an explicit, ratified policy**, not a code change:

> **Policy (proposed): grading is status-blind by design.** `recommendation_products.status` governs only whether a recommendation is currently presented as actionable — it has no bearing on whether its legs get graded. A `WITHDRAWN` (or `REPLACED`) product's legs are graded on the exact frozen `recommendation_legs` row from `recommendation_activation_snapshots` — never a later re-evaluation, never omitted from Track Record. This is the specific mechanism that prevents MANSA from improving its record by withdrawing recommendations after activation: withdrawal changes what a user is told to do next; it never changes what MANSA is scored on for what it already said at 10:00 AM.

Consequences of this policy, made explicit:
- **Does an activated recommendation remain gradeable even if later withdrawn? Yes, always** — enforced today only by the read-layer's own omission of a status filter; **a regression test asserting this (grade a `WITHDRAWN` product's legs, confirm a real grade event is written) does not exist yet and is a missing piece**, not a passing test being newly reported here.
- **Which snapshot/price does grading use?** Always `recommendation_legs`' own frozen `american_odds`/`point`/`ev_per_dollar`/`final_aggregate_confidence` — identical to today, unaffected by any `STRENGTHENED`/`WEAKENED`/`NO_LONGER_QUALIFIES`/`REPLACED` event, which are informational-only per the `trigger_event_data` restriction above.
- **How is MANSA's original decision distinguished from its later updated one?** The ORIGINAL decision is `recommendation_activation_snapshots` + `recommendation_legs` for the ORIGINAL product — untouched. The LATER decision, if one exists, is always a SEPARATE `recommendation_products` row (never a mutation), linked back via `REPLACED`/`related_recommendation_product_id`. Track Record (Volume 5 §5) counts BOTH products independently in its `sampleSize`/`record` denominators when both are graded — a reversal is two graded observations, never collapsed into one.
- **The existing 72-hour finality gate (`RECONCILIATION_WINDOW_HOURS = 72`, Volume 4 §9.6) is unchanged and orthogonal** — lifecycle/withdrawal events never affect grading-eligibility timing, which remains purely a function of `games.finalized_at`.

### Placed-status tracking — proposed new table, not an extension of `user_recommendation_selections`

**Confirmed gap:** `user_recommendation_selections` (§5A above) has no boolean or timestamp representing "the user told MANSA they placed this wager." Extending that table directly would conflict with its existing materiality-suppression trigger (`enforce_urs_materiality` compares only against the user's own latest row for the same key — a `placed` flag toggling would need its own, different suppression semantics). Proposed instead, additive and separate:

```sql
-- proposed, NOT applied:
create table user_recommendation_placements (
  id uuid primary key default uuid_generate_v7(),
  recommendation_product_id uuid not null references recommendation_products(id) on delete cascade,
  recommendation_leg_id uuid references recommendation_legs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  placed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (recommendation_product_id, recommendation_leg_id, user_id)
);
```
One row per user/product(/leg) — the user's own assertion that they placed the wager, nothing more. **MANSA cannot infer this from anything else it observes** (no sportsbook integration exists or is planned to confirm placement) — this table only ever reflects a user's own self-report. Once a row exists here, downstream lifecycle-change communication (dashboard/Time Machine/future Telegram, `docs/ops/recommendation-lifecycle-spec-2026-09-04.md` §4) must shift from actionable framing ("we no longer recommend this") to informational-only framing, and must never imply MANSA can cancel, hedge, or cash out a sportsbook wager on the user's behalf — MANSA has no such capability and none is proposed here.

### What this section does NOT do

- Does not alter `recommendation_products`/`recommendation_legs`' existing immutability rules — no new mutable column on either.
- Does not build a re-evaluation numeric engine — no new `ev_per_dollar`/confidence is ever computed by anything in this section.
- Does not wire `market_monitoring_events`/`worker-market-monitor` (still zero rows, zero code, per Phase 7 Milestone 7.0's own audit) or Volume 4 §9.5's execution states.
- Does not create any migration — every table/column above is a proposal pending HQ authorization as a future milestone (see roadmap update, same date).

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
**LEGACY, UNBUILT, LEFT UNTOUCHED (Phase 5 Milestone 5.4, Decision BG, 2026-08-27) — confirmed unfit for the Phase 5 product layer:** this table FKs to the legacy Phase 4 `recommendations` cycle row, has no product/leg awareness, no append-only trigger, and no deterministic outcome column at all. Zero rows, zero writers, exactly the same "schema exists, nothing writes it" state `explainability_payloads` and `recommendation_snapshots` were found in before their own milestones. **The actual Postgame Review grading/narrative layer is §5D's three new, additive tables** (`recommendation_leg_grade_events`/`recommendation_product_grade_events`/`recommendation_product_postgame_reviews`) — not this table, not repointed, not retrofitted. `outcome_summary` narrates recommendation performance, not wager settlement — it must not be treated as, or conflated with, a graded bet outcome. See §6's Stat Correction ↔ Bet Settlement Policy (v4.3) for the full separation requirement; that policy remains Phase 5 `verified_bets` scope, unaffected by §5D.

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

**Future data sink, not yet wired to anything (v4.19, 2026-08-25).** This table's `event_type`/`action_taken` vocabularies already anticipate the two future capabilities specified in Volume 4 §8.5 (Market Integrity & Anomaly Intelligence) and §9.5 (Bet Timing & Execution Intelligence) — confirmed by direct inspection that this table has zero rows and zero code references anywhere in this repository today. Documented here only so the existing column shape isn't accidentally redesigned before that future work reads/writes it; no schema change made by this entry.

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

### `prompt_registry` (v2.0; production wiring + active-version integrity v4.16)
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
create unique index idx_prompt_registry_one_active_per_name on prompt_registry(prompt_name) where status = 'active';
```
Every agent (Volume 4 §2) loads its prompt from this table by `(prompt_name, status='active')` rather than embedding prompt text in code — as of Milestone 4.8, this is genuinely true in production, not aspirational: each of the 12 built agents' full canonical system prompt is a row here (`prompt_name = agent_name`), resolved once per execution at the orchestration/harness boundary (never inside an agent class, never via the agent's own I/O) and passed in already-built. A missing active row for a required agent fails that agent's run clearly (`PromptConfigError`) — production never silently substitutes hardcoded text.

**`idx_prompt_registry_one_active_per_name` (v4.16, Milestone 4.8):** enforces at the database level that at most one row may be `status='active'` per `prompt_name` at a time — deterministic active-version resolution was explicitly required to not depend on an application-side "highest version wins" convention alone, since that would silently tolerate an invalid multi-active-row state rather than refusing to create one.

This registry is no longer the mechanism that makes `recommendations.prompt_version` (§5 above) meaningful — see that column's own v4.16 note for why a single scalar can't represent per-agent versions once this table moved from a single-recommendation-prompt concept to a per-agent one. `recommendation_agent_outputs.prompt_name`/`.prompt_version` (above) are the mechanism now.

### `model_registry` (v2.0; `provider` added v4.13)
```sql
create table model_registry (
  id uuid primary key default gen_random_uuid(),
  model_name text not null unique,
  provider text not null,                   -- v4.13: explicit vendor identity, e.g. 'openai'/'anthropic'
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
**`provider` (v4.13, Milestone 4.4 pre-check, 2026-08-21):** deliberately `text not null` with no `check` constraint enumerating today's vendors — unlike `game_provider_ids`/`team_provider_ids`/`player_provider_ids.provider_name`'s existing rigid-CHECK pattern (each requiring its own follow-up migration for a new vendor), a future model provider is a plain data `insert`, never a schema migration. Validity is enforced at the application layer instead: `app.models.router`'s `AdapterRegistry` already raises `UnknownProviderError` for any provider it has no adapter registered for (Milestone 4.3) — the same check a DB `CHECK` constraint would otherwise duplicate. `model_routing_rules` deliberately does NOT get its own `provider`/`primary_provider`/`fallback_provider` column — `primary_model`/`fallback_model` remain plain model-name references (already documented as conceptual, not FK, since "routing rules should still function if a model is mid-migration"); provider is resolved by joining through `model_registry.model_name`, avoiding storing the same fact in two places.
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

`verified_bets`, `bet_slips`, `projected_user_performance`, `verified_user_performance`, `betting_dna`, `subscriptions`, `user_recommendation_selections`, and `conversations`/`conversation_messages` (Volume 4/5 own the NL Engine's message schema) all follow the same `auth.uid() = user_id` pattern as the baseline policy, with service-role bypass reserved for the background workers described in Volume 2.

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
