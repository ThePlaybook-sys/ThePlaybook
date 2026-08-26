# The Playbook — Engineering Roadmap & Build Order

**Version:** v4.3
**Last updated:** 2026-08-27
**Type:** Companion document — not a Volume. Volumes 1–5 describe *what* the system is. This document describes *the order in which to build it* and *how to know each piece is actually done* before moving to the next.
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
   ├── Phase 7 (Twilio) ──────┐
   ├── Phase 8 (OCR) ─────────┤  (7, 8, 9 can run in parallel once Phase 6 is stable)
   └── Phase 9 (Analytics) ───┘
   │
Phase 10 (Beta)
   │
Phase 11 (Production Launch)
```

Phases 7, 8, and 9 are the first genuine parallelization point — everything before Phase 6 is strictly sequential because each layer is load-bearing for the next.

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
- Load test against expected Sunday-slate polling volume before this phase is considered done, not deferred to Phase 10
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

**`user_recommendation_selections` (Volume 3 §5A) writer — assigned to Phase 6, not Phase 5 (2026-08-27).** This table's schema shipped in Milestone 5.1 with zero writers, an ownerless gap surfaced during the Milestone 5.4 inspection. The durable selection/presentation event it represents can only become real once a real user views/selects a recommendation through an actual product surface — no such surface exists before Phase 6 (Dashboard/chat). **Phase 6 explicitly owns:** the production writer for user recommendation presentation/selection persistence, Bankroll Coach's personalized selection state capture at that moment, this table's own materiality/idempotency behavior, and a Time Machine reproducibility proof using a genuinely persisted user selection (mirroring the pattern already proven for `recommendation_activation_snapshots` in Milestone 5.3). Not a 5.4 prerequisite — no code for it was built in Milestone 5.4.

**Future Phase 5 capabilities — approved/documented, deliberately NOT assigned a milestone number above (v4.1, 2026-08-25).** Two capabilities were fully specified in Volume 4 §8.5 (Market Integrity & Anomaly Intelligence) and §9.5 (Bet Timing & Execution Intelligence) without being forced into Milestones 1-5 above, per Mac's explicit instruction not to arbitrarily assign a capability to a milestone the Blueprint doesn't clearly support. Dependency analysis, performed against the actual current codebase rather than assumed:

- **Market Integrity & Anomaly Intelligence** depends on: `odds_snapshots` history (Phase 3, built), the Closing Line Movement Agent (Phase 4 Milestone 4.4, built), and the Recommendation Strategy Engine existing as a real consumer of an anomaly signal (Milestone 5.1, built). It also depends on `worker-market-monitor` actually being implemented with real monitoring logic and `market_monitoring_events` actually being written to — **both confirmed still completely unbuilt** (zero application code, zero rows) by direct inspection. **Earliest technically defensible placement: a new Phase 5 milestone (tentatively Milestone 6), after Milestone 5.1 and logically before or alongside Milestone 5.5's Continuous Learning loop** — it needs Strategy Engine to exist (it does) but does not need Explainability, Time Machine, or Continuous Learning to exist first.
- **Bet Timing & Execution Intelligence** depends on everything above, PLUS Market Integrity & Anomaly Intelligence itself (per Volume 4 §9.5's explicit integration requirement — anomaly signals feed execution state), PLUS the automatic re-evaluation loop, which depends on event infrastructure Volume 2 §4.5 already named and explicitly deferred post-MLP (`InjuryUpdated`, `WeatherChanged`, and similar consumers). **Earliest technically defensible placement: a new Phase 5 milestone (tentatively Milestone 7), strictly after the Market Integrity milestone above** — and its full realization (a user actually seeing "WAIT, check back later") likely also touches Phase 7's Twilio/notification work, even though its core decision logic belongs in Phase 5.
- **Neither is scheduled into a specific sprint by this entry** — both remain future capabilities pending a dedicated future architecture inspection (explicitly not performed here, per Mac's instruction) that would determine the exact mechanism (deterministic engine vs. specialist agent(s) vs. hybrid) before implementation begins. This entry exists so neither is forgotten or designed out, not so either is scheduled.

---

## Phase 6 — Dashboard / Core Frontend

**Implements:** Volume 5 §2–§6

**Milestones:**
1. Design tokens implemented and consumed by Tailwind config (Volume 5 §4)
2. Core component library built (Recommendation Card, Game Card, Explainability Panel, etc.)
   - **Owns the `user_recommendation_selections` (Volume 3 §5A) production writer (assigned 2026-08-27, Milestone 5.4 inspection)** — the durable selection/presentation event fires only once a real user views/selects a recommendation through this phase's own UI; also owns Bankroll Coach's personalized selection state capture at that moment, this table's materiality/idempotency behavior, and a Time Machine proof against a genuinely persisted user selection.
3. Navigation/routing per Volume 5 §3 live
4. Onboarding flow complete, ending in a live first recommendation in the same session
5. No Bet Today and Bankroll Preservation states implemented as distinct UI treatments

**Key Tasks:**
- Implement design tokens first, before any component — matches the LEGO/component-library sequencing from the Designer Guide and Volume 1 §3
- Build components against the exact prop shapes from Volume 5 §5, not ad hoc shapes that "seem close enough" to what the API returns
- Build the four-step onboarding flow from Volume 1 §6 / Volume 5 §6, with the same-session first-recommendation requirement as a hard completion gate for this milestone
- Build both distinct empty/alternate states (No Bet Today, Bankroll Preservation) rather than one generic fallback
- **v2.0 addition:** build the AI Transparency Meter and Recommendation Timeline components as part of the Explainability Panel work (`v2.0-amendments-architecture-review.md` §4)
- **v3.0 addition (biggest re-scope in this phase):** `/chat` is now the default landing route, not `/dashboard` (Volume 5 §3) — build the four-level progressive response format (Volume 4 §7) as core chat behavior, not an optional feature. The onboarding modal from Milestone 4 now layers on top of `/chat`, not `/dashboard`.

**Dependencies:** Phase 5 complete (needs a working recommendation pipeline to render real data against) and Phase 2 (needs auth for onboarding).

**Acceptance Criteria:**
- A new user can complete onboarding and see either a real recommendation or a correctly-differentiated No Bet Today / Bankroll Preservation state, in the same session, with no dead-end or blank screen at any step
- Every component consuming backend data uses the typed contracts from Volume 5 §5 with no untyped `any` shortcuts on the data layer
- Mobile-width rendering verified for the dashboard and recommendation feed specifically, per Volume 5 §8's mobile-first requirement

**Testing Requirements:**
- Full onboarding flow tested as an automated end-to-end test, not just manually clicked through once
- Visual regression testing on the core component set once the design system is locked, to catch accidental drift from the token system
- Accessibility audit against the WCAG 2.1 AA baseline from Volume 5 §8 — keyboard navigation and screen-reader labeling specifically, before this phase is called done

---

## Phase 7 — Twilio Integration

**Implements:** Volume 5 §7

**Milestones:**
1. Outbound SMS for time-sensitive notification types live
2. Inbound SMS routed through the same NL Engine intent classification as web chat
3. `notifications` table populated correctly across channels

**Key Tasks:**
- Wire outbound SMS for `new_recommendation` and `market_alert` notification types only, per Volume 5 §7's anti-spam reasoning — resist scope creep into every notification type
- Build the inbound Twilio webhook (`/v1/webhooks/twilio`, Volume 2 §6) and route it through the Volume 4 §7 NL Engine, not a separate SMS-specific parser
- Confirm a user can reply to an SMS alert conversationally and get a response that reflects the same intent classification as the `/chat` web interface

**Dependencies:** Phase 6 complete (needs the NL Engine's web-chat integration proven first, since SMS reuses it) and Phase 5 (needs real recommendations to notify about).

**Acceptance Criteria:**
- A test recommendation triggers an outbound SMS within the expected latency
- Replying "give me something safer" via SMS produces the same classified intent as typing it in `/chat`, verified by comparing the two paths' output
- Notification records are correctly written to the `notifications` table for both directions

**Testing Requirements:**
- Twilio sandbox/test number used for all pre-production testing — never test against a real user-facing number in `staging`
- Load test for a Sunday-slate-scale burst of simultaneous outbound notifications, since this is a realistic peak scenario the master spec's scalability requirement should be validated against

---

## Phase 8 — OCR / Bet Slip Verification

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

## Phase 9 — Analytics

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

## Phase 10 — Beta

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

**Dependencies:** Phases 6–9 complete — beta needs the full product surface, not a partial build, to generate meaningful signal. Also: the beta access model reviewed 2026-08-07 (dedicated `beta_testers` table — not additional `user_profiles` columns — integrated with the existing `feature_flags` entitlement system per that review's six-point assessment) must be implemented before this phase starts, ahead of cohort recruitment (Milestone 1). Placeholder only as of this note — no schema changes made yet; see Technical Debt & Feature Backlog below.

**Acceptance Criteria:**
- Beta cohort actively using the product for a defined minimum window (recommend at least one full sport week cycle, ideally several, before drawing conclusions)
- At least one beta user has independently attempted to verify the Time Machine reproducibility claim and confirmed it holds
- Calibration comparison completed with a documented decision: keep the 0.55 threshold as-is, or adjust it — either way, this should produce the MINOR version bump to Volume 4 anticipated back in that volume's changelog entry
- Legal sign-off obtained for the specific jurisdiction set beta (and initial production launch) will operate in

**Testing Requirements:**
- Full regression pass across all phases before beta opens — this is the point where a bug anywhere in Phases 0–9 becomes visible to real users for the first time
- Load testing against realistic beta-scale concurrent traffic during a live game window specifically, not just synthetic off-peak load

---

## Phase 11 — Production Launch

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

**Dependencies:** Phase 10 complete, with legal sign-off and calibration review both closed out.

**Acceptance Criteria:**
- Production environment serving real users with all monitoring green
- First live Sunday slate handled without triggering the "immediate rollback" incident protocol from Volume 2 §9 — if it is triggered, the protocol itself should be considered tested, not just the launch considered failed
- Business metrics from Volume 1 §8 flowing correctly into the internal dashboard from Phase 9, from day one of real traffic

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
- **Beta access model implementation — required before Phase 10 (added 2026-08-07).** Reviewed and decided 2026-08-07: beta access should be modeled as a dedicated `beta_testers` table, not additional columns on `user_profiles`, and integrated with the existing `feature_flags` entitlement system (Volume 3) rather than a separate ad hoc gate — per that review's six-point assessment. No schema changes made yet; this is a placeholder so the decision isn't lost by the time Phase 10 actually starts. Implement as part of Phase 10 setup, ahead of cohort recruitment (Milestone 1) — see the corresponding note in the Phase 10 section above.
- **Odds provider bake-off — required before either provider is permanently selected (added 2026-08-20).** Surfaced by the v5.0 sourcing-strategy decision (`CHANGELOG.md` v5.0, Volume 2 §8): SportsDataIO's ~$10-15K/season purchase is declined for now, and the odds category has two live candidates — The Odds API (current leading candidate) and SportsGameOdds (second candidate, not yet evaluated). Before permanently selecting either, compare both against the same NFL slate (where trial/free access permits): sportsbook coverage, moneyline/spread/totals coverage, player-prop breadth, alternate markets, freshness/update frequency, missing/null fields, historical odds/props access, stable IDs, response consistency, API ergonomics, rate limits, commercial-use terms, and actual cost at The Playbook's real polling cadence. Evidence-based, not provider-marketing-based. **Explicitly not to be run now** if it would require paid access, credentials Mac hasn't supplied, or would derail Phase 4 — this is a pre-purchase validation task for whenever the odds-provider decision actually needs to be finalized, not a current-phase blocker.
- **`team_provider_ids` — required before Phase 3E-4 (Odds/Player Props Worker) begins (added 2026-08-13).** Surfaced during the 3E-2 Master Refresh planning/build: `teams` carries the same single-column `external_provider_id` limitation `games` had before `game_provider_ids` (Phase 3E-1, Decision 2) — SportsDataIO identifies teams by abbreviation (`SEA`, `NE`, `KC`), while other providers/older data use full names (`"Seattle Seahawks"`). Cross-vendor game reconciliation (matching a The Odds API event to an existing SportsDataIO-created game) needs a deterministic team match, which needs a `team_provider_ids` table mirroring `game_provider_ids`'s exact constraint pattern (Mac's explicit instruction: not ad hoc string normalization scattered through workers). Not built in 3E-1 or 3E-2 — Master Refresh only ever consumes SportsDataIO's own authoritative Schedule/Roster data and never needs cross-vendor team matching itself, so it isn't a 3E-2 blocker. It is a real blocker for whichever worker (3E-4) first needs to link a second provider's game/prop data to an existing game by team identity.

**Next Release** (planned, post-MLP, already named in Volume 1's future sports list):
- NBA
- MLB
- NHL

**Future** (real ideas, not yet scoped):
- Community picks
- Live betting
- Advanced explainability beyond the current nine-question spec
- Deeper personalized betting profiles beyond current Betting DNA
- **Market Integrity & Anomaly Intelligence (added 2026-08-25) — fully specified in Volume 4 §8.5, tentatively Phase 5 Milestone 6.** Not yet implemented; see Phase 5's own "Future Phase 5 capabilities" note above for the dependency analysis.
- **Bet Timing & Execution Intelligence (added 2026-08-25) — fully specified in Volume 4 §9.5, tentatively Phase 5 Milestone 7, strictly after Market Integrity & Anomaly Intelligence.** Not yet implemented; see Phase 5's own "Future Phase 5 capabilities" note above for the dependency analysis.

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

See `CHANGELOG.md` — v1.0, 2026-08-05, Engineering Roadmap & Build Order added as a companion document. Updated to v2.0, 2026-08-05, per external architecture review — Phases 1, 4, 5, and 6 amended directly above, not just noted in the header. Updated to v3.0, 2026-08-05 — Phases 1, 3, 4, 5, and 6 amended directly above with the conversational-first and intelligence pipeline additions. Updated to v4.0, 2026-08-06 — Phases 1, 3, and 4 amended with multi-sport core and Recommendation Worker scope, plus the new Technical Debt & Feature Backlog section. Updated to v4.1, 2026-08-25 — Phase 5 gained a "Future Phase 5 capabilities" note documenting Market Integrity & Anomaly Intelligence and Bet Timing & Execution Intelligence (fully specified in Volume 4 §8.5/§9.5) with a dependency analysis and tentative future-milestone placement (6/7) — neither implemented, neither scheduled, Milestones 1-5 unchanged. Updated to v4.2, 2026-08-25 — Phase 5's Milestone 3 text and acceptance criterion corrected to reflect that `recommendation_snapshots`/`/v1/recommendations/{id}/snapshot` (named in the original spec) are superseded by Milestone 5.3's actual additive activation-snapshot manifest (Volume 3 §5C) and internal-only reconstruction function, per direct live-schema inspection confirming the originally-named table unfit for the Phase 5 product layer.
