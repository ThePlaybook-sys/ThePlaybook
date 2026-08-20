# Demo / Simulation Environment — Architecture & Design

**Status:** APPROVED — IN IMPLEMENTATION (approved by Mac 2026-08-19). DEMO-1 (isolation foundation), DEMO-2 (demo provider-adapter family), and DEMO-3 (virtual clock / scenario runner) are BUILT — see Section 19 for per-step status. DEMO-4 onward remain design only; each step requires its own separately-approved execution plan before implementation, per the phase-gating discipline this document was built under.

**Version:** v1.1 (2026-08-19 — incorporates Mac's approval decisions: isolation model confirmed, notification direction clarified to Telegram-first/provider-neutral, starter scenario scope expanded, implementation sequence relabeled to the DEMO-N convention. Superseded content from v1.0 is not preserved inline; see PROGRESS.md for the decision record.)
**Implementation status note (2026-08-20, no version bump — tracking only, not a design change):** DEMO-1, DEMO-2, and DEMO-3 built per Section 19's own status markers — scenario runner, virtual clock orchestration, demo persistence execution (proven against an in-memory fake standing in for Supabase; live proof against the real `theplaybook-demo` project not yet performed), and one minimal scenario are now BUILT. Not yet built: Operator Dashboard, Component Gallery, expanded scenario library, Telegram/Twilio demo delivery, Phase 4/5 Demo parity — all remain exactly as designed in this document, not implemented.

**Depends on:** Volume 1 (personas, journeys, chat-first positioning), Volume 2 §5 (Railway environment strategy), §7 (adapter pattern), §8 (Sports Intelligence Layer, cadence, caching), §9 (DevOps/CI/CD, secrets management), Volume 3 (schema, Time Machine principle, append-only pattern), Volume 4 (agent committee, explainability — not yet built), Volume 5 (dashboard/chat architecture — not yet built), `engineering-roadmap-build-order.md` (phase definitions)

**Author's note on method:** This document was produced by direct inspection of the current repository state as of 2026-08-19 — the adapter base interface (`apps/sports-intel-layer/app/adapters/base.py`), the existing fake adapters (`apps/sports-intel-layer/tests/adapters/fakes.py`), all seven Phase 3 worker entrypoints and `run_master_refresh`, the environment/secrets policy in Volume 2 §5 and §9, the Volume 3 Time Machine and append-only sections, Volume 5's routing table, and the engineering roadmap's Phase 4/5/6 definitions — not reconstructed from memory of an earlier session. Every claim below is tagged CONFIRMED (verified against repo/blueprint text this session), DERIVED (a direct, low-risk inference from CONFIRMED facts), ASSUMED (a reasonable default that has not been validated and should be treated as a proposal), or DEFERRED (explicitly out of scope for this phase). Where the prompt that requested this document and repository reality appeared to diverge, that is called out explicitly rather than silently resolved.

---

## 1. What Demo Mode Is, and Is Not

**Demo Mode is:** a permanent, first-class operating mode of The Playbook that lets someone — Mac, an investor, a sales prospect, a future support/onboarding flow — walk through realistic, scripted product behavior (a live Sunday slate ramping through its cadence tiers, an injury report changing a recommendation, a postgame review firing) **without touching any real provider, any real user's data, or any real money-adjacent system**, and without the person running the demo needing today's actual NFL schedule to line up with the demo.

**Demo Mode is not:**
- A staging environment. Staging (Volume 2 §5, CONFIRMED) already exists for "real APIs, real odds, real schedules — mirrors production behavior," for internal testers. Demo Mode's entire reason to exist is that it does **not** depend on real games happening at a real time — it is scripted, not just sandboxed.
- A second copy of the business logic. Every worker, every window-classification rule, every persistence path, every future agent-committee/consensus/explainability computation Demo Mode exercises must be the **same code** real traffic runs, per Rule 1 below. A demo that runs different logic than production isn't a demo of the product — it's a mockup that happens to be interactive, and it will drift the moment real logic changes and nobody remembers to update the mockup.
- A dev environment with nicer fixtures. Dev (Volume 2 §5, CONFIRMED) is "sandbox APIs where the provider offers them, fake/seeded data otherwise," with no users, and its own purpose (engineers iterating against something wired-up but disposable). Demo Mode has a different audience (a person watching, possibly external) and a different requirement (the story has to make sense end-to-end, not just exercise code paths).
- A finished thing to build right now. Per the explicit instruction that produced this document: **this is design only.** No infrastructure, no migrations, no environment variables, no provider calls, no frontend code, no Telegram integration, no production changes happen as a result of this document.

**Why it needs to be permanent, not a one-off script:** the same reasoning CLAUDE.md applies to the blueprint itself applies here — if Demo Mode is built once and then left to rot while Phase 4/5/6 land, it becomes actively misleading (a demo that shows behavior the real product no longer has). Section 14 below makes phase-by-phase demo maintenance a standing checklist item, not a one-time build.

---

## 2. Five Non-Negotiable Architecture Rules

These are the rules Demo Mode may never violate, regardless of how convenient a shortcut looks during implementation. Each ties back to something already CONFIRMED in the blueprint or repository.

**Rule 1 — No duplicate business logic.** Demo Mode may only ever supply a different *data source* at the boundary the adapter pattern already defines. CONFIRMED: `app/adapters/base.py`'s own docstring states the enforcement point directly — "Nothing outside this package (no worker, no agent, no other service) is allowed to import a provider SDK directly; they only ever depend on these interfaces and the normalized models." A `DemoOddsAdapter` implementing `OddsAdapter` is exactly as legitimate a citizen of that interface as `TheOddsApiOddsAdapter` — and critically, every worker, every cadence rule, every persistence function, every future agent downstream of it runs completely unmodified. If a demo need ever seems to require a worker or agent to behave differently *because* it's a demo, that is a Rule 1 violation and the design is wrong, not the rule.

**Rule 2 — Hard data isolation.** Demo data must never be reachable from, or comingled with, dev/staging/production data, and real user data must never be reachable from a demo session. This is not a new principle — it is the same reasoning Volume 2 §5 already gives for running dev/staging/production as **three separate Railway environments** rather than three logical modes of one deployment, specifically because "a staging recommendation snapshot must never pollute the production reproducibility record" (CONFIRMED, Volume 2 §5). Demo data is *more* dangerous to comingle than staging data, not less — it is deliberately synthetic and often deliberately dramatic (a scripted blowout, a scripted late-breaking injury), so a demo row leaking into a real table would corrupt not just data quality but the Time Machine reproducibility guarantee itself. Section 5 gives the recommended isolation model.

**Rule 3 — No production credential access.** A demo session — whoever is running it, wherever it runs — must never hold, request, or have a code path that could reach a real provider API key, the production `SUPABASE_SERVICE_ROLE_KEY`, or any other production secret. CONFIRMED (Volume 2 §9): secrets are Railway environment variables scoped per-environment, never committed, never shared across environments implicitly. Demo Mode's provider layer (Section 8) exists specifically so this rule is structurally true rather than policy-enforced — a `DemoOddsAdapter` has no HTTP client pointed at a real vendor at all, so there is no key for it to misuse even by accident.

**Rule 4 — Clear visual labeling.** Any UI, chat response, notification, or exported artifact produced under Demo Mode must be unambiguously marked as such to the person viewing it. This is a product-trust requirement as much as a technical one: The Playbook's core sell (per Volume 1's positioning, DERIVED) is that its recommendations are real, reproducible, and accountable — a demo screen that could be mistaken for a live recommendation undermines that claim the first time someone screenshots it. Section 9 covers the mechanism.

