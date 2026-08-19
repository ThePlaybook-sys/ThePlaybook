# Demo / Simulation Environment — Architecture & Design

**Status:** PROPOSED — DESIGN ONLY. No part of this document has been implemented. This is a planning artifact, not a build log.

**Version:** v1.0 (initial draft, 2026-08-19)

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

## 7. Ten Starter Scenarios

Eight are buildable against Phase 3 as it exists today. Two are explicitly Phase-5-future-only and must not be built early, per the phase-gating rule.

1. **"Sunday Slate Cadence Ramp."** A 13-game synthetic slate (reusing the scale already validated by this session's own full-fleet load test) advances from T-2h to kickoff; the operator watches Odds/Player Props polling tighten through each tier live. The single most demo-worthy Phase 3 story.
2. **"Breaking Injury News."** Mid-slate, a scripted injury status change (`questionable` → `out`) fires; DGI's `injuries` field updates on the next Master Refresh cycle, visibly.
3. **"Weather Turns."** A scripted forecast update (clear → heavy wind) between two polling steps, visible in DGI's `weather` field.
4. **"Provider Outage, Isolated Failure."** One game's Weather fetch is scripted to fail (mirroring this session's own `test_weather_worker_full_slate_bounded_calls_and_isolation` pattern) while the rest of the slate refreshes normally — demonstrates the row-level isolation pattern this session spent significant effort establishing, live.
5. **"Cross-Provider Identity Resolution."** Two synthetic providers report the same game/team/player under different external IDs; the demo shows them resolving to one internal record — demos the identity-resolution work directly, once there's a UI surface for it (Section 3 flags this as low-priority until Phase 6).
6. **"Game Goes Final → Postgame Stats Land."** A scripted status transition to `final` triggers the Postgame Worker; stat lines appear.
7. **"Roster Move Mid-Week."** A scripted depth-chart change between two polling steps.
8. **"Full Master Refresh, League-Wide."** A wider, less dramatic scenario: run one full Master Refresh cycle across the whole synthetic slate and show the resulting `daily_game_intelligence` rows end-to-end — the "here's literally what Phase 3 produces" scenario.
9. **PHASE-5-FUTURE-ONLY — "A Recommendation, Explained."** Do not build until Phase 4/5 are real. Placeholder only: once the agent committee and Explainability Engine exist, this scenario shows one scripted game producing a real (not fabricated) consensus recommendation with a full explainability panel.
10. **PHASE-5-FUTURE-ONLY — "Time Machine Reconstruction."** Do not build until Phase 5's `recommendation_snapshots` exists. Placeholder only: recreate a recommendation from a past scripted moment and show it matches exactly what was shown then — this is meant to demo the product's actual core trust claim (Volume 3 §1, Phase 5's acceptance criteria per the roadmap) once, and only once, that claim is real.

Scenarios 9 and 10 are listed here **specifically so they are not forgotten and not built early** — including them in the design document, marked undoable, is the mechanism that prevents someone from quietly hand-scripting a fake recommendation just because a sales conversation wants one before Phase 4 exists.

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

Phase 7 (Twilio) doesn't exist yet — CONFIRMED via roadmap read. This section is a compatibility note for that future phase, not a build. The user's own instruction referenced "Telegram" specifically; note for the record: the blueprint as currently written (Volume 2, Volume 5 §7 heading "Twilio Integration") specifies **Twilio**, not Telegram, as the SMS/notification vendor — **flagging this as a discrepancy between the request and repository reality** rather than silently substituting one for the other, per this document's own stated method. If Telegram is intended as an actual future channel in addition to or instead of Twilio, that is a blueprint question for Mac to resolve when Phase 7 is scoped, not something this document should decide unilaterally. Whichever vendor Phase 7 ultimately uses, the same Rule 1/Rule 3 logic applies directly: a demo notification must go through a `Demo`-flavored adapter behind whatever notification-adapter interface Phase 7 defines, never a real Twilio (or Telegram) credential, and must be clearly labeled as a demo message if it's ever actually delivered to a real device rather than just logged/rendered in the demo UI.

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

## 19. Proposed Implementation Sequence

Derived from the repository's actual current state (Section 3's parity table) rather than the illustrative `DEMO-0` through `DEMO-6` labels given only as an example in the originating instruction — the real dependency order is:

