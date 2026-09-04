# The Playbook — Engineering Roadmap & Build Order

**Version:** v4.10
**Last updated:** 2026-09-04
**Type:** Companion document — not a Volume. Volumes 1–5 describe *what* the system is. This document describes *the order in which to build it* and *how to know each piece is actually done* before moving to the next.
**v4.10 note (HQ authorization, 2026-09-04, real code):** Phase 7 Milestone 7.1 (Deterministic Unexplained-Movement Detection Engine) authorized and built the same day, following a diagnostic pass on DEV's crashed `cron-master-refresh` service (root cause: a deliberate, correctly-functioning safety guard — `CRON_DISPATCH_TARGET` set to an intentionally-invalid placeholder value so the daily cron can never actually invoke Master Refresh's real, spendable SportsDataIO call; left untouched, not "fixed," per HQ's own explicit guardrail). Milestone 7.1 itself: full detail in the updated Milestone 7.1 entry below. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v4.9 note (HQ Decision Lock, 2026-09-04, planning only):** Milestone 5.6 (Recommendation Lifecycle & Change Communication, proposed at v4.8 earlier the same day) is now DESIGN LOCKED — HQ approved all seven proposed items (vocabulary, `REPLACED` semantics, mandatory status-blind grading policy, `user_recommendation_placements`, explicit non-extension of `market_monitoring_events`, the milestone itself as mandatory pre-Beta, and the dashboard "never silently disappear" principle) — full detail in the updated Volume 4 §9.7/Volume 3 §5G and `docs/ops/recommendation-lifecycle-spec-2026-09-04.md`. New: an explicit phased-authorization split — basic mechanics may be implemented ahead of Phase 7/Phase 8, but the milestone cannot be considered CLOSED (and therefore cannot satisfy Phase 12/Beta's dependency) until real Phase 7/Phase 8 signals actually feed its trigger vocabulary. Still no code, migration, UI, Telegram, grading, or worker change — approving a design is not authorizing its build. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v4.8 note (HQ directive, 2026-09-04, planning only):** New Phase 5 **Milestone 5.6 — Recommendation Lifecycle & Change Communication** proposed (not authorized) — fully specified in the new Volume 4 §9.7 / Volume 3 §5G, per HQ's directive to formally define what happens when MANSA changes its view after a recommendation has already been activated. Added as an explicit mandatory Phase 12 (Beta) prerequisite, alongside the existing Phase 8 requirement, since real recommendations changing between morning analysis and kickoff is a certainty during any live beta cohort. No code, migration, or existing milestone changed by this entry. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v4.7 note (HQ decision, 2026-09-04):** New **Phase 8 — Contextual Performance Intelligence** inserted between Phase 7 (Market Integrity & Anomaly Intelligence, unchanged) and the previously-numbered Phase 8 (Twilio) — fully specified in the new Volume 4 §8.6. Twilio (formerly Phase 8), OCR (formerly 9), Analytics (formerly 10), Beta (formerly 11), and Production Launch (formerly 12) are renumbered to Phases 9-13 respectively — no scope removed, only positions shifted, same discipline as the v4.6 renumbering below. **Phase 8 is a mandatory Beta prerequisite** (see the updated Phase 12/Beta dependency list) — MANSA must be able to learn how comparable context changes expected performance, and propagate that across player props/moneyline/spread/totals/parlays, before real-user validation begins. Phase 8 itself is authorized only through a Milestone 8.0-style contract audit (this entry) — Milestones 8.1+ (the actual contextual-impact engine) remain proposed, not authorized. This same directive also recorded an immediate, time-sensitive **2026 Data Preservation Requirement** (`docs/ops/2026-data-preservation-requirement.md`) — several context factors Phase 8 will eventually need (in-game condition changes, play-by-play/game state, News history) have zero capture in the current architecture, and that gap becomes permanent and unrecoverable, game by game, once the 2026 regular season begins — and a News-cadence redesign audit (`docs/ops/news-cadence-architecture-audit-2026-09-04.md`), neither of which changes any code, migration, or subscription by itself. Two pre-existing stale cross-references from the v4.6 renumbering (Production Launch's "internal dashboard from Phase 9" and the Technical Debt backlog's "before Phase 10" for the beta access model) are also corrected in this pass — both should have been updated during v4.6 and were not. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v4.6 note (HQ decision, 2026-09-02):** Phase 6 formally closed (HQ's final visual-gate approval). HQ authorized Phase 7 planning and, on reviewing the resulting archaeology, made an explicit renumbering decision: **Market Integrity & Anomaly Intelligence (Volume 4 §8.5) is now the official Phase 7** — promoted out of the "Future Phase 5 capabilities" note (v4.1) and the Technical Debt & Feature Backlog's "Future" category, where it had been tentatively parked as an unscheduled Phase 5 milestone before Phase 5 closed. The previously-numbered Phase 7 (Twilio), Phase 8 (OCR), Phase 9 (Analytics), Phase 10 (Beta), and Phase 11 (Production Launch) are **renumbered to Phase 8/9/10/11/12 respectively — none of their scope is removed or reduced**, only their position in the sequence shifts. Bet Timing & Execution Intelligence (Volume 4 §9.5) remains an unscheduled future capability, not promoted to a numbered phase — HQ's explicit instruction preserves only the historical ordering constraint that it must follow Market Integrity & Anomaly Intelligence whenever it is eventually scheduled. Phase 7 itself is authorized only through Milestone 7.0 (Contract Audit & Mechanism Decision) as of this version — Milestones 7.1+ (the actual anomaly-detection engine) remain proposed, not authorized. See `CHANGELOG.md` v4.6 entry for full reasoning.
**v4.5 note:** Phase 6's section fully rewritten — written before Phase 4/5 existed, it cited the original Volume 5 v4.0 component/route spec, assumed `/chat` as the default landing route, and (as of a 2026-08-27 addition) assigned the `user_recommendation_selections` production writer to this phase. A three-pass Phase 6 Product/UX planning review (HQ-approved) replaced the IA/component/onboarding architecture (now matching Volume 5 v5.0) and explicitly removed the stake writer from this phase's scope as new business logic. See `CHANGELOG.md` v4.5 entry for full reasoning.
**v2.0 note:** Amended per external architecture review, which arrived before any phase began building — no phase needed to be reopened, but Phases 1, 4, 5, and 6 gained new scope. See `v2.0-amendments-architecture-review.md` §7 for the full impact summary.
**v3.0 note:** Amended per conversational-first UX and intelligence pipeline additions — Phases 1, 3, 4, 5, and 6 gained new scope (`daily_game_intelligence`, Redis, named vendors, worker cadences, Kelly Criterion, session memory, chat-first landing route). See `v3.0-amendments-conversational-intelligence.md` §12 for the full impact summary.
**v4.0 note:** Amended per the internal markdown-consistency review — Phases 1, 3, and 4 gained new scope (normalized multi-sport core, Recommendation Worker), and a Technical Debt & Feature Backlog section added. See `CHANGELOG.md` v4.0 entry for full detail.
**Depends on:** All five volumes. Every phase below cites the specific volume/section it implements.
**Rule for using this document:** No phase starts before the prior phase's acceptance criteria are met. This isn't bureaucracy for its own sake — Phase 5 (Recommendation Pipeline) will silently produce wrong or unreproducible output if Phase 1 (Database Foundation) has a schema gap, and that kind of bug is far more expensive to find in Phase 9 than in Phase 1.

---

## How to Read This Document

Each phase has five parts:
- **Milestones** — the 2–4 major checkpoints inside the phase
- **Key Tasks** — concrete build items
- **Dependencies** — what must already be true before this phase can start
- **Acceptance Criteria** — the specific, checkable conditions that mean this phase is actually done, not just "mostly working"
- **Testing Requirements** — what must be tested, and how, before moving on

---

## Phase Dependency Overview

```
Phase 0 (Repo/CI/CD)
   │
Phase 1 (Database Foundation)
   │
Phase 2 (Authentication)
   │
Phase 3 (Sports Intelligence Layer) ──┐
   │                                    │
Phase 4 (AI Orchestrator) ─────────────┤
   │                                    │
Phase 5 (Recommendation Pipeline) ◄────┘
   │
Phase 6 (Dashboard / Core Frontend)
   │
   ├── Phase 7 (Market Integrity & Anomaly Intelligence) ─┐
   ├── Phase 9 (Twilio) ─────────────────────────────────────┤
   ├── Phase 10 (OCR) ──────────────────────────────────────┤  (7, 9, 10, 11 can run in parallel once Phase 6 is stable — none of the four depends on any other)
   └── Phase 11 (Analytics) ────────────────────────────────┘
   │
Phase 8 (Contextual Performance Intelligence) — NOT part of the parallel group above; see note below
   │
Phase 12 (Beta)
   │
Phase 13 (Production Launch)
```

Phases 7, 9, 10, and 11 are the first genuine parallelization point — everything before Phase 6 is strictly sequential because each layer is load-bearing for the next. Phase 7's own dependencies (Phase 3's `odds_snapshots`, Phase 4 Milestone 4.4's Closing Line Movement Agent, Phase 5 Milestone 5.1's Strategy Engine) are all already satisfied independent of Phase 6 — it is numbered first among the four not because it architecturally blocks the others, but because it is the capability HQ has actively authorized planning for (2026-09-02, v4.6). Bet Timing & Execution Intelligence (Volume 4 §9.5) is not a numbered phase — it remains an unscheduled future capability whose one preserved ordering constraint is that it must follow Phase 7 whenever it is eventually scheduled (see the Technical Debt & Feature Backlog entry below).