**Rule 5 — Roadmap parity via a permanent maintenance checklist.** Demo Mode's scenario library and Demo Parity Status table (Section 3) must be revisited as a standing item every time a phase closes — not bolted on once and abandoned. Section 14 defines this as a permanent process, not a task that gets marked done.

---

## 3. Demo Parity Status (Against Real Phase 3 Capabilities)

CONFIRMED via direct repository inspection: only `apps/sports-intel-layer` (Phase 3) has real implementation today. `apps/frontend`, `apps/ai-orchestrator`, `apps/api-gateway`, `apps/workers` are Phase 0/1 scaffolding only (health-check-level code). This table is therefore necessarily short right now — it will only grow as later phases land, which is exactly why Section 14 exists.

| Real capability (CONFIRMED, built) | Demo-able today? | Notes |
|---|---|---|
| Provider adapter pattern (8 category interfaces, `base.py`) | Yes | Demo needs one `Demo*Adapter` per category implementing the same ABC (Section 8). |
| Odds / Player Props workers, window-classification cadence (2h→5min ramp) | Yes | This is the single most demo-worthy Phase 3 behavior — "watch the cadence tighten as kickoff approaches" is a genuinely compelling scripted story, and the ramp logic is a pure function of `now`/`kickoff` (Section 6). |
| Injury worker, day-of-week-anchored cadence | Yes | Same mechanism, different classifier (`classify_injury_window`). |
| Weather / News / Roster / DepthChart / Schedule ingestion | Yes | All bulk or per-entity fetches behind the same adapter boundary. |
| Master Refresh → `daily_game_intelligence` assembly | Yes | This is Phase 3's actual product output; a demo that doesn't render DGI rows isn't demoing Phase 3 at all. |
| Postgame Worker, stat finalization | Yes | Needs a scripted "game goes final" trigger (Section 7, Scenario 6). |
| Cache metrics (v4.16), full-fleet load behavior | Partially | Demo-*able* as an "under the hood" technical show-and-tell, but not a Mac/investor-facing story — flagged ASSUMED low priority for the starter scenario set. |
| Identity resolution (player/team/game cross-provider linking) | Yes, but invisible by default | Real and load-bearing, but has no natural UI surface yet (Phase 6 doesn't exist). Worth a scenario only once there's a dashboard to show a "resolved from two providers" badge on. |
| AI agent committee, consensus, explainability | **No** — Phase 4, not built | Nothing to demo. Any Demo Mode "recommendation" shown before Phase 4 exists would have to be hand-scripted output pretending to be agent output — **this would be a Rule 1 violation** (fabricated business logic standing in for real logic) and must not be built. See Section 13's Scenario 9/10 treatment. |
| Recommendation pipeline, Time Machine (`recommendation_snapshots`) | **No** — Phase 5, not built | CONFIRMED via fresh read of Volume 3 §5: `recommendation_snapshots` does not exist as a table yet. Demo Mode cannot demo Time Machine reconstruction until Phase 5 ships it for real. |
| Dashboard / chat UI | **No** — Phase 6, not built | CONFIRMED: `apps/frontend` has only `app/page.tsx`/`app/layout.tsx`, no dashboard components. Demo Mode has nothing to render into today; this document specifies the *strategy* (Section 10) for when Phase 6 lands, not a build. |
| Twilio / notifications | **No** — Phase 7, not built | Section 11 covers the compatibility design only. |

**Bottom line (DERIVED):** a Demo Mode built today can only honestly demonstrate Phase 3 — the sports-intelligence ingestion pipeline itself (cadence, identity resolution, DGI assembly, postgame finalization). It cannot yet demo a recommendation, an explanation, a dashboard, or a notification, because none of those exist. This is not a limitation of the demo design; it is an accurate reflection of what the product currently is, and the parity table above is exactly the mechanism for keeping that honest as later phases close.

---

## 4. Isolation Model — Recommendation

Three options were evaluated, matched against Rule 2 and the existing Volume 2 §5 precedent.

**Option A — Dedicated Railway environment + dedicated Supabase project (RECOMMENDED).** A fourth environment, `demo`, structurally identical in kind to dev/staging/production: its own Railway environment, its own Supabase project, its own environment variables. CONFIRMED: `RAILWAY_ENVIRONMENT_NAME` is already the (only) mechanism the codebase uses to distinguish environments today (`apps/sports-intel-layer/app/main.py` — Sentry tagging and the dev-only `/sentry-debug` route both branch on it). Adding a fourth value the same way is a natural extension of a pattern that already exists, not a new mechanism. This gives Demo Mode the same isolation guarantee dev/staging/production already have from each other — a demo row cannot leak into a real table because there is no shared table, full stop, matching the exact reasoning Volume 2 §5 gives for the existing three-way split.

**Option B — Shared non-production Supabase project, separate Postgres schema (`demo.*`).** Cheaper (one fewer Supabase project to provision/pay for), but weaker: CONFIRMED, the append-only trigger pattern (`block_snapshot_updates()`) is applied per-table across `odds_snapshots`/`injury_reports`/`weather_snapshots`/etc. — a shared-project, schema-separated approach means demo tables either inherit those same triggers (fine) or need their own careful mirroring of them (a maintenance burden and a place for Rule 1-adjacent drift to creep in), and any future cross-schema query, backup/restore operation, or RLS policy written carelessly against `public.*` has a real chance of accidentally touching `demo.*` too. Isolation here is enforced by discipline, not by the environment boundary itself.

**Option C — Reuse the existing dev environment/database, tag rows with an `is_demo` flag.** Rejected outright. This is the weakest form of isolation of the three (a single missed `WHERE is_demo = false` filter anywhere is a real-data leak or a demo-data leak) and it directly conflicts with dev's own defined purpose (Volume 2 §5: internal engineers iterating, no external viewers) — a demo session run for an investor has no business sharing infrastructure with an engineer's disposable local iteration data.

**Recommendation: Option A**, consistent with the existing three-environment precedent and the fact that this repository already has the exact mechanism (`RAILWAY_ENVIRONMENT_NAME`-based branching) needed to extend to a fourth environment cheaply. Option B is noted as an acceptable *interim* fallback only if cost/provisioning constraints (a decision for Mac, not made here) rule out a fourth Supabase project — but it should be treated as a deliberate, documented trade-off if chosen, not a default.

**Explicitly ASSUMED, not decided here:** whether `demo` should be a real Railway environment with its own always-on services, or a Railway *environment that only spins up on demand* (cheaper, since nobody's watching a demo 24/7). That's an infrastructure decision for the implementation phase, not this design document.

---

## 5. Simulated Clock Design

The demo's entire value proposition — "watch a live Sunday slate happen right now, regardless of what day it actually is" — depends on controlling *what time the system believes it is* without touching real system clocks.

**A concrete, CONFIRMED finding that shapes this section:** every one of Phase 3's real entrypoints already accepts an explicit clock override, defaulting to real wall-clock time only when the override is omitted:
- `run_odds_worker`, `run_pregame_worker`, `run_injury_worker`, `run_weather_worker`, `run_player_props_worker`, `run_postgame_worker`, `run_news_worker` — all accept `now: datetime | None = None`.
- `run_master_refresh` accepts `today` with the same optional-override pattern (`today = today or datetime.now(timezone.utc).date()`).
- The underlying pure classification functions (`classify_window`, `should_poll`, `classify_injury_window`, `should_poll_injuries` in `app/workers/windows.py`) take `now` as a required keyword argument — they were never coupled to wall-clock time in the first place.

This means the simulated clock does **not** require touching a single line of real worker/orchestration code. Four options were evaluated:

1. **Wall-clock passthrough with pre-dated fixtures.** No clock simulation — scenarios use whatever `datetime.now()` actually is. Rejected: this cannot produce "watch cadence ramp toward a kickoff happening right now" unless a real kickoff happens to be imminent, which defeats the entire point of a demo not depending on the real schedule.

2. **Full dependency-injection refactor of every `datetime.now()` call site.** Rejected as unnecessary and out of proportion: it would mean touching real production files that today have no reason to change, purely to serve a demo need — a direct tension with Rule 1's spirit (don't let the demo's needs leak into changing how real code is written) and simply not required, given the finding above.

3. **A demo-only virtual clock, owned entirely by the demo orchestration layer, that computes `now`/`today` values and passes them into the *existing* optional-override parameters (RECOMMENDED).** The demo runner tracks one value — call it `virtual_now` — per running demo session, advances it according to the scenario's script (Section 6), and calls the real `run_odds_worker(..., now=virtual_now)`, `run_master_refresh(..., today=virtual_now.date())`, etc. Zero production code changes. The real cadence/classification logic runs completely unmodified against a clock the demo controls. This is a direct, low-effort consequence of the CONFIRMED optional-override pattern already in place — DERIVED, not a new architectural invention.

4. **Time-compressed live playback** (e.g., 1 real minute = 1 simulated hour, continuously advancing in the background). Evaluated as a *presentation* mode layered on top of Option 3, not a replacement for it — the underlying mechanism is identical (compute a `virtual_now`, feed it to the same override parameters); the only difference is whether `virtual_now` advances on a timer or only on discrete scripted steps. Recommended as a **future enhancement**, not part of the initial build, since Section 6's discrete step-based scenario format is simpler to script, test, and narrate live.

**Recommendation: Option 3**, with Option 4 noted as a natural later extension of the same mechanism rather than a competing design.

---

## 6. Scenario Format Definition

A **scenario** is a versioned, checked-in data structure (proposed: a Python dataclass or a declarative YAML/JSON file under a new `demo/scenarios/` directory — file format is an implementation-phase decision, not fixed here) that fully describes one scripted story. A scenario has:

- **`id` / `title` / `description`** — human-readable identity, shown in the demo operator UI (Section 12) and in Rule 4's on-screen labeling.
- **`slate`** — the synthetic games/teams/players the scenario operates over (a small, fixed, clearly-fake roster — e.g. reusing the same synthetic-team convention already established by this session's own load tests, `H##`/`A##`-style placeholder abbreviations, or equally-fake but more presentable names — an implementation-phase choice).
- **`steps`** — an ordered list of `(virtual_now, action)` pairs, where `action` is one of: *advance the clock and re-run a named worker/Master Refresh*, *inject a scripted provider event* (e.g., "an injury report changes: player X moves from `probable` to `out`"), or *assert/narrate a checkpoint* (a human-readable line the operator UI can surface — "watch the odds cadence tighten from 15-minute to 5-minute polling here").
- **`demo_provider_data`** — the fixed, scripted responses the `Demo*Adapters` (Section 8) return at each step, keyed by category and step index. This is the scenario's actual content — everything else is orchestration around it.
- **`phase_requirements`** — which real capabilities (per the Section 3 parity table) the scenario depends on, so a scenario referencing not-yet-built Phase 4/5/6 behavior is mechanically identifiable rather than silently broken (this is what lets Section 14's maintenance checklist actually catch drift).

This format is intentionally close to how the existing test suite's fixture-driven scenario tests already work (CONFIRMED pattern across `tests/adapters/*_fixtures.py` and the scenario tests built on them this session) — a scenario is, in effect, a fixture set plus a script, reusing a shape the codebase has already proven out for testing rather than inventing a new one.

---

## 7. Starter Scenarios (Approved Scope — Full Phase 3 Lifecycle)

Per Mac's approval (Decision 4), the starter scenario scope is the **full current real Phase 3 lifecycle**, not a representative subset. The initial Demo environment should eventually exercise every one of the following Phase 3 capabilities (each already CONFIRMED real and shipped, per Section 3's parity table): game/schedule ingestion, game/team/player identity resolution, rosters, depth charts, odds, player props, injuries, weather, news, Master Refresh, DGI assembly, Pregame refresh, Postgame ingestion, final scores, team stats, player stats, bounded reconciliation, malformed-row isolation, and cache behavior. This is a wider build than the original eight-scenario proposal — the scenario list below is organized as coverage of that full lifecycle, not a fixed count.

**Core lifecycle scenarios:**

1. **"Sunday Slate Cadence Ramp."** A 13-game synthetic slate (reusing the scale already validated by this session's own full-fleet load test) advances from T-2h to kickoff; the operator watches Odds/Player Props polling tighten through each tier live. The single most demo-worthy Phase 3 story.
2. **"Breaking Injury News."** Mid-slate, a scripted injury status change (`questionable` → `out`) fires; DGI's `injuries` field updates on the next Master Refresh cycle, visibly.
3. **"Weather Turns."** A scripted forecast update (clear → heavy wind) between two polling steps, visible in DGI's `weather` field.
4. **"Provider Outage, Isolated Failure."** One game's Weather fetch is scripted to fail (mirroring this session's own `test_weather_worker_full_slate_bounded_calls_and_isolation` pattern) while the rest of the slate refreshes normally — demonstrates the row-level isolation pattern this session spent significant effort establishing, live.
5. **"Cross-Provider Identity Resolution."** Two synthetic providers report the same game/team/player under different external IDs; the demo shows them resolving to one internal record — demos the identity-resolution work directly, once there's a UI surface for it (Section 3 flags this as low-priority until Phase 6).
6. **"Game Goes Final → Postgame Stats Land."** A scripted status transition to `final` triggers the Postgame Worker; stat lines appear.
7. **"Roster Move Mid-Week."** A scripted depth-chart change between two polling steps.
8. **"Full Master Refresh, League-Wide."** A wider, less dramatic scenario: run one full Master Refresh cycle across the whole synthetic slate and show the resulting `daily_game_intelligence` rows end-to-end — the "here's literally what Phase 3 produces" scenario.

**Controlled scenarios (approved additions, Decision 4):**

9. **"Normal Game Lifecycle."** One game, start to finish, with no scripted complications — the baseline story every other scenario is a variation on; useful as the first thing shown in any demo.
10. **"Major Pregame Injury."** A star-player injury status change lands close to kickoff, inside the FINAL_RAMP injury-cadence tier (`classify_injury_window`) — distinct from Scenario 2 in that it specifically demonstrates the day-of-week-anchored cadence tightening near kickoff, not just a mid-week change.
11. **"Significant Line Movement."** A scripted odds swing large enough to be visually obvious between two consecutive polling steps — demonstrates the odds snapshot history (append-only) rather than just the latest value.
12. **"Overtime / Final-OT Game."** A scripted game status transition through `final/OT` rather than a regulation `final` — proves the Postgame Worker and schedule-status handling treat this as a normal completion, not an edge case that breaks ingestion.
13. **"Postponed / Rescheduled Game."** A scripted schedule change moves a game's `scheduled_start` mid-slate — demonstrates that window-classification and driver-game selection correctly follow the game to its new time rather than continuing to treat the old kickoff as authoritative.
14. **"Malformed Provider Row, Valid Rows Survive."** A scripted provider response includes one deliberately malformed row (missing/invalid field) alongside otherwise-valid rows in the same batch — demonstrates the row-level isolation pattern (Volume 2 §8, this session's own corrective work) at the data-shape level, distinct from Scenario 4's whole-request-failure case.
15. **"Player-Team Change / Identity Stability."** A scripted mid-week roster move (trade/waiver) for a specific player, followed by a subsequent poll — demonstrates `roster_memberships`' insert-on-change convention and confirms the player's internal identity (`players.id`) stays stable across the team change rather than being treated as a new player.
16. **"Postgame Stat Correction."** A scripted stat line for an already-final game is corrected in a later provider poll — demonstrates the append-only correction-history pattern (a new row per correction, never an overwrite) directly.

**Explicitly NOT built yet — future Demo parity items (do not build early):**

17. **PHASE-4-FUTURE-ONLY — "A Recommendation, Explained."** Do not build until Phase 4/5 are real. Placeholder only: once the agent committee and Explainability Engine exist, this scenario shows one scripted game producing a real (not fabricated) consensus recommendation with a full explainability panel.
18. **PHASE-5-FUTURE-ONLY — "Time Machine Reconstruction."** Do not build until Phase 5's `recommendation_snapshots` exists. Placeholder only: recreate a recommendation from a past scripted moment and show it matches exactly what was shown then — this is meant to demo the product's actual core trust claim (Volume 3 §1, Phase 5's acceptance criteria per the roadmap) once, and only once, that claim is real.

Scenarios 17 and 18 are listed here **specifically so they are not forgotten and not built early** — including them in the design document, marked undoable, is the mechanism that prevents someone from quietly hand-scripting a fake recommendation just because a sales conversation wants one before Phase 4 exists. Per Decision 3: Demo Mode must never simulate a feature the real product has not actually implemented yet — parlay and grading scenarios are Phase 4/5 parity items and are not listed above at all, pending those phases shipping.

---

## 8. Provider / Fixture Strategy

CONFIRMED: the adapter base interface (`app/adapters/base.py`) defines nine category ABCs (`OddsAdapter`, `PlayerPropsAdapter`, `InjuryAdapter`, `WeatherAdapter`, `RosterAdapter`, `ScheduleAdapter`, `NewsAdapter`, `TeamStatsAdapter`, `PlayerStatsAdapter`), each with exactly one abstract fetch method. CONFIRMED: `tests/adapters/fakes.py` already contains one `Fake*Adapter` per category, but its own docstring is explicit about their purpose and limits — they exist "to prove the conformance suite and cache boundary work correctly," return static, hardcoded, single-shape responses, and have no concept of a scenario, a step, or a scripted sequence of changing values over time.

**Recommendation:** a new `Demo*Adapter` family (one per category, same ABCs), living outside the test tree (proposed: `apps/sports-intel-layer/app/demo/adapters.py` or a sibling `demo/` package — exact location an implementation-phase decision), that differs from the existing fakes in one specific way: instead of returning one hardcoded response, each `Demo*Adapter` is constructed with (or looks up) the current scenario step's `demo_provider_data` and returns *that*. Everything else — implementing the same ABC, raising the same `ProviderUnavailableError` family for scripted failure scenarios (reusing Scenario 4's pattern), participating in the same `CachingAdapter` wrapping if desired — is identical to how a real adapter behaves. This is a direct, minimal extension of a pattern the repository has already proven twice (once for unit-test fakes, once for real vendor adapters) rather than a new concept.

**Explicitly not reused as-is:** the existing `tests/adapters/fakes.py` classes themselves should not be imported into demo code — they're a test-tree module scoped to proving conformance, and coupling demo behavior to test infrastructure would mean a future change to make a fake stricter for testing purposes could silently break a demo. Copy the *pattern*, not the *module*.

---

## 9. Persistence Strategy

Two genuinely different things must not be conflated, per the explicit instruction that requested this document:

**Unit/CI fakes** (the existing `tests/adapters/fakes.py` and the broader test suite's in-memory mocking) write nothing durable — they exist entirely within a test process, use `InMemoryCacheBackend` or mocked persistence functions, and leave no trace once the test ends. This is unchanged by anything in this document; Demo Mode does not touch or replace the test suite's own approach.

**The Interactive Demo Environment** (what a human actually watches during a live demo) is different: it needs **real persistence** — real Postgres writes, through the real persistence modules (`app/persistence/daily_game_intelligence.py` and siblings), against **isolated demo data** (Section 4, Option A: a dedicated `demo` Supabase project). This matters because a demo that only holds state in memory can't demonstrate the thing that actually makes Phase 3 real — that `daily_game_intelligence` rows persist, that append-only history accumulates, that a second Master Refresh cycle correctly builds on the first. Faking persistence would mean Demo Mode isn't actually exercising the real system, which is a Rule 1 violation in spirit even if not in the letter (the persistence layer is exactly as much "business logic" as the workers are).

**Practical implication:** the same append-only trigger pattern (`block_snapshot_updates()`) that applies to real `odds_snapshots`/`injury_reports`/etc. should apply identically to the demo project's schema — Demo Mode should get its own copy of the real migrations, not a simplified schema, so that what it demonstrates is structurally the same database the real product runs on. This reinforces the Option A isolation recommendation: a full separate Supabase project can simply run the real migration set; a shared-schema approach (Option B) would need to duplicate every trigger by hand and keep it in sync — a second concrete point in Option A's favor beyond Section 4's original reasoning.

---

## 10. Cache / Redis Approach

Demo Mode should use its own `InMemoryCacheBackend` or a demo-scoped Redis instance/namespace — never the real Redis instance dev/staging/production use, per Rule 2. Given demo scenarios are short, scripted, and operator-driven rather than high-throughput, `InMemoryCacheBackend` (already CONFIRMED to exist and require zero external infrastructure) is the simpler and lower-risk default — ASSUMED, not mandated — with a demo-scoped `RedisCacheBackend` only worth adding later if a specific scenario needs to demonstrate cache-hit/miss behavior itself (Section 3 already flags cache metrics as a low-priority, "under the hood" demo topic, not a headline story).

---

## 11. Dashboard Strategy

CONFIRMED: `apps/frontend` has no dashboard components yet (Phase 6 hasn't started). This section is therefore a strategy statement for *when* Phase 6 lands, not a build plan.

**The dashboard strategy is: there is no separate demo product.** Per Volume 5's already-specified architecture (CONFIRMED: `/chat` as the default landing route, `/dashboard` as the card-view reference library, both consuming typed contracts from the same component library), Demo Mode should render through the exact same Next.js routes and exact same component library real traffic uses, with two additions layered on top rather than a parallel UI: (a) the Rule 4 visual labeling treatment (a persistent banner/badge — exact visual design deferred to whoever builds Phase 6 alongside the Designer Guide), and (b) whatever session/environment switching mechanism lets a demo session point at demo-environment API responses instead of real ones (naturally an extension of Option A's environment separation — a demo session simply talks to the `demo` environment's API Gateway, the same way a staging session talks to staging's). No separate demo frontend codebase, no demo-specific component variants.

---

## 12. Telegram / Notification Compatibility

**Resolved by Mac, 2026-08-19 (Decision 2).** Phase 7 doesn't exist yet — CONFIRMED via roadmap read, still titled "Twilio Integration" in the roadmap and in Volume 5 §7 as of this document's version. That heading is now understood to name the roadmap's originally-scoped SMS channel, not an exclusive commitment: for early Demo/Beta use, **Telegram is the preferred notification channel**, while the underlying notification architecture stays provider-neutral. This is a direction for how Phase 7 (or an earlier notification need) should be *architected*, not a decision this document makes on Phase 7's behalf — the roadmap and Volume 5 §7's own text should be updated to reflect this the next time either is substantively revised, per Change Management (Blueprint first, roadmap second).

**The required pattern, regardless of which channel ships first:**

```
Playbook event
  → notification abstraction/service   (channel-agnostic, mirrors the adapter pattern's own boundary)
      → Telegram                        (initial channel)
      → SMS/Twilio, or other channels    (added later if needed, behind the same abstraction)
```

This is a direct extension of the adapter pattern's own enforcement point (Section 8, Rule 1): exactly as no worker is allowed to import a provider SDK directly, no piece of core business logic (a worker, a future agent, the Recommendation Worker) may depend on Telegram — or any specific channel — directly. Everything upstream of the notification abstraction stays channel-agnostic; only the abstraction's own implementation knows which vendor it's currently calling.

**What this means for Demo Mode specifically:** Demo Mode's own notification compatibility work (Section 19, DEMO-9) targets that same channel-agnostic abstraction, not Telegram's API directly — a `DemoNotificationAdapter` sits behind whichever interface the abstraction defines, exactly like every other `Demo*Adapter` in Section 8, and is swappable for a `TelegramNotificationAdapter` or `TwilioNotificationAdapter` with no change to calling code. **Per Mac's explicit instruction: do not implement Telegram yet, in Demo Mode or anywhere else, unless/until the approved Demo implementation sequence actually reaches DEMO-9.** Building it earlier — even for a demo — would be exactly the kind of early-and-unapproved implementation this document's approval process exists to prevent, and would risk locking in a real Telegram integration before the channel-agnostic abstraction it's supposed to sit behind has itself been designed.

---

## 13. Investor / Sales-Demo Distinction

Two different claims must never be conflated, and Rule 4's labeling exists specifically to keep them apart:

- **Demo proof** ("here is what the system does, scripted, to show the mechanism") — what everything in this document describes.
- **Live performance proof** ("here is how the system actually performed, on real games, with real money-adjacent stakes") — this is what Phase 5's Time Machine reconstruction and Phase 9's Analytics phase are for, and it is **never** something Demo Mode can substitute for. Scenario 9/10's explicit "do not build early" status in Section 7 is the concrete enforcement of this distinction: an investor asking "show me a real recommendation" before Phase 4/5 exist should get an honest "that doesn't exist yet, here's the ingestion pipeline that will feed it" — not a fabricated recommendation dressed up to look real. Silently building Scenario 9/10 early to satisfy a sales conversation would be exactly the kind of undocumented drift between blueprint and reality that CLAUDE.md's "stop and flag" discipline exists to prevent.

---

## 14. Security / Safety Guardrails

- **No production credentials reachable from any demo code path** (Rule 3) — structurally enforced by Demo Mode's provider layer never holding a real HTTP client pointed at a real vendor at all (Section 8), not by a runtime check that could be bypassed.
- **No shared database with dev/staging/production** (Rule 2 / Section 4) — Option A's dedicated Supabase project makes this a network/credential-boundary fact, not a query-discipline convention.
- **No shared Redis instance/namespace** (Section 10).
- **Demo environment variables scoped exactly like the other three environments** (Volume 2 §9's existing per-environment Railway variable pattern, CONFIRMED) — nothing new invented here, just applied to a fourth environment.
- **Rule 4 labeling is mandatory, not optional,** on every surface (UI, chat response, exported/downloaded artifact, any notification that reaches a real device) — a demo artifact that could pass for real output is a trust failure even if the underlying data isolation held perfectly.
- **Demo sessions should be operator-initiated and time-bounded** (ASSUMED — an implementation-phase decision, not fixed here, but flagged as a sane default): a demo environment left running indefinitely and unattended is more attack surface and more risk of accidental real-looking output than one an operator explicitly starts and stops (Section 15).
- **No real user data ever seeds a demo scenario.** Scenario slates (Section 6) must be entirely synthetic (fake team/player names, fake IDs) — never a copy or subset of real production data, even anonymized, since Volume 1's persona/journey content (checked this session, no demo-relevant material found there beyond general positioning) gives no indication real user data would ever be an acceptable demo substrate, and CLAUDE.md's broader data-handling discipline (RLS on every user-data table, append-only enforcement) implies the same caution extends here.

---

## 15. Failure Modes and Prevention

1. **Demo data leaks into a real table.** Prevention: Option A's structural isolation (separate project/credentials) makes this a connection-string-level impossibility rather than a runtime check that could fail silently.
2. **Real provider is accidentally called during a demo.** Prevention: `Demo*Adapters` never construct a real HTTP client; there is no code path from a demo scenario to a real vendor SDK, mirroring Rule 1's adapter-boundary enforcement.
3. **A demo screen is mistaken for real output** (screenshotted, shared, or misread live). Prevention: Rule 4's mandatory, structural labeling — not a convention the operator has to remember to apply per-session.
4. **Demo scenario silently rots as real logic changes underneath it** (e.g., a worker's cadence tiers change in Phase 3 maintenance, but the scripted scenario still narrates the old tiers). Prevention: Section 14's permanent phase-by-phase maintenance checklist, plus each scenario's `phase_requirements` field making dependency on specific real behavior explicit and greppable.
5. **A scenario is built for a phase that doesn't exist yet** (fabricated agent output, fabricated Time Machine reconstruction), quietly normalizing fake data as if it were real. Prevention: Section 7's explicit PHASE-5-FUTURE-ONLY marking and Section 13's investor/sales-demo distinction — a standing rule, not a one-time check.
6. **Demo environment credentials sprawl / a demo-scoped key is provisioned with production-level scope by mistake.** Prevention: follow CLAUDE.md's existing Credentials & Connections discipline exactly — any new demo-environment key request goes through the same "tell Mac which key, when it's needed, where to get it, set as Railway env var, never echo the value back" process already governing dev/staging/production; no new process invented, no shortcut taken because "it's just a demo."
7. **A demo session's synthetic slate collides in shape with the real slate-size assumptions elsewhere in the codebase** (e.g., a hardcoded expectation of exactly 16 real NFL teams somewhere), producing confusing errors that look like real bugs. Prevention: reuse this session's own already-proven synthetic-slate convention (13-game/26-team generated slates, distinctly-fake `H##`/`A##`-style identifiers) rather than inventing new synthetic IDs that might accidentally collide with a real provider's ID scheme.
8. **Demo Mode becomes a second thing people maintain instead of the real product**, absorbing engineering time disproportionate to its value. Prevention: Rule 1 keeps the marginal cost of a new scenario low (it's fixture data plus a script, not new logic), and Section 16's phased sequence explicitly gates further demo investment behind real phases actually shipping, not ahead of them.
9. **An operator forgets to stop/reset a running demo session**, leaving synthetic data or a stale scenario state visible or consuming resources indefinitely. Prevention: Section 16's lifecycle makes session start/stop/reset explicit operator actions with a defined end state, not an implicit "just leave it running" assumption.
10. **A future Telegram/Twilio integration (Section 12) accidentally delivers a demo notification to a real phone number.** Prevention: the same adapter-boundary reasoning as failure mode 2 — a demo notification adapter should have no code path to a real delivery credential, and any demo notification content should carry Rule 4 labeling even in the (should-never-happen) case it is delivered.

---

## 16. Demo Lifecycle (Operator Actions)

Proposed, ASSUMED (implementation-phase decision, sketched here for completeness):

1. **Select a scenario** from the library defined in Section 7.
2. **Start a session** — provisions/resets the demo environment's data to the scenario's clean starting state (drops and reseeds demo-scoped tables, or starts from a known-good snapshot — implementation detail).
3. **Advance the session** through the scenario's steps, either manually (operator clicks "next" narrating live) or on a timer (Section 5's Option 4 compressed-playback mode, once built).
4. **Pause / rewind** — since the clock is entirely virtual and operator-controlled (Section 5), rewinding to an earlier step should be structurally straightforward (recompute `virtual_now`, re-run the relevant workers against it) rather than needing special-cased "undo" logic.
5. **End the session** — resets demo data back to a clean state, so the next operator starts from the same known baseline rather than inheriting the previous session's scripted history.

---

## 17. Testing Strategy

At minimum, twelve categories, each mapped to a concrete concern this document raises:

1. **Adapter conformance** — every `Demo*Adapter` passes the same conformance suite real adapters already do (CONFIRMED pattern exists — this session's own work extended it repeatedly for each new real adapter).
2. **Scenario schema validation** — every checked-in scenario file conforms to Section 6's format, catching malformed scenarios before they run.
3. **Clock-injection correctness** — a scenario's `virtual_now` sequence produces the exact `Window`/`InjuryWindow` classifications the scenario's narration claims it will (a direct, automatable check against the real `classify_window`/`classify_injury_window` functions).
4. **Isolation boundary tests** — prove a demo-environment write cannot reach a dev/staging/production table (schema/connection-level test, not just a code-review assertion).
5. **No-real-credential tests** — prove `Demo*Adapter` construction never requires, reads, or references a real provider API key (e.g., assert no `os.environ` lookup for a real vendor's key name anywhere in the demo adapter module).
6. **Labeling presence tests** — once Phase 6 exists, an automated check that every demo-rendered screen/component includes the Rule 4 label.
7. **Persistence parity tests** — a demo scenario's Master Refresh cycle produces a `daily_game_intelligence` row with the same shape/invariants the real pipeline's own tests already assert (reuse, don't reinvent, the existing DGI shape tests).
8. **Row-level isolation scenario tests** — Scenario 4 (partial-failure slate) produces exactly the same "partial status, N failures isolated" outcome this session's own full-fleet load tests already established for real workers.
9. **Lifecycle tests** — start/advance/rewind/end a session and confirm the demo environment returns to a clean, deterministic starting state.
10. **Phase-requirement guard tests** — a scenario marked as depending on a not-yet-built phase capability (Section 6's `phase_requirements` field) fails fast/loudly if accidentally invoked, rather than silently rendering broken or fabricated output.
11. **Regression-safety tests** — running the full real test suite with demo code present produces no change in existing pass/fail counts (demo code is purely additive, never modifies real code paths — a direct test of Rule 1).
12. **Documentation-sync tests** (lightweight, possibly manual rather than automated) — the Demo Parity Status table (Section 3) is checked for staleness against the roadmap's phase-closure state as part of Section 18's standing maintenance process.

---

## 18. Phase-by-Phase Maintenance — Permanent Standing Checklist

This is not a one-time task. Add to the phase-closure process (alongside CLAUDE.md's existing "present a checklist mapping each acceptance criterion... explicitly ask Mac to confirm" requirement) the following, every time a phase closes:

- [ ] Update the Demo Parity Status table (Section 3) to reflect the newly-real capability.
- [ ] Determine whether any of the phase's newly-real behavior warrants a new starter scenario, or whether an existing "future-only" scenario (Section 7, Scenario 9/10 pattern) can now be promoted to buildable.
- [ ] Confirm no existing demo scenario's narration/assertions have silently gone stale against the phase's actual shipped behavior (Failure Mode 4).
- [ ] If the phase changed any adapter interface shape (Volume 2 §8), confirm the corresponding `Demo*Adapter` was updated in lockstep — not left implementing a now-outdated ABC.
- [ ] Log the update in this document's own version history the same way CHANGELOG.md tracks blueprint changes (Reason / Decision / Alternatives Considered / Expected Impact), so Demo Mode's own drift-prevention has the same discipline the rest of the blueprint already has.

---

## 19. Approved Implementation Sequence (DEMO-1 through DEMO-9)

Approved by Mac 2026-08-19 (Decision 5). Labeled `DEMO-N` to match the repository's existing phase-substep convention (e.g. `3E-1`…`3E-4`, `3F-4`, `3F-5`) rather than a standalone numbering scheme — Demo Mode is a cross-cutting initiative gated by the real roadmap's phases, not a roadmap phase of its own, so its substeps are named the same way this session's own sub-phase work has been throughout Phase 3.

1. **DEMO-1 — Isolation foundation. STATUS: BUILT (2026-08-19).** Provision the `demo` Railway environment + Supabase project (Section 4, Option A), including the full real migration set (Section 9) — nothing else can safely proceed without this existing, since every later step either writes demo data or needs somewhere isolated to write it. **Do not skip this step** — explicitly called out in Decision 5 as non-skippable regardless of how much faster it might feel to prototype DEMO-2/3 against a shared database first. This document's companion execution plan (delivered separately, per Mac's request) scopes DEMO-1 in full before any provisioning happens. Closed with live Railway proof (deployment, clean startup log) and live Supabase proof (migration parity, zero operational data) — see `PROGRESS.md`'s 2026-08-19 entries for the full evidence trail.
2. **DEMO-2 — Demo provider-adapter family. STATUS: BUILT (2026-08-19), NOT YET WIRED.** (Section 8) — the nine category adapters (`app/demo/adapters.py`), conformance-suite-tested (Section 17 #1) exactly like real adapters. Application code and tests only — no worker/Master Refresh/persistence call site references these adapters yet, no scenario runner exists to drive them, and nothing was deployed or wired into the live `demo` Railway service for this step. That begins at DEMO-3.
3. **DEMO-3 — Virtual clock / scenario runner. STATUS: BUILT (2026-08-20), NOT YET LIVE-PROVEN.** (Section 5, Section 6) — the orchestration layer that drives real worker entrypoints via their existing `now`/`today` override parameters. `app/demo/scenario.py` (schema), `app/demo/runner.py` (`ScenarioRunner`), `app/demo/reset.py` (FK-safe operational reset + its own independent destructive-operation guard), `app/demo/scenarios/minimal_pregame_to_postgame.json` (the one approved minimal scenario). Required, and received, an additive adapter-injection seam on 8 real worker/orchestration files (optional `*_adapter=` parameters, `None` default preserves exact prior behavior) — see `PROGRESS.md`'s 2026-08-20 entry for the full seam/testing trail, including two genuine pre-existing bugs (one in DEMO-2's own `DemoOddsAdapter`, one in real production `app/persistence/daily_game_intelligence.py`) discovered and fixed only once this step actually exercised the full pipeline end-to-end. Proven against an in-memory fake Supabase (87 tests, full regression 561/561) — **not yet proven against the live `theplaybook-demo` Supabase project**, since that requires `SUPABASE_SERVICE_ROLE_KEY` for `demo`/`sports-intel-layer`, not yet requested from Mac.
4. **DEMO-4 — Phase 3 scenario library** (Section 7) — the full approved lifecycle-coverage scenario set (core lifecycle + controlled scenarios), built and tested (Section 17) against the real Master Refresh/worker pipeline.
5. **DEMO-5 — Operator lifecycle tooling** (Section 16) — session start/advance/rewind/end, likely a minimal internal-only interface (CLI or bare API endpoints) until Phase 6 gives it a real UI to live in.
6. **DEMO-6 — Shared dashboard integration** — Rule 4 labeling plus the dashboard strategy (Section 10), built when Phase 6's frontend/UX components actually exist; not startable earlier no matter how ready the rest of Demo Mode is.
7. **DEMO-7 — Phase 4 scenario parity** — Scenario 17 (agent/explainability demo), unlocked only once Phase 4 ships for real, per the Section 18 maintenance process.
8. **DEMO-8 — Phase 5 / Time Machine scenario parity** — Scenario 18 (Time Machine reconstruction demo), unlocked only once Phase 5 ships `recommendation_snapshots` for real.
9. **DEMO-9 — Telegram notification compatibility** — built against the channel-agnostic notification abstraction described in Section 12, once that abstraction and a real notification need exist. Explicitly not started before this step is reached, per Decision 2.

DEMO-1 through DEMO-5 are the only steps that could reasonably start soon, since they depend only on Phase 3 (already real). DEMO-6 through DEMO-9 are hard-gated on later phases per the roadmap's own dependency chain, exactly mirroring CLAUDE.md's phase-gating rule — Demo Mode does not get to skip ahead of the phases it's demonstrating. **Approval of this sequence is not approval to begin executing it.** Per Mac's instruction, a focused execution plan for DEMO-1 specifically is required and must be separately approved before any provisioning occurs; each subsequent DEMO-N step is expected to get the same treatment in turn.

---

## 20. Documentation Cross-References — Registration Record

Per Mac's approval (Document Registration section of the 2026-08-19 decision), this document is now registered as an authoritative Blueprint/supporting architecture document. What changed, file by file:

- **`docs/blueprint/README.md`** — added a Documentation Index row for this document, and corrected the two stale "Current Versions" rows this session had already found (Volume 2 shown as v4.0, actually v4.16; Volume 3 shown as v4.0, actually v4.12.1) since the correction was straightforward, directly verifiable against each volume's own header, and unrelated behavior was not affected. Volumes 1/4/5, the roadmap, and both amendments documents were checked against their own headers too and found to already match the table (v3.0/v4.0/v4.0/v4.0/v2.0/v3.0 respectively) — left untouched, no correction needed there.
- **`engineering-roadmap-build-order.md`** — a single pointer added at the close of Phase 3's Testing Requirements, where Demo Mode's DEMO-4 scenario library first becomes buildable (per Section 19) — no new phase, no renumbering, minimal footprint per Mac's "do not create broad documentation churn" instruction.
- **`CLAUDE.md`** — no change. Unchanged from the original assessment: CLAUDE.md's existing rules already govern Demo Mode's eventual implementation without modification.
- **`PROGRESS.md`** — added an entry recording this document's approval and the five decisions above.
- **`CHANGELOG.md`** — still not touched, per the original reasoning: no architectural/schema/deployed-behavior change has happened yet. The DEMO-1 execution plan (Section 19, requested separately) is the next point at which a real decision requiring a CHANGELOG entry is likely to occur.