1. **Isolation infrastructure first.** Provision the `demo` Railway environment + Supabase project (Section 4, Option A), including the full real migration set (Section 9) — nothing else can safely proceed without this existing, since every later step either writes demo data or needs somewhere isolated to write it.
2. **`Demo*Adapter` family** (Section 8) — the nine category adapters, conformance-suite-tested (Section 17 #1) exactly like real adapters.
3. **Virtual clock + scenario runner** (Section 5, Section 6) — the orchestration layer that drives real worker entrypoints via their existing `now`/`today` override parameters.
4. **Scenarios 1–8** (Section 7) — the eight Phase-3-buildable starter scenarios, built and tested (Section 17) against the real Master Refresh/worker pipeline.
5. **Operator lifecycle tooling** (Section 16) — session start/advance/rewind/end, likely a minimal internal-only interface (CLI or bare API endpoints) until Phase 6 gives it a real UI to live in.
6. **Rule 4 labeling + dashboard integration** — blocked on Phase 6 existing at all; not startable earlier no matter how ready the rest of Demo Mode is.
7. **Scenario 9 (agent/explainability demo)** — unlocked only once Phase 4 ships for real.
8. **Scenario 10 (Time Machine reconstruction demo)** — unlocked only once Phase 5 ships `recommendation_snapshots` for real.
9. **Notification/Twilio-or-Telegram demo compatibility** (Section 12) — unlocked only once Phase 7 exists, and only once the Twilio-vs-Telegram discrepancy flagged in Section 12 is resolved by Mac.

Steps 1–5 are the only ones that could reasonably start soon, since they depend only on Phase 3 (already real). Steps 6–9 are hard-gated on later phases per the roadmap's own dependency chain, exactly mirroring CLAUDE.md's phase-gating rule — Demo Mode does not get to skip ahead of the phases it's demonstrating.

---

## 20. Documentation Cross-References — What Else Needs Updating

Per the instruction's explicit ask to determine (but not unilaterally execute beyond registering this document's existence): the following files reference or list documentation in a way that should plausibly mention this new document, and are flagged here rather than edited:

- **`docs/blueprint/README.md`** — its "Reserved for Future Documents" list (CONFIRMED, read this session) does not include a Demo Mode category, and this new document doesn't cleanly fit any of the six placeholders already listed (API Reference, Developer Guide, Operations Manual, Deployment Runbook, Disaster Recovery, Security Handbook). It likely needs a new entry — either added to that reserved list (if treated as not-yet-authoritative) or added directly to the "Current Versions" table (if treated as authoritative once approved). **Separately and independently of this document:** that same "Current Versions" table was already found to be stale (shows Volume 2/3 at v4.0 against their real current v4.16/v4.12.1) — a pre-existing gap unrelated to Demo Mode, flagged for Mac's awareness but out of scope to fix as part of this task.
- **`engineering-roadmap-build-order.md`** — currently has no Demo Mode phase or mention. Given Section 19's sequencing is gated by the existing phases rather than being its own phase, it may not need a new numbered phase at all — but the roadmap's own text could reasonably gain a pointer to this document near Phase 3's close (where Demo Mode first becomes buildable) and near Phase 6's close (where the dashboard-labeling work unlocks). A decision for Mac.
- **`CLAUDE.md`** — no change needed. CLAUDE.md's existing rules (phase-gating, credentials discipline, blueprint-vs-reality flagging) already govern Demo Mode's eventual implementation without modification; this document was written to comply with those rules, not to add new ones to that file.
- **`PROGRESS.md`** — should get an entry noting this design document now exists, once Mac confirms it as accepted (consistent with how every other piece of work this session was logged there).
- **`CHANGELOG.md`** — arguably not yet, since nothing architectural has changed (no code, no schema, no deployed behavior) — a design document's creation is not itself a PATCH/MINOR/MAJOR blueprint change under the versioning scheme's own definition (CONFIRMED, that scheme keys off actual decisions affecting the volumes, not documents that reference them). A CHANGELOG entry would be more appropriate at the point Demo Mode's actual implementation begins and produces a real decision to log.

None of the above have been edited. This section is a report, per the instruction's own framing ("do not make unrelated edits — report if broader changes are needed").