**Phase 8 (Contextual Performance Intelligence) is deliberately drawn separately above, not folded into the Phase 7/9/10/11 parallel group** — it is numbered directly after Phase 7 because HQ has authorized its planning now (2026-09-04, v4.7, mirroring Phase 7's own 2026-09-02 precedent), not because it is proven independent of the others the way Twilio/OCR/Analytics are proven independent of Market Integrity. Its real dependency shape is deliberately NOT resolved by this entry: Volume 4 §8.6 documents it as sitting upstream of the already-frozen Probability Modeling Agent (§2.5) and several already-built Context & Data/Matchup agents (§2.2/§2.3), which is a Phase 4 pipeline position, not a standalone Phase-6-onward capability the way Phase 7/9/10/11 are. Whether Milestone 8.1+ implementation actually requires reopening Phase 4 agent wiring is an explicit open question for Phase 8's own future contract-audit milestone, not decided here — **Phase 8 is placed after Phase 7 in sequence and is a mandatory Beta (Phase 12) prerequisite, but this diagram does not claim it can run in parallel with 7/9/10/11 the way those four can run in parallel with each other.**

---

## Phase 0 — Repository, Environments, CI/CD

**Implements:** Volume 2 §5 (Railway environments), §9 (CI/CD, secrets, observability)

**Milestones:**
1. Monorepo or multi-repo structure decided and initialized
2. Three Railway environments (`dev`, `staging`, `production`) provisioned
3. CI/CD pipeline running on every push, deploying to `dev` automatically

**Key Tasks:**
- Initialize repo(s): API Gateway, AI Orchestrator, Sports Intel Layer, Workers, Frontend (decide monorepo vs. separate repos before Phase 1 — this is expensive to change later)
- Set up GitHub Actions workflows matching Volume 2 §9's branch-to-environment mapping
- Provision Railway projects for all three environments with the four-service shape from Volume 2 §5
- Set up Sentry (or equivalent) error tracking, wired to all services from day one, even before there's meaningful traffic
- Establish secrets management convention (Railway env vars, never committed) and document the rotation schedule for API keys

**Dependencies:** None — this is the starting phase.

**Acceptance Criteria:**
- A trivial code change pushed to the `dev` branch deploys automatically and is visible in the `dev` environment within the CI/CD pipeline's expected time
- All three environments exist and are network-isolated from each other per Volume 2 §5
- Error tracking captures and reports a deliberately-triggered test error in each service

**Testing Requirements:**
- CI pipeline itself is tested: a failing test must block deployment (verify this by intentionally committing a failing test and confirming it doesn't reach `dev`)
- Rollback tested once, manually, to confirm the one-click rollback path (Volume 2 §9) actually works before it's ever needed under pressure

---

## Phase 1 — Database Foundation

**Implements:** Volume 3, full document

**Milestones:**
1. Core user/account tables live (§3)
2. Sports data tables live (§4)
3. AI intelligence tables live (§5)
4. Performance attribution + postgame + config tables live (§6–§8)
5. RLS policies and triggers applied to every table (§10–§11)

**Key Tasks:**
- Write migrations in the exact order Volume 3 presents tables (dependencies flow top to bottom in that document — `user_profiles` before `subscriptions`, `games` before `odds_snapshots`, etc.)
- Apply RLS to every table as it's created, not as a batch at the end — this avoids a window where tables exist unprotected
- Implement both triggers from Volume 3 §11, especially the append-only enforcement trigger on `recommendation_agent_outputs`
- Set up the Supabase CLI migration workflow described in Volume 3 §12 (dev → staging → production promotion)

**Dependencies:** Phase 0 complete (need environments to migrate into).

**v2.0 addition:** also build `feature_flags`, `prompt_registry`, `model_registry`, `recommendation_costs`, and the expanded `audit_log` (all specified in `v2.0-amendments-architecture-review.md` §1). Add AI versioning columns and soft-delete columns to their respective tables. Use UUIDv7 for `odds_snapshots`, `recommendation_agent_outputs`, and `market_monitoring_events` specifically.

**v3.0 addition:** also build `daily_game_intelligence` and the 13 derived score tables (Volume 3 §4.1–§4.2). Add `display_id` to `recommendations` and `session_preferences` to `conversations` (the latter is created in this phase even though it's populated starting in Phase 5, so the schema is ready). Note that `daily_game_intelligence` is a working table with no historical-integrity requirement — it doesn't need the append-only or soft-delete treatment the snapshot tables get.

**v4.0 addition:** build the normalized multi-sport core (Volume 3 §4.0) — `sports`, `leagues`, `seasons`, `teams`, `players`, `player_stats`, `team_stats`, and the `player_stats_nfl` extension table. Update `games` to add `sport_id`/`league_id`/`season_id` while keeping the legacy `sport` text column — both coexist through this phase. Add the data quality metadata convention (source/confidence/last_updated/status) to `daily_game_intelligence`'s jsonb categories.

**Acceptance Criteria:**
- Every table from Volume 3 (including the v2.0, v3.0, and v4.0 additions above) exists in `dev` with correct types, constraints, and foreign keys
- RLS policies verified by attempting a cross-user read (e.g., User A querying User B's `user_profiles` row) and confirming it returns zero rows, not an error and not the data
- The append-only trigger on `recommendation_agent_outputs` verified by attempting an `UPDATE` and confirming it raises the expected exception
- A full migration replay from empty database to current state completes without manual intervention
- Every seeded NFL game correctly populates both the legacy `sport` field and the new `sport_id` reference — proof the backward-compatible dual-write actually works, not just that both columns exist

**Testing Requirements:**
- Automated RLS test suite: for every table with a policy, a test that confirms both the "owner can access" and "non-owner cannot access" cases
- Migration reversibility check on at least the additive migrations (Volume 3 §12's backward-compatible preference)
- Seed script producing realistic fake data for every table, needed for Phase 3–5 development without depending on live provider data yet

---

## Phase 2 — Authentication

**Implements:** Volume 2 §6 (JWT validation, internal service token), Volume 3 §3 (`user_profiles` linkage to `auth.users`)

**Milestones:**
1. Supabase Auth configured and issuing JWTs
2. API Gateway validating JWTs on every protected route
3. Internal service token implemented for service-to-service calls
4. Onboarding data collection wired to `user_profiles` (jurisdiction gating live)

**Key Tasks:**
- Configure Supabase Auth (email/password at minimum; evaluate OAuth providers as a nice-to-have, not a blocker)
- Implement JWT validation middleware in the API Gateway
- Generate and securely store the internal service token; update Orchestrator/Workers to use it exclusively for internal calls, never a user JWT
- Build the jurisdiction-state collection step and enforce the `not null` constraint's intent at the application layer too (clear error messaging, not just a database rejection)

**Dependencies:** Phase 1 complete (tables must exist to link auth users to profiles).

**Acceptance Criteria:**
- A user can sign up, and a corresponding `user_profiles` row is created automatically (via trigger or application code — decide and document which)
- An expired or tampered JWT is rejected by the Gateway with a proper 401, not a 500
- A request using a user JWT against an internal-only endpoint is rejected; a request using the internal service token succeeds
- Attempting to complete onboarding without a jurisdiction value is blocked with a clear message, not a silent failure

**Testing Requirements:**
- Auth flow tested end-to-end: signup → profile creation → login → authenticated request
- Negative tests: expired token, malformed token, token for a deleted user
- Internal token isolation explicitly tested (this is a security-critical boundary from Volume 2 §10, worth its own dedicated test)

---

## Phase 3 — Sports Intelligence Layer

**Implements:** Volume 2 §8

**Milestones:**
1. First provider adapter (odds) built against the shared internal interface
2. Additional adapters (injuries, weather, rosters, schedules) built
3. Caching layer live with category-appropriate TTLs
4. Normalized data flowing into `games` / `odds_snapshots` and supporting tables

**Key Tasks:**
- Define the shared internal adapter interface first, before writing any specific provider's adapter — this is the enforcement point for the "no other service imports a provider SDK directly" rule
- Build odds adapter first (highest-priority data category), verify normalization into `odds_snapshots`
- Build remaining adapters (injuries, weather, rosters, schedules), each against a documented fallback provider per Volume 2 §8
- Implement caching per category with the TTLs specified in Volume 2 §8

**v3.0 addition:** implement Redis as the concrete cache layer (Volume 2 §8) rather than an unspecified cache. Build against the named vendor candidates — The Odds API (odds), SportsDataIO (stats/injuries/rosters/schedules), WeatherAPI with OpenWeatherMap fallback (weather), NewsAPI or GNews (news). Build the Master Refresh worker (daily 6:00 AM) that populates `daily_game_intelligence`, plus the Odds/Player Props (5 min), Injury (10 min), Weather/News (15 min), and Pregame (triggered) workers per Volume 2 §8's cadence table.

**v4.0 note (no new build in this phase, sequencing only):** the Recommendation Worker (Volume 2 §4.4) that consumes Master Refresh's output belongs to Phase 4/5 (it needs the agent committee to exist first) — this phase only needs to guarantee Master Refresh completes reliably and on schedule, since Phase 4/5's proactive worker depends on it.

**Dependencies:** Phase 1 complete (target tables must exist).

**Acceptance Criteria:**
- Real (or sandboxed) provider data flows end-to-end into `games` and `odds_snapshots` with correct normalization
- Switching a provider adapter's underlying implementation (tested with a mock swap) requires no changes outside the Sports Intelligence Layer itself — this is the actual test of whether the adapter pattern was implemented correctly, not just described correctly
- Cache hit rate is measurable and matches expected TTL behavior per category
- `daily_game_intelligence` is populated correctly by the Master Refresh worker and stays current per the cadence table — verified by checking `last_updated` against each source worker's actual run time

**Testing Requirements:**
- Adapter interface conformance tests — every adapter implements the full shared interface, verified automatically, not by code review alone
- Simulated provider outage test: confirm the system degrades gracefully (uses cached data, doesn't crash downstream services) when a provider call fails
- Load test against expected Sunday-slate polling volume before this phase is considered done, not deferred to Phase 11 (Analytics — corrected v4.7, 2026-09-04; same class of stale post-v4.6 reference as the two corrected in the Beta/Production Launch sections above)
- Verify `daily_game_intelligence` is correctly treated as a working table, not a Time Machine source — confirm a `recommendation_snapshots` reconstruction (tested fully in Phase 5) never reads from it

**Demo Mode note (added 2026-08-19):** this phase's real, shipped ingestion pipeline is the first thing the approved Demo/Simulation Environment (`demo-simulation-environment.md`) can build scenarios against — see that document's DEMO-4 step. Demo work is gated behind its own separately-approved execution plans and does not affect this phase's own acceptance criteria.

---

## Phase 4 — AI Orchestrator

**Implements:** Volume 4 §1–§6 (agent committee through adaptive weighting), Volume 2 §7

**Milestones:**
1. Shared agent output contract implemented (Volume 4 §2.1), including the v2.0 `evidence_classification` field
2. All 21 fan-out agents plus the Meta Agent (22nd, post-consensus) built and returning structured output against real/sandboxed data
3. Async fan-out execution working per the flow in Volume 4 §3.1
4. Consensus Engine computing aggregate confidence and agreement variance, with the Meta Agent's confidence_adjustment applied afterward
5. Model routing table live and driving actual model selection, informed by `model_registry` cost/latency data
6. Agents load prompts from `prompt_registry` rather than hardcoded text

**Key Tasks:**
- Build the shared agent output contract and a test harness that validates any agent's output against it before wiring it into the real pipeline
- Build agents in the four functional groups from Volume 4 §2, starting with Context & Data Agents since Matchup and Decision agents depend on their output
- Implement the async fan-out orchestration flow, respecting the sequential dependency in steps 4–6 of Volume 4 §3.1 (Probability Modeling → EV → Risk/Bankroll)
- Implement the Consensus Engine formula from Volume 4 §4.1, and the Elite second-pass trigger from §4.3
- Populate `model_routing_rules` with the launch defaults from Volume 4 §3.2

**v3.0 addition:** implement fractional (quarter-Kelly) Kelly Criterion in the Bankroll Coach agent's stake formula (Volume 4 §2.5) rather than an unspecified stake translation. Wire agents to query `daily_game_intelligence` (Volume 3 §4.1) first per the updated step 1 of Volume 4 §3.1, falling back to individual supporting tables only when a field isn't yet reflected there. Confirm the Recommendation Strategy Engine's parlay logic (built fully in Phase 5, but the underlying agent outputs feeding it are built here) supports mixed-market legs per Volume 4 §9's v3.0 addition — no market-type restriction baked into any single agent's output shape.

**v4.0 addition:** build the Recommendation Worker (Volume 2 §4.4, Volume 4 §3.1) — triggers the full agent committee proactively shortly after Master Refresh completes, for each active user (or user-persona cluster as a later optimization), storing results the same way an on-demand request would. Confirm this doesn't bypass personalization: the worker must read each user's `user_profiles`/`betting_dna` at run time, not produce one generic recommendation shared across users.

**Dependencies:** Phase 3 complete (agents need real normalized sports data to reason over) and Phase 1 (agent output tables must exist).

**Acceptance Criteria:**
- All 21 fan-out agents plus the Meta Agent produce output conforming to the shared contract against a real game snapshot
- Meta Agent's `confidence_adjustment` is verified to only ever reduce aggregate confidence, never increase it, tested with a deliberate attempt to produce a positive adjustment
- A full orchestration run completes and produces a correct `consensus_snapshots` row with plausible aggregate confidence
- Disabling/zero-weighting a single agent measurably changes the aggregate confidence calculation in the expected direction — proof the weighting math is actually wired in, not decorative
- The 0.55 "No Bet Today" floor from Volume 4 §4.2 correctly suppresses a recommendation in a deliberately low-confidence test scenario
- Bankroll Coach's Kelly-based stake output changes correctly when `risk_tolerance` changes on an otherwise identical test profile — proof the formula is actually parameterized per user, not a fixed fraction

**Testing Requirements:**
- Unit tests per agent against known input/output pairs (this is where the pre-launch backtesting data from Volume 4 §11 starts getting collected, even informally)
- Consensus Engine math validated against hand-calculated expected values for at least a handful of constructed scenarios
- Latency test on the full 21-agent fan-out — this is the flow the natural-language chat interface (Phase 6+) depends on feeling responsive, so a latency regression here should block the phase from closing

---

## Phase 5 — Recommendation Pipeline

**Implements:** Volume 4 §7–§10 (NL Engine, Explainability Engine, Recommendation Strategy Engine, Continuous Learning loop), Volume 3 §5–§7

**Milestones:**
1. Recommendation Strategy Engine deciding output shape per Volume 4 §9's priority order
2. Explainability Engine populating all nine question fields
3. Time Machine snapshot writing correctly to `recommendation_snapshots`
4. Postgame Review worker generating reviews on game completion
5. Continuous Learning loop updating agent weights under guardrails

**Key Tasks:**
- Implement the Recommendation Strategy Engine's decision logic exactly per the priority order in Volume 4 §9 — this order matters and should be tested in that order, not just as independent cases
- Wire the Explainability Engine's field-by-field sourcing from Volume 4 §8's table
- Implement `recommendation_snapshots` writing as part of the same transaction/flow that creates a recommendation — this must never be a separate, best-effort step that can silently fail
- Build the scheduled worker that triggers on `games.status = 'final'` and generates `postgame_reviews`
- Implement the adaptive weighting algorithm from Volume 4 §6, with all three guardrails (sample size, max change, evaluation window) enforced in code, not just documented as intent
- **v2.0 addition:** wire `RecommendationCreated`, `RecommendationUpdated`, and `RecommendationWithdrawn` events (Postgres LISTEN/NOTIFY, per `v2.0-amendments-architecture-review.md` §2) as part of the same transaction that writes `recommendation_snapshots` — not a best-effort afterthought
- **v3.0 addition:** generate `display_id` (Volume 3 §5) as part of the same creation transaction. Wire the NL Engine's session-preference checking (Volume 4 §7) — a stated exclusion in `conversations.session_preferences` must actually filter what the Recommendation Strategy Engine considers, not just get stored and ignored.

**Dependencies:** Phase 4 complete (needs the full agent committee and consensus output to build a recommendation from) and Phase 2 (needs user profiles for Bankroll Coach personalization).

**Acceptance Criteria:**
- A recommendation created today can be fully reconstructed via `/v1/recommendations/{id}/snapshot` and matches what was actually shown to the user at creation time — this is the single most important acceptance test in the entire roadmap, since it's the Time Machine guarantee the whole product's trust claim depends on
- Attempting to force a weight update below the minimum sample size is rejected by the guardrail, verified with a deliberate test case
- A completed game correctly triggers a postgame review within the expected worker cycle time, with correct/underperforming agents populated

**Testing Requirements:**
- End-to-end reproducibility test: create a recommendation, wait, mutate the live `agents.current_weight` value directly, then confirm the snapshot reconstruction still shows the *original* weight, not the current one
- Guardrail tests for all three weighting constraints, each with a case designed to violate it and confirm rejection
- Full pipeline integration test: game snapshot in → recommendation out → postgame review generated → weight update attempted, all as one traced flow using the correlation ID from Volume 2 §9

**Milestone 5.3 correction (v4.2, 2026-08-25):** Milestone 3 above ("Time Machine snapshot writing correctly to `recommendation_snapshots`") and this section's own acceptance criterion (reconstruction via `/v1/recommendations/{id}/snapshot`) both predate Phase 5's actual product-layer architecture (Milestones 5.1/5.2) and name a table confirmed, by direct live-schema inspection, to be unfit for it — `recommendation_snapshots` is one row per Phase 4 `recommendations.id`, structurally unable to represent a slate-scoped `multiple_singles`/`bankroll_preservation` product, a `no_bet` product with zero legs, or per-leg Explainability provenance; it remains legacy/untouched, same treatment as `explainability_payloads`. Milestone 5.3 (Time Machine) instead built an additive activation-snapshot manifest (Volume 3 §5C) composing already-frozen Milestone 5.1/5.2 rows by FK, and an internal-only reconstruction function (`app.orchestration.reconstruction`, not a public route — Decision BC defers the actual `/v1/...` public API surface to Phase 6, which owns the product-layer-identity API design this roadmap's original one-line endpoint mention never specified). The roadmap's own named reproducibility test (mutate `agents.current_weight` live, confirm reconstruction shows the original) is built and passing against the new manifest, satisfying this milestone's actual intent even though the literal table/endpoint names above are superseded.

**Milestone 5.4 correction (v4.3, 2026-08-27).** This section's own Key Task ("Build the scheduled worker that triggers on `games.status = 'final'` and generates `postgame_reviews`") is necessary-but-insufficient as written: `games.status = 'final'` is required, but the Postgame Ingestion Worker's own bounded reconciliation window (Volume 2 §8) can still correct final stats for up to 72 hours afterward — the actual grading-readiness condition Milestone 5.4 implemented is reconciliation-completeness (`games.finalized_at + 72h`), reusing the ingestion worker's own approved checkpoint schedule rather than the raw status transition alone (Volume 4 §9.6, Volume 3 §5D). `postgame_reviews` itself, like `recommendation_snapshots` before it, is confirmed unfit for the Phase 5 product layer (no product/leg awareness, no append-only trigger, no deterministic outcome column) and remains legacy/untouched — the real grading/review layer is three new additive tables (Volume 3 §5D). This milestone's own acceptance criterion ("A completed game correctly triggers a postgame review... with correct/underperforming agents populated") is satisfied by the new layer, not the legacy table the criterion names. Adaptive weighting (this section's other Key Task, and the "aggregated into `agent_performance_scores`" step of §10's loop) remains explicitly unimplemented — Milestone 5.4 produces the graded evidence that loop will eventually consume, per Decision BW; it does not close the loop itself, and is deferred to a dedicated Milestone 5.5 inspection, which must also resolve what unit ("recommendation") the roadmap's own 200-sample guardrail (Volume 4 §6.1) counts under the modern product/leg architecture.

**Milestone 5.5 correction (v4.4, 2026-08-27).** Milestone 5.4's own correction note above deferred adaptive weighting to "a dedicated Milestone 5.5 inspection, which must also resolve what unit ('recommendation') the roadmap's own 200-sample guardrail (Volume 4 §6.1) counts under the modern product/leg architecture." That inspection is complete and the milestone is built: the 200-sample guardrail counts **200 classifiable graded-leg observations per agent** — a leg whose authoritative deterministic grade produces a realized direction, graded by an agent that succeeded and made a classifiable directional call (game-level voting agents only; `multiple_singles` legs count independently) — not "200 recommendations" in any product-layer sense, since a single product can contain zero, one, or many such legs. Milestone 5.5 is a **propose-only V1**: it computes ROI/performance_delta/guardrails and persists the result append-only (Volume 3 §5E, `adaptive_weight_proposals`/`adaptive_weight_proposal_observations`), but no worker or process may autonomously mutate `agents.current_weight` — promotion is a separate, not-yet-authorized future capability. `learning_rate` (Volume 4 §6.1's formula, previously unresolved) is fixed at `0.25` as an approved initial product-policy default (`ADAPTIVE_WEIGHT_LEARNING_RATE`), not an empirically-derived value, independent of the pre-existing ±10% single-adjustment guardrail. The two `agent_performance_scores` rows dated 2026-08-07 predate this architecture entirely, carry no valid provenance, and are disregarded as evidence (not deleted). Because zero real graded recommendations exist yet in this environment, Milestone 5.5 is complete as **implementation validation** (proven against deterministic fixtures, full regression, and a live rollback-wrapped SQL proof); **empirical validation** (does the weighting actually improve committee performance against real outcomes) remains an open, explicitly-disclosed future item, not a defect of this milestone.

**`user_recommendation_selections` (Volume 3 §5A) writer — assigned to Phase 6, not Phase 5 (2026-08-27).** This table's schema shipped in Milestone 5.1 with zero writers, an ownerless gap surfaced during the Milestone 5.4 inspection. The durable selection/presentation event it represents can only become real once a real user views/selects a recommendation through an actual product surface — no such surface exists before Phase 6 (Dashboard/chat). **Phase 6 explicitly owns:** the production writer for user recommendation presentation/selection persistence, Bankroll Coach's personalized selection state capture at that moment, this table's own materiality/idempotency behavior, and a Time Machine reproducibility proof using a genuinely persisted user selection (mirroring the pattern already proven for `recommendation_activation_snapshots` in Milestone 5.3). Not a 5.4 prerequisite — no code for it was built in Milestone 5.4.

**Future Phase 5 capabilities — approved/documented, deliberately NOT assigned a milestone number above (v4.1, 2026-08-25).** Two capabilities were fully specified in Volume 4 §8.5 (Market Integrity & Anomaly Intelligence) and §9.5 (Bet Timing & Execution Intelligence) without being forced into Milestones 1-5 above, per Mac's explicit instruction not to arbitrarily assign a capability to a milestone the Blueprint doesn't clearly support. Dependency analysis, performed against the actual current codebase rather than assumed:

- **Market Integrity & Anomaly Intelligence** depends on: `odds_snapshots` history (Phase 3, built), the Closing Line Movement Agent (Phase 4 Milestone 4.4, built), and the Recommendation Strategy Engine existing as a real consumer of an anomaly signal (Milestone 5.1, built). It also depends on `worker-market-monitor` actually being implemented with real monitoring logic and `market_monitoring_events` actually being written to — **both confirmed still completely unbuilt** (zero application code, zero rows) by direct inspection. **Earliest technically defensible placement: a new Phase 5 milestone (tentatively Milestone 6), after Milestone 5.1 and logically before or alongside Milestone 5.5's Continuous Learning loop** — it needs Strategy Engine to exist (it does) but does not need Explainability, Time Machine, or Continuous Learning to exist first.
- **Bet Timing & Execution Intelligence** depends on everything above, PLUS Market Integrity & Anomaly Intelligence itself (per Volume 4 §9.5's explicit integration requirement — anomaly signals feed execution state), PLUS the automatic re-evaluation loop, which depends on event infrastructure Volume 2 §4.5 already named and explicitly deferred post-MLP (`InjuryUpdated`, `WeatherChanged`, and similar consumers). **Earliest technically defensible placement: a new Phase 5 milestone (tentatively Milestone 7), strictly after the Market Integrity milestone above** — and its full realization (a user actually seeing "WAIT, check back later") likely also touches Phase 7's Twilio/notification work, even though its core decision logic belongs in Phase 5.
- **Neither is scheduled into a specific sprint by this entry** — both remain future capabilities pending a dedicated future architecture inspection (explicitly not performed here, per Mac's instruction) that would determine the exact mechanism (deterministic engine vs. specialist agent(s) vs. hybrid) before implementation begins. This entry exists so neither is forgotten or designed out, not so either is scheduled.

**Superseded in part (v4.6, 2026-09-02, HQ decision).** Phase 5 closed 2026-08-27 before either capability above was scheduled into it, so "a new Phase 5 milestone" is no longer a live placement option. Following Phase 6's close (2026-09-02) and a dedicated Phase 7 planning/archaeology pass, HQ formally promoted **Market Integrity & Anomaly Intelligence to Phase 7** — see the new Phase 7 section immediately after Phase 6 below for its current milestone structure (Milestone 7.0 authorized, 7.1+ proposed). The dependency analysis above remains accurate and is not repeated verbatim in the new section. **Bet Timing & Execution Intelligence remains unscheduled** (not promoted to a numbered phase) — its one preserved constraint, per HQ's explicit instruction, is that it must follow Phase 7 whenever it is eventually scheduled; see its Technical Debt & Feature Backlog entry below for the current cross-reference.

**Milestone 5.6 — Recommendation Lifecycle & Change Communication — DESIGN APPROVED / DECISION LOCKED, PHASED IMPLEMENTATION, NOT YET AUTHORIZED TO BUILD (v4.9, 2026-09-04, HQ Decision Lock).** HQ directed a formal definition of what happens when MANSA changes its view after a recommendation has already been activated, ahead of Phase 12 (Beta) — fully specified in Volume 4 §9.7 and Volume 3 §5G (`docs/ops/recommendation-lifecycle-spec-2026-09-04.md`), and locked the same day across seven items: the `STRENGTHENED`/`WEAKENED`/`NO_LONGER_QUALIFIES`/`REPLACED` event-type vocabulary; `REPLACED` always creating a new product row AND a new activation snapshot, never a mutation; a mandatory, ratified "grading is status-blind" policy (an activated recommendation stays independently gradeable on its original frozen terms regardless of later lifecycle events, and a replacement/reversal is its own separate gradeable decision — HQ's own named survivorship-bias protection); a new `user_recommendation_placements` table (user-reported placement, communication-tone-only, never implying cancel/hedge/cash-out); an explicit decision NOT to touch or extend `market_monitoring_events` (Phase 7 remains its sole owner); and a locked-at-the-principle-level dashboard rule (a materially changed recommendation must never silently disappear or overwrite its previous state; exact visual treatment stays open). **Phased authorization, per the Decision Lock:** the schema/vocabulary/`user_recommendation_placements` layer may be implemented ahead of Phase 7/Phase 8 — none of it structurally depends on either. **Milestone 5.6 cannot be considered CLOSED, however, until real Phase 7 (`market_monitoring_events`-sourced) and Phase 8 (contextual-intelligence) signals can actually populate `trigger_type`** — a build that could only ever produce `model_refresh`-triggered events would not satisfy this milestone's own purpose. **Placed here as the natural continuation of Phase 5's own product/leg/lifecycle-event layer** (the schema this milestone extends is 5A/5C's own), not folded into Phase 7 (a different axis — execution/price, not analytical-validity/communication) or Phase 8 (one of several trigger *inputs*, not its owner). **Still not authorized to start building** — this entry records the locked design and its required placement in the dependency graph (below); a separate future authorization is needed before any code/migration for this milestone begins.

---

## Phase 6 — Product / UI / UX Frontend (v4.5 — fully rewritten)

**Implements:** Volume 5 v5.0 in full, per the three-pass Phase 6 Product/UX planning review (repository archaeology, HQ-approved architecture — Quant Broadcast/Desk Open visual direction, five-destination IA, four-layer recommendation detail, Time Machine six-stage stepper, narrowed Track Record scope).

**Milestones:**
1. **Design system** — Quant Broadcast/Desk Open tokens (Volume 5 §4) implemented and consumed by Tailwind config; base low-level UI primitives built. No product screens yet.
2. **Thin read-only API exposure** — routes exposing already-existing Phase 1-5 data/logic only (recommendation feed/detail, Time Machine reconstruction, grading/track-record aggregation, own-tier read). No new betting intelligence, no new recommendation-ranking logic, no new analytical engines, no new entitlement-existence logic. RLS preserved exactly as-is.
3. **Core recommendation experience** — `/today`, `/recommendations`, `/recommendations/[displayId]` (four layers), all legitimate card/state variants including No Bet Today and Bankroll Preservation as distinct, equally-weighted treatments. No artificial "top pick" — a single qualifying recommendation may receive hero treatment, multiple recommendations render as an unordered semantic set with neutral display ordering only (Volume 5 §5).
4. **History / Time Machine** — `/history`, `/history/[displayId]`, the stable six-stage vertical stepper (Volume 5 §5), translating `reconstruct_recommendation_product()`'s output into bettor-facing language, never a raw audit log by default.
5. **Track Record** — `/track-record`, product-level (never leg-level-blended) win/loss/push/void record + sample-size-aware zero/low/mature states, scoped to only what's directly stored or cheaply derivable. Units/ROI/EV/CLV/calibration/projected/verified performance excluded — future capability, no placeholder charts.
6. **Onboarding / Account / Auth** — `/onboarding` (dashboard-first, `jurisdiction_state` only), `/account` (profile, own-tier display, auth/session state), real customer signup/login/logout wired to the already-proven Phase 2 Supabase Auth backend (frontend currently has zero Supabase awareness — adding the SDK dependency and client env-var exposure is in scope; no new backend/auth architecture is).
7. **Responsive / accessibility / polish** — mobile-priority for Today/cards/Layers 1-2, desktop-optimized for Layers 3-4/Time Machine/Track Record (Volume 5 §8); WCAG 2.1 AA audit; loading/unavailable/error states across all built screens.

**Explicitly out of scope for this phase (do not silently build when a UI gap reveals the need — flag and stop instead):** conversational backend (`conversation_messages`, NL intent classification — Volume 4 §7 remains unbuilt), bet-slip verification/OCR, "My Bets," parlay construction/intelligence, the `user_recommendation_selections` personalized-stake writer (schema exists, remains an explicitly unplaced future capability — not this phase's job to build, not silently deferred to an unofficial "Phase 6.5"), notifications infrastructure (Volume 5 §7, no `notifications` table exists), Market Integrity, Bet Timing & Execution Intelligence, Adaptive Weighting promotion, any new recommendation/ranking algorithm.

**Key Tasks:**
- Implement design tokens first, before any component (Volume 5 §4)
- Build components against the real Phase 5 data model (Volume 5 §5) — `recommendation_products`/`recommendation_legs`/the explanation tables/activation snapshots/grade events — not the pre-Phase-5 shapes this section originally cited
- Build the minimal onboarding flow (Volume 5 §6) — `jurisdiction_state` only; do not ask questions with no current product consumer
- Build No Bet Today and Bankroll Preservation as distinct, first-class UI treatments, not one generic empty state
- Before implementing the Track Record milestone, verify existing product-grade event semantics genuinely support the proposed Win/Loss/Push/Void presentation for every currently-active recommendation type; if an outcome can't be honestly represented at the product level, narrow the UI rather than inventing an aggregation rule
- Any agent-count/committee-size UI language must derive from live system data, never hardcode the originally-specified 22 (Volume 1 v3.1, Volume 4 v5.10)

**Dependencies:** Phase 5 complete (needs a working recommendation pipeline to render real data against) and Phase 2 (needs auth for onboarding — already formally closed and live-proven, per Phase 2's own closure record below).

**Acceptance Criteria:**
- A new user can complete onboarding (jurisdiction only) and reach `/today`, seeing either a real recommendation or a correctly-differentiated No Bet Today / Bankroll Preservation state, with no dead-end or blank screen at any step
- No screen implies a business ranking (top pick, best bet, #1) that isn't backed by a persisted field
- Every component consuming backend data uses typed contracts with no untyped `any` shortcuts on the data layer
- No Category C metric (units, ROI, EV, CLV, calibration, projected/verified performance) appears anywhere in the shipped Track Record UI
- Mobile-priority rendering verified for `/today` and the recommendation feed/cards specifically; desktop rendering verified for Layers 3-4, Time Machine, and Track Record

**Testing Requirements:**
- Full onboarding flow tested as an automated end-to-end test, not just manually clicked through once, mirroring the proof pattern already established for Phase 2 (`scripts/phase2_e2e_test.py`)
- Contract test on every thin read-only route confirming it returns only existing data/logic, no new server-side computation
- Visual regression testing on the core component set once the design system is locked
- Accessibility audit against the WCAG 2.1 AA baseline (Volume 5 §8) — keyboard navigation and screen-reader labeling specifically, before this phase is called done

---

## Phase 7 — Market Integrity & Anomaly Intelligence

**New phase (v4.6, 2026-09-02, HQ decision)** — promoted from the "Future Phase 5 capabilities" note (v4.1) after Phase 5 closed before either capability there was scheduled. Fully specified in Volume 4 §8.5; Bet Timing & Execution Intelligence (§9.5) must follow this phase whenever it is eventually scheduled but is not itself a numbered phase.

**Implements:** Volume 4 §8.5.

**Status as of v4.9 (2026-09-04, HQ authorization):** Milestone 7.0 (Contract Audit & Mechanism Decision) COMPLETE 2026-09-02. **Milestone 7.1 (Deterministic Unexplained-Movement Detection Engine) AUTHORIZED AND COMPLETE, 2026-09-04** — backend only, no consumers, per its own scope below; see the dated note under Milestone 7.1 itself for full build detail. Milestones 7.2/7.3 remain **proposed below, NOT authorized.**

**Milestone 7.0 findings (audit only, no code written):**
- **Odds history in DEV is not usable for empirical calibration.** Live inspection (not schema-only): `odds_snapshots` has 4 total rows, spanning 1 game, with only one (game, sportsbook, market_type) group ever reaching 2 samples — exactly one computable price delta exists in the entire dataset, and the row/timestamp pattern (3 of 4 rows sharing one identical microsecond timestamp) indicates seed/fixture data, not organically captured history. `market_monitoring_events` has 1 row (also seed-pattern), not the 0 prior static code inspection expected — confirmed live, flagged as a discrepancy from the earlier static claim, consistent with seed data rather than any application code writing to it (still zero Python code references the table).
- **Closing Line Movement Agent** (`apps/ai-orchestrator/app/agents/closing_line_movement.py`) is real and built — an LLM-backed committee agent that *interprets* an already-deterministic `LineMovementFeatures` computation (`apps/ai-orchestrator/app/features/market.py`: opening/latest price & point, movement deltas, direction, sample count, `insufficient_history` flag, computed per `(sportsbook, market_type, side)` from real `odds_snapshots` rows, ≥2 snapshots required or an honest null). It answers "how has the line moved," never "is this movement explained" — that second question remains unbuilt, exactly as Volume 4 §8.5 describes. The deterministic feature computation itself is directly reusable, not to be duplicated.
- **Explanatory data comparability** (injury/weather/lineup/news, all four checked directly against real schema and ingestion code): Injuries (`injury_reports`), Weather (`weather_snapshots`), and Lineup/Roster (`roster_memberships`, `depth_chart_snapshots`) all carry real, timestamped, append-only history directly comparable to `odds_snapshots.captured_at` (same `timestamptz`, same our-own-ingestion-clock semantics). **News is the one exception** — persisted only as a single overwritten `jsonb` column on `daily_game_intelligence` (Mac's approved Option A, 2026-08-18), with no history table; once overwritten, a prior news state cannot be reconstructed. `daily_game_intelligence` itself is current-state-only for every field. A deterministic "was this movement explained" check can therefore use Injuries/Weather/Lineup as real evidence, but can never cite News as a reason a line moved or didn't.
- **`market_monitoring_events`** schema (`event_type`: line_movement/injury_update/weather_change/lineup_change/breaking_news; `action_taken`: none/updated/withdrawn) is already exactly the right shape for this capability's output — no schema change needed for Milestone 7.1's classification writes.
- **Time Machine** (`recommendation_activation_snapshots` + its FK-linked companion tables, Milestone 5.3) is built as an additive manifest specifically designed to absorb new evidence categories without altering the core manifest row — already proven three times over (lifecycle events, grading/postgame review, adaptive weighting each added as their own later, purely additive migration). An anomaly-classification table follows the identical pattern.
- **`worker-market-monitor`** remains a provisioned, empty Railway service — zero application code, confirmed by direct search.

**Threshold calibration (Decision, v4.6):** **NOT empirically derivable today** — DEV's real odds history is functionally nonexistent (one computable delta, total). Per HQ's own precedent for exactly this situation (`ADAPTIVE_WEIGHT_LEARNING_RATE = 0.25`, Milestone 5.5 — an approved initial product-policy default, explicitly not empirically derived, disclosed as such everywhere it surfaces), Milestone 7.1 must ship, if authorized, with a disclosed conservative policy threshold for NORMAL/WATCH/ELEVATED/SEVERE rather than any threshold presented as data-driven, revisited once real production-cadence odds history actually accumulates (realistically: multiple full weeks of a live NFL slate with the Odds Worker actually firing on schedule against real games — DEV's own `games` table has only 4 rows today, so this dependency is not yet met either).

**Mechanism decision (Decision, v4.6): deterministic engine, not an LLM agent.** Matches Volume 4 §8.5's own explicit warning against "just another fan-out agent," and matches every comparable guardrail already built in this codebase (Grading, Adaptive Weighting's guardrails, the 0.55 confidence floor, the EV>0 gate — all pure functions over structured inputs). An LLM's only defensible future role is an optional narrative layer describing an already-computed deterministic classification (same pattern as Postgame Review's `FakeModelAdapter`-only narrative over a deterministic grade) — never the classification decision itself.

**Service ownership (Decision, v4.6): no new worker.** The detection function belongs alongside `app/features/market.py` in `ai-orchestrator` (where `LineMovementFeatures` already lives) and runs synchronously inside the existing Recommendation Worker cycle — matching Volume 4 §8.5's own stated architectural position (`Market/Data Refresh → Committee → Market Integrity → Strategy Engine`, a pipeline stage, not a freestanding poller). `worker-market-monitor` stays a reserved, unused placeholder — its plausible future role is Bet Timing's continuous re-evaluation loop (§9.5), explicitly out of this phase's scope, not Milestone 7.1's synchronous per-cycle check.

**Language lock (Decision, v4.6):** ALLOWED terminology — STATISTICAL ANOMALY, MARKET ANOMALY, UNEXPLAINED MARKET MOVEMENT (the core buildable signal), neutral magnitude/direction/timing description, explicit reliability/confidence disclosure. Actual "integrity" language (rigging, manipulation, insider activity, etc.) is PROHIBITED absent a confirmed authoritative source (regulator action, official investigation, credible reporting) with provenance preserved — per Volume 4 §8.5's own three-tier framework (statistical anomaly / market anomaly / confirmed integrity information, never conflated).

**Milestones (7.1-7.3 proposed, not authorized):**
1. **7.0 — Contract Audit & Mechanism Decision.** COMPLETE (this entry).
2. **7.1 — Deterministic Unexplained-Movement Detection Engine (backend only, no consumers). AUTHORIZED AND COMPLETE, 2026-09-04.** A new deterministic module (`app.features.market_integrity`, `app.persistence.market_integrity`, `app.orchestration.market_integrity`, all in `ai-orchestrator`) computing INSUFFICIENT_HISTORY/NORMAL/WATCH/ELEVATED/SEVERE from `LineMovementFeatures`, writing real rows to `market_monitoring_events` for the first time (`event_type='line_movement'`, `action_taken` always `'none'` — Milestone 7.0's own decision, unchanged). No Strategy Engine wiring, no withdrawal, no UI, no cron/worker wiring — `assess_game_market_integrity` is reachable only by direct import (this milestone's own 42 new tests) and by a future Milestone 7.2's explicit wiring. Explanatory-evidence check extended to FOUR categories, not three: injuries/weather/lineup (Milestone 7.0's original three) PLUS **News**, now included because `news_article_history` (Volume 3 §4.4, built 2026-09-04 in the Pre-9/9 Data Preservation pass) closed the exact gap Milestone 7.0 flagged ("News... can never cite... as a reason a line moved or didn't"). Thresholds (`POINT_MOVEMENT_THRESHOLDS`/`PRICE_MOVEMENT_THRESHOLDS`, `THRESHOLD_VERSION="v1-provisional"`) and the explanatory-evidence lookback window (`EXPLANATORY_EVIDENCE_LOOKBACK=24h`) are disclosed-conservative policy defaults, explicitly NOT empirically derived — DEV's real odds history remains exactly as thin as Milestone 7.0 found it (4 rows/1 game/1 computable delta, live-reconfirmed unchanged 2026-09-04), so validation is fixture-first (42 new tests: 24 feature, 10 persistence, 8 orchestration), not a live DEV proof. Full regression 784/784 (ai-orchestrator), 654/654 (sports-intel-layer, unchanged), 39/39 (workers, unchanged) — `cron-odds-worker`, `app.workers.odds_worker`/`player_props_worker`, and every Odds/Player Props file untouched by this pass. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
3. **7.2 — Strategy Engine Integration & SEVERE Suppression (backend only).** Wires the validated signal into Strategy Engine, reusing the existing `recommendations.status = 'withdrawn'` mechanism for SEVERE — no new state machine.
4. **7.3 — Explainability & Command Center Disclosure.** The first user-visible capability: extends the already-designed Layer 3/4 `dataLimitations`/evidence fields, plus a minimal, restrained Command Center indicator — never a gauge, meter, or permanent fixture, only rendered when a real classification exists.

**Key Tasks (7.1+, once authorized):** Build the deterministic module fixture-first, same discipline as `app.features.grading`; give `market_monitoring_events` its first real writer; add one new FK-linked, append-only table to the Time Machine manifest per its established additive pattern; never fabricate a "sharp money" or "public betting" signal — that remains a separate, permanently-blocked vendor-data gap (Volume 2 §8), not to be conflated with market-movement anomaly detection (Volume 4 §4).

**Dependencies:** Phase 3 (`odds_snapshots`, built), Phase 4 Milestone 4.4 (Closing Line Movement Agent, built), Phase 5 Milestone 5.1 (Strategy Engine, built). Not dependent on Phase 6, though Milestone 7.3 benefits from it being closed (it now is). Not dependent on Phase 8 (Contextual Performance Intelligence), or on Phase 9/10/11 (Twilio/OCR/Analytics).

**Explicitly out of scope:** Bet Timing & Execution Intelligence (§9.5 — must follow this phase, not built here); Sharp Money/Public Betting data (permanently blocked, separate vendor gap); any numeric threshold presented as empirically derived without real accumulated data to support it; parlay/correlation intelligence; team logos/colors; new sports provider integrations; any change to recommendation ranking, grading semantics, or adaptive-weight promotion.

**Acceptance Criteria / Testing Requirements:** To be defined per-milestone as each is authorized, following this project's established fixture-first + live rollback-wrapped SQL proof discipline (Grading, Explainability, Adaptive Weighting all set this precedent) — not written here in advance of authorization, per the same "don't force a milestone before its scope is real" principle this document applies throughout.

---

## Phase 8 — Contextual Performance Intelligence

**New phase (v4.7, 2026-09-04, HQ decision)** — added directly, not promoted from an existing backlog/future-capability note the way Phase 7 was (Phase 7 had Volume 4 §8.5 fully specified since 2026-08-25, weeks ahead of promotion; Phase 8's Volume 4 §8.6 spec was written in this same pass). This is a real, disclosed departure from this project's own established "spec fully in a Volume first, then promote to a numbered phase" discipline — flagged here rather than silently treated as equivalent precedent.

**Implements:** Volume 4 §8.6.

**Status as of v4.7:** Milestone 8.0 (Contract Audit & Architecture Decision) **AUTHORIZED AND COMPLETE, 2026-09-04.** Milestones 8.1+ (the contextual-impact computation engine itself) are **proposed below, NOT authorized** — no product code, migration, or worker exists yet for this phase.

**Milestone 8.0 findings (audit only, no code written) — full detail in Volume 4 §8.6 and `docs/ops/2026-data-preservation-requirement.md`:**
- **Several named context factors already have real, usable, timestamped history** this capability could query directly without any new capture pipeline: injuries/availability (`injury_reports`), lineup/depth-chart changes and teammate dependency (`depth_chart_snapshots`, `roster_memberships`), and pregame weather/venue/home-away (`weather_snapshots`, `games.venue_lat`/`venue_long`/`venue_type`). This is a genuine existing strength, confirmed by direct schema inspection, not assumed.
- **A confirmed, material gap: no play-by-play or game-event table exists anywhere in this schema.** `player_stats`/`team_stats` are single, post-finalization snapshots (Postgame Ingestion Worker) — there is no quarter-by-quarter or play-level record of how a final stat line was produced. "Game state/script" and any in-game-sequencing-dependent context factor cannot be reconstructed at any depth from what this schema captures today.
- **A confirmed, material, and immediately time-sensitive gap: Odds/Player Props/Injury/Weather Workers all stop polling a game at its own kickoff** (`app.workers.windows`'s `Window.STOPPED`, Volume 2 §8) — no in-game weather change, in-game injury/inactive update, or in-game odds movement is captured by any currently-running worker, for any game, ever, unless this changes before it's played. See the 2026 Data Preservation Requirement for the full, dated finding and recommendation.
- **A confirmed gap: playing surface (turf vs. grass) is not captured** anywhere in `games` or any supporting table.
- **News has no history** (re-confirmed, same finding as Phase 7 Milestone 7.0's audit) — a material news event's (injury, inactive designation, suspension, lineup change, trade) precise timestamp/content cannot be reconstructed once `daily_game_intelligence.news` is next overwritten, which weakens this capability's own "News → context" connection (Volume 4 §8.6) until a structured, timestamped News event history exists.
- **No "comparable situation" retrieval capability exists anywhere** — the raw material (`player_stats`/`team_stats`/`games`) exists, but nothing today computes, caches, or reuses a "find similar historical situations" query. This is genuinely new computation, not a missing table alone.
- **Historical backfill depth is currently mixed and provider-dependent** (2026-09-03 NFL provider bake-offs) — BALLDONTLIE at least one prior season, API-SPORTS 2022-2024 only, MySportsFeeds prior-season listings plan-restricted on the evaluated key. "Comparable sample size" and "recency" both depend on backfill depth this project has not yet fully resolved with any single provider.

**Threshold/rigor calibration (Decision, v4.7):** **NOT invented by this entry**, same discipline as Phase 7's own NORMAL/WATCH/ELEVATED/SEVERE deferral and the Adaptive Weighting learning-rate precedent. No minimum comparable-sample-size, similarity cutoff, recency decay rate, or confidence band is set here — Milestone 8.1+, if authorized, must derive these from real accumulated comparable-situation data or ship with a disclosed conservative default exactly as those precedents did, never presented as empirically derived before it is.

**Mechanism decision (Decision, v4.7): deterministic computation, not an LLM agent, feeding existing agents rather than replacing them.** Matches Volume 4 §8.6's own reasoning and Volume 2 §1.1's "never delegate to an LLM what application code can compute" principle: the evidence-quality requirements (sample size, similarity, recency, confidence, confounders) are reproducible computation, not reasoning. The existing Injury Intelligence/Weather/Travel & Fatigue/Rest Days (§2.2), Offensive/Defensive Matchup/Team Form/Player Prop (§2.3), and Probability Modeling (§2.5) agents are not replaced or duplicated — they gain a new, richer, evidence-graded upstream input where today they reason narratively over raw context alone.

**Service ownership (Decision, v4.7, tentative — see the disclosed departure above): likely a new deterministic module in `ai-orchestrator`** (e.g. `app/features/contextual_performance.py`), alongside `app/features/market.py`, not a new worker and not a new agent — mirroring Phase 7's own "no new worker" decision. **Unlike Phase 7, this placement has not been confirmed against a working committee-wiring prototype** — whether feeding this module's output into Probability Modeling and the Context & Data/Matchup agents requires reopening any Phase 4 agent code is an explicit open question for Milestone 8.1's own contract audit, not resolved here.

**Milestones (8.1+ proposed, not authorized):**
1. **8.0 — Contract Audit & Architecture Decision.** COMPLETE (this entry).
2. **8.1 — Comparable-Situation Retrieval & Evidence Scoring (backend only, no consumers).** A new deterministic module computing comparable historical situations (by whatever similarity/recency/sample-size logic Milestone 8.1's own inspection derives) from already-persisted `player_stats`/`team_stats`/`injury_reports`/`depth_chart_snapshots`/`weather_snapshots`/`games` data, producing a player/team impact estimate with disclosed confidence and an explicit "insufficient comparable evidence" outcome. No agent wiring yet.
3. **8.2 — Committee Integration.** Wires the validated signal into the relevant existing agents' inputs (§2.2/§2.3/§2.5) — the milestone where the "does this require reopening Phase 4" question from Milestone 8.0 above gets a real answer.
4. **8.3 — Explainability & Market Propagation.** Extends Explainability (§8) to disclose contextual-impact evidence (FACT/INFERENCE/INSUFFICIENT-EVIDENCE, mirroring §8.5's own category discipline) and confirms the impact signal actually reaches player props/moneyline/spread/totals, not only whichever market it was first validated against.

**Key Tasks (8.1+, once authorized):** Build the deterministic module fixture-first, same discipline as `app.features.grading`/`app.features.market`; never fabricate a contextual pattern from an isolated observation; never suppress or dress up "insufficient comparable evidence" as a lower-confidence answer; resolve the News-history gap (Volume 4 §8.6's own flagged prerequisite) before wiring News as a context input, not around it.

**Dependencies:** Phase 4 (agent committee, built — Probability Modeling and the relevant Context & Data/Matchup agents this capability feeds), Phase 5 Milestone 5.1 (Strategy Engine, built). Not dependent on Phase 6 or Phase 7, though it should account for whatever Phase 7 establishes about deterministic-signal-into-committee wiring once Phase 7's own Milestones 7.1+ are built, as the most directly comparable precedent. **Depends on the 2026 Data Preservation Requirement being addressed for any context factor Milestone 8.1+ intends to use that isn't currently captured** — a milestone cannot honestly claim comparable evidence for data that was never recorded.

**Explicitly out of scope:** any numeric threshold presented as empirically derived without real accumulated data to support it; building or backfilling any new data-capture pipeline (that is the Data Preservation Requirement's and the relevant Phase 3 workers' scope, not this phase's); parlay/correlation intelligence beyond what §9's existing market-mixing rule already anticipates; new sports/provider integrations; any change to recommendation ranking, grading semantics, or adaptive-weight promotion.

**Acceptance Criteria / Testing Requirements:** To be defined per-milestone as each is authorized, following this project's established fixture-first + live rollback-wrapped SQL proof discipline — not written here in advance of authorization, same principle Phase 7 applied.

---

## Phase 9 — Twilio Integration

**Renumbered from Phase 8 to Phase 9 (v4.7, 2026-09-04, HQ decision)** — Contextual Performance Intelligence was inserted as the new Phase 8; this phase's scope is unchanged, only its position shifted. (Originally Phase 7, renumbered to Phase 8 at v4.6, 2026-09-02, when Market Integrity & Anomaly Intelligence was promoted to Phase 7.)

**Implements:** Volume 5 §7

**Milestones:**
1. Outbound SMS for time-sensitive notification types live
2. Inbound SMS routed through the same NL Engine intent classification as web chat
3. `notifications` table populated correctly across channels

**Key Tasks:**
- Wire outbound SMS for `new_recommendation` and `market_alert` notification types only, per Volume 5 §7's anti-spam reasoning — resist scope creep into every notification type
- Build the inbound Twilio webhook (`/v1/webhooks/twilio`, Volume 2 §6) and route it through the Volume 4 §7 NL Engine, not a separate SMS-specific parser
- Confirm a user can reply to an SMS alert conversationally and get a response that reflects the same intent classification as the `/chat` web interface

**Dependencies:** Phase 6 complete (needs the NL Engine's web-chat integration proven first, since SMS reuses it) and Phase 5 (needs real recommendations to notify about). Not dependent on Phase 7.

**Acceptance Criteria:**
- A test recommendation triggers an outbound SMS within the expected latency
- Replying "give me something safer" via SMS produces the same classified intent as typing it in `/chat`, verified by comparing the two paths' output
- Notification records are correctly written to the `notifications` table for both directions

**Testing Requirements:**
- Twilio sandbox/test number used for all pre-production testing — never test against a real user-facing number in `staging`
- Load test for a Sunday-slate-scale burst of simultaneous outbound notifications, since this is a realistic peak scenario the master spec's scalability requirement should be validated against

---

## Phase 10 — OCR / Bet Slip Verification

**Renumbered from Phase 9 to Phase 10 (v4.7, 2026-09-04, HQ decision)** — scope unchanged, only position shifted, per the same Phase 8 insertion noted in Phase 9's own renumbering note above. (Originally Phase 8, renumbered to Phase 9 at v4.6, 2026-09-02.)

**Implements:** Volume 3 §6 (`bet_slips`, `verified_bets`), master spec OCR requirement

**Milestones:**
1. Image upload to Supabase Storage working
2. OCR extraction pipeline producing structured data from bet slip images
3. Extracted data correctly linked to `verified_bets` and, where applicable, a `recommendation_id`

**Key Tasks:**
- Build the upload flow, explicitly optional per Volume 1 §6 / master spec — verify the rest of the product functions completely with zero bet slips ever uploaded, as a deliberate test, not an assumption
- Integrate an OCR/vision pipeline to extract stake, odds, bet type, sportsbook, legs, payout, event details
- Build the matching logic that links an uploaded slip to an existing recommendation where the details plausibly match, without forcing a match where one doesn't exist

**Dependencies:** Phase 6 complete (needs the frontend upload UI) and Phase 1 (target tables must exist).

**Acceptance Criteria:**
- A representative sample of real-format bet slip images (multiple sportsbooks) extracts correctly at an acceptable accuracy threshold — define this threshold explicitly before calling the phase done, don't leave it implicit
- A user who never uploads a bet slip experiences zero degraded functionality anywhere else in the product
- Extracted data correctly populates `verified_bets`, and `verified_user_performance` reflects it distinctly from projected performance, per the Volume 3 §6 separation

**Testing Requirements:**
- OCR accuracy tested against a curated set of real (or realistic mock) slip images per major sportsbook format
- Explicit test that verified performance and projected performance remain in separate tables/charts after a slip is uploaded and processed — this is the one place in the whole build where accidental blending is easiest to introduce by mistake, so it deserves its own dedicated regression test

---

## Phase 11 — Analytics

**Renumbered from Phase 10 to Phase 11 (v4.7, 2026-09-04, HQ decision)** — scope unchanged, only position shifted, per the same Phase 8 insertion noted above. (Originally Phase 9, renumbered to Phase 10 at v4.6, 2026-09-02.)

**Implements:** Volume 5 §5 (Charts), Volume 1 §8 (Success Metrics)

**Milestones:**
1. `/analytics`, `/performance`, `/ai-insights`, `/agent-performance` pages live
2. Business metrics from Volume 1 §8 instrumented and dashboarded internally
3. Chart components correctly separating AI/projected/verified series

**Key Tasks:**
- Build the four analytics-related pages from Volume 5 §3's route table
- Instrument the business metrics from Volume 1 §8 (Month-2 retention, Free→Pro conversion by persona, explainability panel open rate, Elite upgrade rate after a No Bet Today day) into an internal admin view — these are product decisions, not user-facing charts, and need their own home
- Confirm every chart touching performance data respects the three-way separation from Volume 3 §6 / Volume 5 §5

**Dependencies:** Phase 6 complete (needs core frontend) and enough recommendation history from Phases 4–5 running in `staging`/early `production` to have real data to chart.

**Acceptance Criteria:**
- Internal team can view all Volume 1 §8 business metrics without querying the database directly
- User-facing analytics pages render correctly with both populated and empty (new user, no history yet) states
- A manual audit confirms no chart or query anywhere blends `ai_performance`, `projected_user_performance`, and `verified_user_performance`

**Testing Requirements:**
- Data accuracy spot-check: manually verify a handful of chart values against raw database queries before trusting the aggregation logic
- Empty-state testing for a brand-new user with zero history across every analytics page

---

## Phase 12 — Beta

**Renumbered from Phase 11 to Phase 12 (v4.7, 2026-09-04, HQ decision)** — scope unchanged, only position shifted; its dependency list below now also names Phase 8 as an explicit mandatory prerequisite, not merely part of a numeric range. (Originally Phase 10, renumbered to Phase 11 at v4.6, 2026-09-02, when its dependency list gained Phase 7.)

**Implements:** Volume 1 personas (real-user validation), Volume 4 §11 (live calibration check)

**Milestones:**
1. Closed beta cohort recruited, weighted toward Persona A (Grinder) per Volume 1 §9's go-to-market reasoning
2. Feedback loop established (structured, not just informal)
3. Real-world confidence calibration compared against the pre-launch backtest from Volume 4 §11
4. Legal/compliance review (Volume 1 §10) completed before beta expands beyond a controlled jurisdiction set

**Key Tasks:**
- Recruit a small, deliberately Persona-A-weighted beta cohort — this validates the highest-LTV, most-scrutinizing segment first, consistent with the go-to-market sequencing from Volume 1 §9
- Set up a structured feedback channel (not just "let us know if something breaks") — specifically ask beta users to stress-test the reproducibility claim (Volume 1's Journey 3) since that's the claim most likely to lose a skeptical user permanently if it fails even once
- Compare live confidence calibration against the backtested numbers from Volume 4 §11; this is the first real-world check on the 0.55 threshold and weighting defaults flagged as launch assumptions
- Complete the legal/compliance review flagged as open since Volume 1 §10 — jurisdiction gating enforcement (already built in Phase 2) should be exercised for real here, limited to cleared states only

**Dependencies:** Phases 6–7 and 9–11 complete, **PLUS Phase 8 (Contextual Performance Intelligence) explicitly, as a mandatory prerequisite, not merely a number inside a range** — beta needs the full product surface, not a partial build, to generate meaningful signal, and HQ's explicit instruction (2026-09-04, v4.7) is that MANSA must be able to learn how comparable context changes expected performance, and propagate that across player props/moneyline/spread/totals/parlays, before real-user validation begins. (This range was "Phases 6–10" before the v4.7 Phase 8 insertion, and "Phases 6–9" before the v4.6 Phase 7 promotion — both prior figures are superseded, not additional history to reconcile against.) **PLUS Milestone 5.6 (Recommendation Lifecycle & Change Communication, design locked above, v4.9, 2026-09-04) explicitly, CLOSED (not merely started)** — per HQ's own directive, real recommendations will change between morning analysis and kickoff during any live beta cohort, and an unhandled silent-disappearance case would directly damage the Time Machine reproducibility claim this phase's own acceptance criteria already depend on (below). Per Milestone 5.6's own phased-completion condition, "closed" here specifically requires real Phase 7/Phase 8 signals already feeding its `trigger_type` — not merely the schema existing. Also: the beta access model reviewed 2026-08-07 (dedicated `beta_testers` table — not additional `user_profiles` columns — integrated with the existing `feature_flags` entitlement system per that review's six-point assessment) must be implemented before this phase starts, ahead of cohort recruitment (Milestone 1). Placeholder only as of this note — no schema changes made yet; see Technical Debt & Feature Backlog below.

**Acceptance Criteria:**
- Beta cohort actively using the product for a defined minimum window (recommend at least one full sport week cycle, ideally several, before drawing conclusions)
- At least one beta user has independently attempted to verify the Time Machine reproducibility claim and confirmed it holds
- Calibration comparison completed with a documented decision: keep the 0.55 threshold as-is, or adjust it — either way, this should produce the MINOR version bump to Volume 4 anticipated back in that volume's changelog entry
- Legal sign-off obtained for the specific jurisdiction set beta (and initial production launch) will operate in

**Testing Requirements:**
- Full regression pass across all phases before beta opens — this is the point where a bug anywhere in Phases 0–11 becomes visible to real users for the first time
- Load testing against realistic beta-scale concurrent traffic during a live game window specifically, not just synthetic off-peak load

---

## Phase 13 — Production Launch

**Renumbered from Phase 12 to Phase 13 (v4.7, 2026-09-04, HQ decision)** — scope unchanged, only position shifted; its dependency below now reads "Phase 12" (Beta). (Originally Phase 11, renumbered to Phase 12 at v4.6, 2026-09-02.)

**Implements:** Volume 1 §9 (Go-to-Market), Volume 2 §5/§9 (production environment, rollback discipline)

**Milestones:**
1. Production environment promoted from validated `staging` state
2. Monitoring/alerting confirmed live and tested under real conditions
3. Public launch executed per the NFL-only, narrow-launch strategy from Volume 1 §9
4. Content strategy (public postgame reviews) live per Volume 1 §9

**Key Tasks:**
- Promote the exact validated build from beta to `production` — no last-minute changes introduced directly to production that skipped `staging` validation
- Confirm all observability from Volume 2 §9 (structured logging, error tracking, uptime/health checks feeding the System Health Dashboard) is actively monitored, not just technically present
- Execute the narrow NFL-only launch, resisting any pressure to multi-sport launch, per Volume 1 §9's explicit reasoning about data depth per sport
- Begin the public postgame review content cadence from Volume 1 §9 as an ongoing operational commitment, not a one-time launch asset

**Dependencies:** Phase 12 complete, with legal sign-off and calibration review both closed out.

**Acceptance Criteria:**
- Production environment serving real users with all monitoring green
- First live Sunday slate handled without triggering the "immediate rollback" incident protocol from Volume 2 §9 — if it is triggered, the protocol itself should be considered tested, not just the launch considered failed
- Business metrics from Volume 1 §8 flowing correctly into the internal dashboard from Phase 11 (Analytics) — **corrected v4.7, 2026-09-04**: this line read "Phase 9" both before and after the v4.6 renumbering, a stale reference to Analytics' pre-v4.6 number (9) that the v4.6 pass should have updated to 10 and didn't; now corrected to Analytics' current number (11) directly, one renumbering ahead of where the v4.6 miss would have left it

**Testing Requirements:**
- Full production smoke test immediately post-launch, covering the complete onboarding-to-recommendation flow with a real (small-stakes) test account
- First live game-day window treated as a monitored event with the team actively watching dashboards in real time, not assuming the automated alerting alone is sufficient for the first cycle

---

## Technical Debt & Feature Backlog (v4.0)

Organized by priority category rather than one flat list, specifically to keep the backlog actionable and prevent feature creep — a flat list makes everything look equally urgent, which is how scope creep happens by accident rather than by decision.

**Immediate** (blocking or near-blocking current work):
- GitHub Actions / CI pipeline issues as they surface
- Redis provisioning and configuration
- Any infrastructure issue actively blocking a phase's acceptance criteria
- **Active cross-environment isolation test (added 2026-08-07).** Phase 0's AC2 ("all three environments... are network-isolated from each other per Volume 2 §5") was accepted at Phase 0 sign-off on structural grounds only — three separate Railway environments, separate services, separate env vars, nothing in the repo configures cross-environment networking — not on an actual test that attempted a cross-environment connection and confirmed it was refused. No such active probe has ever been run. Design and run one (e.g., attempt to reach a dev service's internal Railway networking address from a staging/production container, confirm it fails) before this assumption is load-bearing for anything security-sensitive.
- **`market_monitoring_events` RLS treatment — revisit once Phase 3/5 clarifies real read patterns (added 2026-08-08).** Phase 1 Milestone 4 gave this table default-deny RLS (no anon/authenticated select policy, service-role-only), the same as the other seven non-user-facing §6-§8 tables — but flagged at the time as the least certain of the eight, since Volume 2 mentions Realtime events like `RecommendationWithdrawn` that could plausibly ride on this table rather than on `recommendations.status` changes (which already carries its own RLS and is the more likely mechanism). No active defect — just an assumption worth confirming once Phase 3's Market Monitoring Engine and Phase 5's frontend consumption patterns are real rather than speculative.
- **Beta access model implementation — required before Phase 12 (added 2026-08-07; phase number corrected v4.7, 2026-09-04 — this entry read "Phase 10" both before and after the v4.6 renumbering, a stale reference to Beta's pre-v4.6 number that the v4.6 pass should have updated to 11 and didn't; now corrected to Beta's current number, one renumbering ahead of where the v4.6 miss would have left it, matching the identical correction made to Production Launch's acceptance criteria above).** Reviewed and decided 2026-08-07: beta access should be modeled as a dedicated `beta_testers` table, not additional columns on `user_profiles`, and integrated with the existing `feature_flags` entitlement system (Volume 3) rather than a separate ad hoc gate — per that review's six-point assessment. No schema changes made yet; this is a placeholder so the decision isn't lost by the time Phase 12 actually starts. Implement as part of Phase 12 setup, ahead of cohort recruitment (Milestone 1) — see the corresponding note in the Phase 12 section above.
- **Odds provider bake-off — required before either provider is permanently selected (added 2026-08-20).** Surfaced by the v5.0 sourcing-strategy decision (`CHANGELOG.md` v5.0, Volume 2 §8): SportsDataIO's ~$10-15K/season purchase is declined for now, and the odds category has two live candidates — The Odds API (current leading candidate) and SportsGameOdds (second candidate, not yet evaluated). Before permanently selecting either, compare both against the same NFL slate (where trial/free access permits): sportsbook coverage, moneyline/spread/totals coverage, player-prop breadth, alternate markets, freshness/update frequency, missing/null fields, historical odds/props access, stable IDs, response consistency, API ergonomics, rate limits, commercial-use terms, and actual cost at The Playbook's real polling cadence. Evidence-based, not provider-marketing-based. **Explicitly not to be run now** if it would require paid access, credentials Mac hasn't supplied, or would derail Phase 4 — this is a pre-purchase validation task for whenever the odds-provider decision actually needs to be finalized, not a current-phase blocker.
- **`team_provider_ids` — required before Phase 3E-4 (Odds/Player Props Worker) begins (added 2026-08-13).** Surfaced during the 3E-2 Master Refresh planning/build: `teams` carries the same single-column `external_provider_id` limitation `games` had before `game_provider_ids` (Phase 3E-1, Decision 2) — SportsDataIO identifies teams by abbreviation (`SEA`, `NE`, `KC`), while other providers/older data use full names (`"Seattle Seahawks"`). Cross-vendor game reconciliation (matching a The Odds API event to an existing SportsDataIO-created game) needs a deterministic team match, which needs a `team_provider_ids` table mirroring `game_provider_ids`'s exact constraint pattern (Mac's explicit instruction: not ad hoc string normalization scattered through workers). Not built in 3E-1 or 3E-2 — Master Refresh only ever consumes SportsDataIO's own authoritative Schedule/Roster data and never needs cross-vendor team matching itself, so it isn't a 3E-2 blocker. It is a real blocker for whichever worker (3E-4) first needs to link a second provider's game/prop data to an existing game by team identity.
- **2026 Data Preservation Requirement — time-sensitive, added 2026-09-04, ahead of the 2026-09-09 regular-season opener.** Full audit: `docs/ops/2026-data-preservation-requirement.md`. Confirmed by direct schema/worker inspection: Odds/Player Props/Injury/Weather Workers all stop capturing at a game's own kickoff (`Window.STOPPED`), no play-by-play/game-event table exists anywhere in this schema, and News has no history table (single overwritten `daily_game_intelligence.news` field) — so in-game condition changes, game-state/script detail, and precise news-event timing for every 2026 regular-season game are permanently unrecoverable once played, unless capture changes before the season starts. This is the single most important input the new Phase 8 (Contextual Performance Intelligence, Volume 4 §8.6) will eventually need and cannot get later if it isn't captured now — **capture first, Phase 8 may process/reprocess later.** No code changed by the audit itself; see the linked report for the specific recommended captures and the decisions HQ needs to make.
- **News cadence redesign — required before any GNews Essential production decision (added 2026-09-04).** Full audit: `docs/ops/news-cadence-architecture-audit-2026-09-04.md`; tracked in `docs/ops/news-provider-decision-record.md`. The News Worker's current up-to-32-team/15-minute-flat/no-stop-at-kickoff cadence (Volume 2 §8, as implemented) is confirmed NOT an accepted production requirement — HQ directed a redesign toward a centralized, adaptive, lower-volume strategy (baseline morning/late-afternoon refreshes, higher cadence only in justified high-value windows) before GNews Essential's 1,000 req/day quota is judged a real blocker or not. Exact production schedules are explicitly NOT locked by this entry. The separate GNews real-time/`expand=content` provisioning blocker (`docs/ops/news-provider-validation-gnews-2026-09-03.md`) remains open and is not resolved by a cadence redesign alone.

**Next Release** (planned, post-MLP, already named in Volume 1's future sports list):
- NBA
- MLB
- NHL

**Future** (real ideas, not yet scoped):
- Community picks
- Live betting
- Advanced explainability beyond the current nine-question spec
- Deeper personalized betting profiles beyond current Betting DNA
- **Market Integrity & Anomaly Intelligence — PROMOTED to Phase 7 (v4.6, 2026-09-02, HQ decision).** No longer a backlog item; fully specified in Volume 4 §8.5, see the Phase 7 section between Phase 6 and Phase 8 above. Milestone 7.0 (Contract Audit & Mechanism Decision) authorized and complete; Milestones 7.1+ (the anomaly-detection engine itself) proposed, not yet authorized.
- **Bet Timing & Execution Intelligence (added 2026-08-25) — fully specified in Volume 4 §9.5. Remains unscheduled, not promoted to a numbered phase (v4.6, 2026-09-02).** Its one preserved ordering constraint, per HQ's explicit instruction, is that it must follow Phase 7 (Market Integrity & Anomaly Intelligence) whenever it is eventually scheduled. Not yet implemented; see Phase 5's original "Future Phase 5 capabilities" note (superseded in part, still present above) for the underlying dependency analysis, which remains accurate.

**Research** (exploratory, no committed timeline):
- Personalized AI beyond the current persona-classification model
- Machine learning model training pipeline (ties to the deferred "Future ML Tables" category from `v3.0-amendments-conversational-intelligence.md` §11)
- Autonomous betting agents
- Market simulation

**How to use this list:** before adding anything new to it, check whether it already has a home elsewhere — several items above are already tracked as deferred decisions in `CHANGELOG.md` (Knowledge Graph, Public Transparency Portal, sentiment monitoring, sportsbook promotions) and don't need a second entry here. This list is for items that haven't yet been evaluated against the blueprint at all, not a duplicate of decisions already made.

---

## Notes for Using This Roadmap Going Forward

This document should be revisited whenever a volume gets a version bump. A MAJOR bump to any volume (per the `CHANGELOG.md` scheme) should trigger a check of whether the phase that implements it is already built — if so, that phase may need to be reopened, which is exactly the kind of cross-document contradiction the versioning system exists to catch early rather than discover mid-build.

---

## Changelog Entry for This Version

See `CHANGELOG.md` — v1.0, 2026-08-05, Engineering Roadmap & Build Order added as a companion document. Updated to v2.0, 2026-08-05, per external architecture review — Phases 1, 4, 5, and 6 amended directly above, not just noted in the header. Updated to v3.0, 2026-08-05 — Phases 1, 3, 4, 5, and 6 amended directly above with the conversational-first and intelligence pipeline additions. Updated to v4.0, 2026-08-06 — Phases 1, 3, and 4 amended with multi-sport core and Recommendation Worker scope, plus the new Technical Debt & Feature Backlog section. Updated to v4.1, 2026-08-25 — Phase 5 gained a "Future Phase 5 capabilities" note documenting Market Integrity & Anomaly Intelligence and Bet Timing & Execution Intelligence (fully specified in Volume 4 §8.5/§9.5) with a dependency analysis and tentative future-milestone placement (6/7) — neither implemented, neither scheduled, Milestones 1-5 unchanged. Updated to v4.2, 2026-08-25 — Phase 5's Milestone 3 text and acceptance criterion corrected to reflect that `recommendation_snapshots`/`/v1/recommendations/{id}/snapshot` (named in the original spec) are superseded by Milestone 5.3's actual additive activation-snapshot manifest (Volume 3 §5C) and internal-only reconstruction function, per direct live-schema inspection confirming the originally-named table unfit for the Phase 5 product layer. Updated to v4.6, 2026-09-02 (HQ decision) — Phase 6 formally closed; **Market Integrity & Anomaly Intelligence promoted from an unscheduled "Future Phase 5 capability" to the new Phase 7**, with the previously-numbered Phase 7 (Twilio) through Phase 11 (Production Launch) renumbered to Phase 8 through Phase 12 — no scope removed, only positions shifted. Phase 7's Milestone 7.0 (Contract Audit & Mechanism Decision) authorized and completed the same day: live DEV data confirmed odds history is not yet usable for empirical threshold calibration, explanatory-data timestamp comparability confirmed for injuries/weather/lineup but not news, Time Machine's schema confirmed able to absorb the new evidence category additively, and deterministic-engine/no-new-worker/language-lock decisions recorded. Milestones 7.1+ remain proposed, not authorized. Updated to v4.7, 2026-09-04 (HQ decision) — **new Phase 8 (Contextual Performance Intelligence)** inserted between Phase 7 and the previously-numbered Phase 8 (Twilio), fully specified in new Volume 4 §8.6; Twilio/OCR/Analytics/Beta/Production Launch renumbered to Phases 9-13 (no scope removed), and Phase 8 recorded as an explicit mandatory Beta (Phase 12) prerequisite rather than folded into the Phase 7/9/10/11 parallel group. Milestone 8.0's own contract audit (completed the same day) found several context factors already have real, usable history (injuries, pregame weather, depth charts, roster) while others have none today (in-game condition changes, play-by-play/game state, News history, playing surface) — the latter recorded as an immediate, time-sensitive 2026 Data Preservation Requirement (`docs/ops/2026-data-preservation-requirement.md`) ahead of the 2026-09-09 season opener. The same directive also authorized a News-cadence architecture audit (`docs/ops/news-cadence-architecture-audit-2026-09-04.md`), and this pass corrected two stale cross-references left over from the v4.6 renumbering (Production Launch's business-metrics acceptance criterion and the Beta-access-model backlog entry, both of which had never been updated to their post-v4.6 phase numbers).
