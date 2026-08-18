# The Playbook — Blueprint Changelog

This file is the single source of truth for how the blueprint has evolved. Every volume carries a version header that must match the latest entry here for that volume. If a volume's header and this changelog ever disagree, this changelog wins.

## Version Scheme

| Bump | Example | Trigger |
|---|---|---|
| **PATCH** | v1.0 → v1.0.1 | Wording, formatting, clarity fixes. No architectural meaning changes. Doesn't require checking other volumes. |
| **MINOR** | v1.0 → v1.1 | A new component, persona, agent, or decision added/refined *within one volume* that doesn't contradict the others. |
| **MAJOR** | v1.x → v2.0 | A decision that ripples across volumes — e.g., changing the pricing model (hits Vol 1, 2, 3), swapping the backend framework (hits Vol 2, 3), or restructuring the AI Orchestrator (hits Vol 2, 4). Requires a cross-volume consistency check before closing the version out. |

Every entry below follows the same four-field format from the original spec: **Reason → Decision Changed → Alternatives Considered → Expected Impact.**

---

## v1.0 — 2026-08-05

**Volumes affected:** Volume 1 (Business, Product Vision, UX, Pricing, Customer Journeys)

**Reason:** Initial blueprint generation from the master architecture prompt. No prior version exists.

**Decision:** Established the foundational business model, target personas, pricing tiers, onboarding flow, and success metrics for The Playbook.

**Alternatives considered:** N/A — baseline version.

**Expected impact:** Volumes 2–5 will inherit and must stay consistent with:
- The three user personas defined here
- The subscription tier structure and what each tier unlocks
- The "No Bet Today" philosophy as a non-negotiable product principle
- The success metrics hierarchy (ROI/EV/CLV over win %)

Any future change to pricing tiers, personas, or the core philosophy triggers a MAJOR version bump and requires re-checking Volumes 2 (system design), 3 (database — subscription tables), 4 (AI confidence thresholds tied to tier), and 5 (dashboard access by tier).

---

## v1.0 — 2026-08-05 (cont.)

**Volumes affected:** Volume 2 (System Architecture, Backend Design, Railway Deployment, API Strategy, AI Orchestration, DevOps)

**Reason:** Second volume of the initial blueprint pass. Master prompt required a justified backend framework choice rather than an assumed one.

**Decision:** FastAPI (Python) selected over Node.js — reasoning centers on the AI/ML-heavy nature of the Orchestrator and Continuous Learning Engine (Volume 4) being Python-native problems, avoiding a two-language split later. Also established: 4-service Railway deployment shape (API Gateway, AI Orchestrator, Sports Intelligence Layer, Background Workers), strict provider-adapter pattern for all external sports/odds data, async parallel agent fan-out, and confidence-gated "No Bet Today" logic living at the Orchestrator layer.

**Alternatives considered:** Node.js backend (rejected — would require a second Python service for ML/calibration work anyway). Raw AWS/GCP over Railway at launch (rejected for now — Railway reduces DevOps overhead for a small team; flagged as a future MAJOR-version reconsideration if scale outgrows it, since containerization keeps that migration path open).

**Expected impact:**
- Volume 3 (Database) must define the model-routing table referenced in Section 7, and RLS/security policies referenced in Section 10.
- Volume 4 (AI Intelligence) owns the full agent committee spec and must finalize the confidence variance threshold flagged in Section 7 as an open decision.
- Volume 5 (Frontend/UX) must align on data contracts for the System Health Dashboard.
- This is additive, not a break from Volume 1 — no MAJOR bump triggered. Framework/hosting choices here don't touch pricing, personas, or product principles.

---

## v1.0 — 2026-08-05 (cont.)

**Volumes affected:** Volume 3 (Database Architecture)

**Reason:** Third volume of the initial blueprint pass. Resolves two items Volume 2 flagged as open: the model-routing table schema and RLS enforcement of tier gating.

**Decision:** Full schema built around three non-negotiable patterns: (1) snapshot/frozen-copy tables anywhere Time Machine reproducibility matters (`recommendation_agent_outputs.weight_applied`, `recommendation_snapshots`, append-only `odds_snapshots`), (2) RLS-enforced tier gating on `recommendations` so subscription limits can't be bypassed by calling the API directly, and (3) three fully separate performance-attribution tables (`ai_performance`, `projected_user_performance`, `verified_user_performance`) rather than one table with a type column, per the master spec's explicit "never mix these" requirement. `model_routing_rules` table added as data, not code, satisfying Volume 2's "swap models without redesign" goal.

**Alternatives considered:** Single `performance` table with a `type` enum (rejected — too easy to accidentally query across projected/verified/AI data and misrepresent results). Referencing live `agents.current_weight` from historical agent outputs instead of freezing it (rejected — would silently rewrite history on Time Machine reconstruction).

**Expected impact:**
- Volume 4 (AI Intelligence) must design the adaptive weighting algorithm against the `agents` / `agent_performance_scores` shape defined here, including respecting the required `sample_size` guardrail against overfitting.
- Volume 4/5 jointly own finalizing the `conversations` / `conversation_messages` schema, flagged here as incomplete.
- Volume 5 (Frontend) should build dashboard queries assuming RLS is the enforcement layer for tier gating — no need to duplicate that check client-side, only reflect it in UI state.
- No MAJOR bump — this volume implements Volume 1/2 decisions, doesn't change them.

---

## v1.0 — 2026-08-05 (cont.)

**Volumes affected:** Volume 4 (AI Intelligence Architecture)

**Reason:** Fourth volume of the initial blueprint pass — the largest and highest-risk volume. Resolves the confidence variance threshold flagged in Volume 2 §7 and the agent weighting algorithm + conversation schema flagged in Volume 3 §13.

**Decision:** Full 21-agent committee specified across four functional groups (Context/Data, Matchup/Form, Market, Decision/Advisory). Consensus Engine uses a weighted-average confidence formula with a directional-agreement penalty. "No Bet Today" hard floor set at aggregate_confidence < 0.55 (launch default, explicitly flagged as tunable pending backtesting). Elite-tier second-pass reconciliation triggers on agreement_variance > 0.25, giving concrete technical meaning to Volume 1's "priority agent compute" pricing language. Adaptive weighting algorithm capped at ±10% per update with a 200-recommendation minimum sample size and 90-day rolling window, directly enforcing the master spec's anti-overfitting instruction as a hard limit rather than a guideline. Risk Manager and Bankroll Coach kept as separate agents from Expected Value, since "is this bet good" and "is this bet good for this specific user" are different questions that Volume 1's personalization promise requires keeping distinct and auditable.

**Alternatives considered:** Collapsing Risk Manager/Bankroll Coach into the Expected Value Agent (rejected — would blur objective EV from personalized fit). Deactivating chronically underperforming agents entirely instead of weighting toward zero (rejected — destroys historical record needed for postgame reviews and any future re-evaluation).

**Expected impact:**
- Volume 5 (Frontend/UX) must design around the explainability question-to-source mapping in Section 8, and build two distinct empty states (No Bet Today vs. Bankroll Preservation) rather than one generic empty state.
- The 0.55 confidence threshold and ±10% max weight change are launch defaults pending pre-launch backtesting (Section 11) — expect a MINOR version bump to this volume once real backtesting numbers replace them.
- Pre-launch backtesting against a full historical NFL season is now a scoped milestone, not a footnote — should be reflected in any future project timeline/roadmap document.
- No MAJOR bump — this volume implements and specifies logic within the structure Volumes 1–3 already established.

---

## v1.0 — 2026-08-05 (cont.)

**Volumes affected:** Volume 5 (Frontend & UX Architecture) — final volume of the initial blueprint pass

**Reason:** Closes the loop between the companion Designer Onboarding Guide (visual/non-technical) and the engineering layer. Resolves the notification schema gap flagged in Volume 3 §13.

**Decision:** Next.js App Router with Server Components for static content, Client Components + React Query for stateful data, Supabase Realtime reserved specifically for recommendation status changes and live game updates (not used as a default pattern everywhere). Design tokens implemented as CSS custom properties feeding Tailwind config, so the designer's Figma decisions (Designer Guide) have exactly one source of truth in code. New component identified and added: **Explainability Panel** — not in the original Designer Guide component list, required to implement Volume 4 §8's nine-question explainability mapping. Notifications table added, with SMS reserved for time-sensitive events only to avoid channel fatigue, and Twilio conversation flow routed through the same NL Engine intent classification as the web chat interface rather than a separate SMS-only logic path.

**Alternatives considered:** A global state management library (Redux/Zustand) — rejected as unnecessary complexity at current scale given React Query already handles server state. Blending AI/projected/verified performance into shared chart components — rejected, mirrors the Volume 3 database-level separation for the same misrepresentation risk.

**Expected impact:**
- Designer needs to be looped in on the new Explainability Panel component before final screen designs.
- Full cross-volume consistency check performed (Section 9) — no contradictions found across all five volumes; no MAJOR bump triggered.
- Two items remain genuinely open project-wide: pre-launch backtesting (Volume 4) and legal/compliance review (Volume 1) — neither blocks the blueprint itself, both block public launch.

## v1.0 — 2026-08-05 (cont.)

**Document affected:** Engineering Roadmap & Build Order (companion document, not a Volume — describes build sequence, not system design)

**Reason:** Requested after all five volumes were complete, to translate the finished specification into an actual build order with checkable completion criteria per phase, since a 5-volume spec doesn't by itself tell an engineering team what to build first or how to know a phase is really done.

**Decision:** 12-phase sequence (Phase 0–11), strictly sequential through Phase 6 (each layer is load-bearing for the next: repo/CI → database → auth → sports data → AI orchestrator → recommendation pipeline → frontend), with Phases 7–9 (Twilio, OCR, Analytics) parallelized only after Phase 6 is stable. Every phase cites the specific volume/section it implements, and every phase's acceptance criteria are written as checkable conditions rather than vague completion language. Phase 5's acceptance criteria explicitly names the Time Machine reconstruction test as the single most important test in the entire roadmap, since it's the mechanical proof of the whole product's core trust claim.

**Alternatives considered:** A less strict phase ordering allowing earlier frontend work in parallel with backend (rejected — Phase 6 explicitly depends on Phase 5 producing real recommendation data, and building UI against placeholder data shapes risked exactly the kind of drift this whole versioned-blueprint exercise was meant to prevent).

**Expected impact:**
- This document is designed to be checked, not just read: a MAJOR version bump to any Volume should trigger a re-check of whichever phase already implements the changed area, since a build might need to reopen a "completed" phase.
- Phase 10 (Beta) is explicitly named as the point where Volume 4's launch-default confidence threshold (0.55) and weight-change cap (±10%) get their real-world check — expect the MINOR bump to Volume 4 anticipated in that volume's changelog entry to actually happen during or after this phase, not before.
- Legal/compliance review (open since Volume 1 §10) now has a concrete deadline: end of Phase 10, before Phase 11 can start.

This document does not change any Volume's version number — it's a build-sequencing layer on top of an already-complete v1.0 blueprint.

---

## v2.0 — 2026-08-05 — MAJOR

**Volumes affected:** All five volumes, plus the Engineering Roadmap & Build Order. First MAJOR bump of the project.

**Reason:** External architecture review (9.8/10 overall score) proposed 25 improvements against the completed v1.0 blueprint. Triaged rather than adopted wholesale — see `v2.0-amendments-architecture-review.md` for the full point-by-point assessment, including what was declined and why.

**Decision (accepted, summarized):**
- **Volume 1:** Referral code field added; Public Transparency Portal flagged as a post-MLP feature.
- **Volume 2:** Scoped internal event system (Postgres LISTEN/NOTIFY at MLP stage, not a full message-broker architecture) wired to five events tied to recommendation lifecycle and agent weight changes; AI abuse protection (prompt injection filtering, SMS flood protection, Orchestrator circuit breakers); disaster recovery targets (RTO/RPO); per-component observability expansion.
- **Volume 3:** New tables — `feature_flags`, `prompt_registry`, `model_registry`, `recommendation_costs`, expanded `audit_log`. New columns — AI versioning fields (`ai_version`, `prompt_version`, `agent_version`, `consensus_version`, `weight_version`) on `recommendations`; soft-delete columns on key tables. UUIDv7 recommended for the three highest-insert append-only tables.
- **Volume 4:** Committee expanded to 22 agents — Meta Agent added as a post-consensus reviewer whose `confidence_adjustment` can only ever reduce aggregate confidence, never increase it, preserving the anti-overfitting guardrails already in place. Shared agent output contract extended with `evidence_classification` (data_backed / inference / assumption), discounting assumption-heavy findings in the consensus weighting.
- **Volume 5:** AI Transparency Meter (extends Explainability Panel with evidence strength, agent agreement, and data quality dimensions) and Recommendation Timeline (powered directly by the new event system) added as components.
- **Roadmap:** Phases 1, 4, 5, and 6 gained new scope items; no phase needed to be reopened since this review landed before any phase began building — exactly the scenario the "no code before the blueprint is complete" discipline was meant to protect against.

**Alternatives considered:**
- Full enterprise event-driven architecture connecting every service (the review's literal proposal) — rejected in favor of a scoped version. Reasoning: the blueprint's own MLP strategy argues against front-loading infrastructure complexity that doesn't have proven consumers yet; a message broker and event schema versioning system is real operational weight for a small team's first release. The scoped version delivers the two features that actually need it (decoupled notifications, the Recommendation Timeline) without the full footprint.
- Knowledge Graph — deferred, not rejected outright, but no near-term schema action; existing relational + jsonb design already covers agent committee needs.
- AI Notebook — declined as new backend architecture; it's functionally already the combination of `recommendation_snapshots` + `explainability_payloads` + `postgame_reviews`, so any further work belongs in Volume 5 as a UI view, not a new engine.
- Separate ADR system — declined; this changelog's four-field format already serves that function.

**Expected impact:**
- This is a genuine MAJOR bump — schema changes in Volume 3 affect what Volume 4's Orchestrator reads/writes and what Volume 5's components render, touching all five volumes' consistency simultaneously, which is exactly the ripple pattern the MAJOR-bump definition at the top of this file was written for.
- Phase 1 of the roadmap now has a larger table list to complete before its acceptance criteria are met.
- Phase 4's "all agents built" milestone now means 22, not 21.
- No volume's core product principles, pricing, or personas changed — this bump is architectural/operational depth, not a reversal of any prior decision.

**Full technical detail:** `v2.0-amendments-architecture-review.md`

---

## v2.0.1 — 2026-08-05 — PATCH

**Volume affected:** Volume 4 (AI Intelligence Architecture) only

**Reason:** Caught by Claude Code during repo setup, correctly following CLAUDE.md's "blueprint vs. reality" protocol rather than silently patching. The v2.0 entry above declared Volume 4's Meta Agent and `evidence_classification` additions as done, and Volume 4's own header was bumped to v2.0 — but the file's body was never actually edited to match. Section 2 still said "Twenty-one independent agents," §2.1's contract had no `evidence_classification` field, there was no §2.6 Meta Agent entry, §4.1's consensus math didn't account for either addition, and the closing line still cited v1.0. The header made a promise the body didn't keep — an internal inconsistency, not a new decision.

**Decision:** No architectural change. Volume 4's body corrected to match what v2.0 already declared: Section 2 now states 22 agents (21 fan-out + Meta Agent); §2.1's contract includes `evidence_classification`; new §2.6 fully specifies the Meta Agent; §3.1's execution flow inserts the Meta Agent as step 8, after Consensus and before Explainability; §4.1 documents both the evidence-classification discount (0.5× weight for `assumption`-classified findings, per-calculation only, not a permanent weight change) and the Meta Agent's `confidence_adjustment` producing a `final_aggregate_confidence` that feeds §4.2's threshold; the closing line now correctly reads v2.0.

**Alternatives considered:** N/A — this is a consistency fix, not a design decision. The only "alternative" would have been leaving the inconsistency in place, which isn't a real option under the versioning discipline this project already committed to.

**Expected impact:** None beyond Volume 4 itself — no other volume referenced the parts of Volume 4's body that were stale. This is a PATCH per the versioning scheme (wording/consistency fix, no architectural meaning change) since the actual decision was already logged in v2.0; this entry just closes the gap between that decision and the document that was supposed to reflect it. Corrected file needs to replace the one already committed to the repo — see note below.

**Process note:** This is exactly the scenario CLAUDE.md's "blueprint vs. reality" section anticipated, just one step earlier than expected — during initial repo setup rather than mid-build. Flagging and logging it rather than quietly re-uploading a fixed file is the correct behavior and should continue for anything else caught during setup.

---

## v2.0.2 — 2026-08-05 — PATCH

**Volumes affected:** Volumes 1, 2, 3, and 5 (same drift pattern as v2.0.1), plus one residual fix to Volume 4.

**Reason:** Same header-body drift as v2.0.1, caught the same way — Claude Code flagging each volume during repo setup rather than assuming a v2.0 header meant the body was actually updated. Volumes 1, 2, 3, and 5 all had the identical shape of problem: a `**v2.0 note:**` line in the header pointing to `v2.0-amendments-architecture-review.md`, with no corresponding content actually written into the volume's own body, and closing lines still citing v1.0. Separately, Claude Code also caught a smaller residual in Volume 4: Section 9's decision logic still referenced `aggregate_confidence` instead of `final_aggregate_confidence`, missed by the v2.0.1 fix because that section wasn't touched by the Meta Agent integration work.

**Decision:** No architectural changes — all four volumes' bodies corrected to match what was already decided and logged in the v2.0 entry above:
- **Volume 1:** New §9.1 "Referral & Public Trust Levers" added, covering the `referral_code` field rationale and the Public Transparency Portal's post-MLP scoping — both already decided in v2.0, now actually written into the volume.
- **Volume 2:** New §4.5 "Scoped Internal Event System" fully specifies the LISTEN/NOTIFY approach, the MLP-stage vs. deferred event lists, and why it's scoped down from the review's full proposal. §9 (DevOps) gained real DR targets (RTO/RPO/restore testing) and per-component latency tracking. §10 (Security) gained the three-part AI abuse protection spec.
- **Volume 3 (largest fix):** `recommendations` gained five AI versioning columns plus `deleted_at`; `user_profiles` gained `referral_code` and `deleted_at`; four new tables (`prompt_registry`, `model_registry`, `feature_flags`, `recommendation_costs`) and the expanded `audit_log` fully specified in §8; §10 (RLS) documents soft-delete filtering; §11 (Triggers) gained a third trigger auto-populating `audit_log` on system-config writes.
- **Volume 5:** New component specs for AI Transparency Meter and Recommendation Timeline added to §5, both previously only mentioned in the header note.
- **Volume 4 residual:** §9's decision logic corrected to `final_aggregate_confidence`, matching §4.1/§4.2.

**Alternatives considered:** N/A — consistency fixes, not design decisions, same as v2.0.1.

**Expected impact:** None beyond the volumes themselves. All five volumes plus the roadmap are now internally consistent with their own version headers. This closes out the full v2.0 rollout — no further known header/body drift remains as of this entry. Corrected files need to replace what's already committed to the repo.

**Process note:** Two rounds of this pattern (v2.0.1, v2.0.2) is a signal worth naming plainly: batch header-only updates across multiple volumes create exactly this risk. Going forward, a version bump to any volume should be treated as incomplete until the body is verified against the header's claims in the same pass — not assumed correct because the header was updated with good intentions.

---

## CLAUDE.md — 2026-08-05 — Addendum (not a volume, no version bump)

**Document affected:** `CLAUDE.md` (project instructions, repo root)

**Reason:** Mac asked how Claude Code would actually connect to Railway and how OpenAI/Anthropic API keys would get provided — a real operational gap in CLAUDE.md, which had no guidance on credential or connection handling before this point.

**Decision:** Added a "Credentials & Connections" section distinguishing two categories: (1) OAuth-based platform connections (Railway, GitHub, Supabase) — one-time authorize click, persists after that; (2) API keys (OpenAI, Anthropic, sports/data providers, Twilio) — Mac must generate these himself on each provider's site, Claude Code cannot obtain them, and once provided they're set as Railway environment variables per Volume 2 §9, never hardcoded or echoed back in full after being set. Core rule: never assume a credential or connection exists — ask explicitly before a phase that needs one, rather than discovering the gap mid-build.

**Alternatives considered:** Leaving this undocumented and handling it ad hoc when each phase hit the need — rejected, since this is exactly the kind of gap that's cheap to close now and expensive to discover mid-Phase-4 when the AI Orchestrator needs both model API keys at once.

**Expected impact:** No architectural change to any volume. Applies going forward starting with Phase 0 (Railway authorization) and becomes directly relevant again in Phase 4 (OpenAI/Anthropic keys) and Phase 7 (Twilio credentials).

---

## v3.0 — 2026-08-05 — MAJOR

**Volumes affected:** All five volumes, the Engineering Roadmap, and (indirectly) CLAUDE.md's file manifest.

**Reason:** Three supplementary specification documents arrived covering conversational AI experience, an expanded ~150-table proposal, and infrastructure/intelligence architecture details. Triaged the same way as the v2.0 external review — accepted what closed real gaps, scoped down what was oversized for MLP, deferred what lacked a proven near-term consumer. Full point-by-point reasoning in `v3.0-amendments-conversational-intelligence.md`.

**Decision (accepted, summarized):**
- **Volume 1:** Chat-first positioning confirmed in §1 — the product's primary surface is conversational, the dashboard is the reference library, not the front door.
- **Volume 2:** Redis added as the concrete cache implementation; named vendor candidates (The Odds API, SportsDataIO, WeatherAPI/OpenWeatherMap, NewsAPI/GNews) picked for each adapter category; concrete worker refresh cadences (5/10/15-minute workers plus a 6 AM Master Refresh and a triggered Pregame worker) replacing previously vague TTL language.
- **Volume 3:** `daily_game_intelligence` added as a pre-assembled master working table agents query first, explicitly positioned *upstream* of the existing Time Machine snapshot architecture rather than replacing it; 13 derived intelligence score tables feeding it; `display_id` added to `recommendations` for human-readable IDs.
- **Volume 4:** Bankroll Coach's stake formula is now explicit fractional (quarter-Kelly) Kelly Criterion; NL Engine gained session-scoped preference memory (distinct from persistent `betting_dna`) and a four-level progressive disclosure spec (concise by default, expanding only on request); Recommendation Strategy Engine's parlay logic explicitly confirmed to freely mix market types.
- **Volume 5:** `/chat` reordered to the default landing route, `/dashboard` reframed as the reference library — no new architecture, every route already existed; Recommendation Card gained chat-context rendering using the four-level disclosure spec.
- **Roadmap:** Phases 1, 3, 4, 5, and 6 gained new scope, cited per-phase in each volume's changes above.

**Alternatives considered:**
- Adopting the full ~150-table supplementary proposal wholesale — rejected. Most duplicated existing Volume 3 tables under different names or was premature for MLP scope (ML training tables, sentiment tables, extensive historical-data duplication the append-only snapshot tables already cover). Full list of what was deferred and why is in the amendments doc §11.
- Treating chat-first as requiring a tie-breaking decision from Mac before proceeding — considered, but resolved directly: nothing architectural reverses, `/chat` already existed as a fully-specified route, this is a reprioritization of which surface loads first, consistent with what Volume 1 already said about the product feeling like texting an analyst rather than using a dashboard.
- Sportsbook promotions tracking and social sentiment monitoring (X/Reddit) as full features — deferred, no proven MLP-stage consumer, same reasoning pattern already used for several v2.0 deferrals.

**Expected impact:**
- Second MAJOR bump for the project (v2.0 was the first). Same ripple pattern: schema changes in Volume 3 affect Volume 4's agent querying order and Volume 5's data contracts.
- This time, unlike the v2.0 rollout, every volume's body was integrated in the same pass its header was bumped — no header-only shortcut repeated, directly applying the lesson logged in the v2.0.2 entry above.
- CLAUDE.md's file manifest needs `v3.0-amendments-conversational-intelligence.md` added to its list of blueprint documents.
- No volume's pricing, core product principles, or agent committee membership changed — this bump is UX positioning and infrastructure depth, not a reversal of any prior decision.

**Full technical detail:** `v3.0-amendments-conversational-intelligence.md`

---

## v4.0 — 2026-08-06 — MAJOR

**Volumes affected:** Volume 2, Volume 3, Volume 4, Volume 5, and the Engineering Roadmap. Volume 1 reviewed and confirmed to need no changes.

**Reason:** An internal markdown-consistency review (requested directly, not an external document this time) checked all volumes against the latest architectural decisions and proposed four changes plus two additional recommendations. Full change plan was presented and approved before any file was touched — with one approved modification to Change 1.

**Decision (approved, summarized):**
- **Change 1 (modified):** Normalized multi-sport core added to Volume 3 §4.0 — `sports`, `leagues`, `seasons`, `teams`, `players`, `player_stats`, `team_stats`, and a `player_stats_nfl` extension table. `games` gains `sport_id`/`league_id`/`season_id`. **Modification from the original proposal:** the legacy `sport` text column is *not* removed now — both fields coexist through Phase 0/1, with `sport` formally marked deprecated and scheduled for removal only after the NFL migration is verified complete (now a Phase 1 acceptance criterion). This trades brief duplication for zero Phase-0 disruption.
- **Change 2:** Recommendation Worker added — proactive generation (`Master Refresh → Recommendation Worker → AI Committee → store recommendations`) coexisting with on-demand NL Engine generation, not replacing it. Documented in both Volume 2 §4.4 (the trigger) and Volume 4 §3.1 (the flow it triggers), since both needed to agree.
- **Change 3:** Data quality metadata convention added to `daily_game_intelligence` (Volume 3 §4.1) — every jsonb category now carries `source`/`confidence`/`last_updated`/`status`, giving the AI Transparency Meter's `data_quality` dimension (Volume 5 §5) a real computation source instead of vague "cache freshness" language.
- **Change 4:** Environment data-source policy formalized as an official table in Volume 2 §5 (previously only an informal roadmap note).
- **Additional recommendation #1 (approved):** Core Architecture Principles added to Volume 2 §1.1 — ten principles serving as the explicit lens for future decisions, most restating decisions already made elsewhere, collected in one place rather than left implicit across five volumes.
- **Additional recommendation #2 (approved):** Technical Debt & Feature Backlog added to the Engineering Roadmap, organized into Immediate/Next Release/Future/Research categories rather than one flat list, explicitly cross-referencing items already tracked as deferred decisions elsewhere in this changelog to avoid duplicate tracking.

**Alternatives considered:**
- Immediately removing the legacy `sport` field as part of Change 1 (the original proposal) — rejected in favor of the deprecated-but-present transition, per the explicit modification.
- Treating the Recommendation Worker as a replacement for on-demand generation rather than a coexisting path — rejected; the NL Engine's ability to handle a specific unanticipated request ("build me something around Mahomes") is core to the chat-first positioning from v3.0 and can't be lost to a purely proactive model.

**Expected impact:**
- Third MAJOR bump for the project. Same ripple pattern as v2.0/v3.0: schema changes in Volume 3 affect Volume 4's flow and Volume 5's data contracts.
- Phase 1's acceptance criteria gained a real check (dual-write verification for `sport`/`sport_id`) rather than just a note.
- Phase 4's "all agents built" milestone now implicitly includes the Recommendation Worker as a build item, cross-referenced from Phase 3's Master Refresh dependency.
- Volume 1 was reviewed and confirmed to require no changes — worth stating explicitly so a future review doesn't re-check the same ground.
- Every volume's body was integrated in the same pass as its header bump, continuing the discipline established after the v2.0.1/v2.0.2 lesson — no header-only shortcut this time either.

**Full technical detail:** This entry, plus the reasoning inline in each volume's v4.0 note.

---

## v4.1 — 2026-08-07 — MINOR

**Volume affected:** Volume 2 (System Architecture, Backend Design, Railway Deployment, API Strategy, AI Orchestration, DevOps) only.

**Reason:** Phase 0 closure work exercised the CI/CD pipeline for real for the first time — until this session, Railway's native git-autodeploy had been doing all the actual deploying on every environment, silently running in parallel with the Actions pipeline that Volume 2 §9 already claimed was gating every deploy on the test suite. That parallel path masked three real defects that only surfaced once the Actions pipeline was made to actually deploy: a dual-trigger race on `dev` (two deployments live simultaneously for the same commit, confirmed directly against the Railway API — not a theoretical risk), a `working-directory` bug in `ci-cd.yml` that broke every Actions-triggered deploy while native autodeploy quietly covered for it, and a same-day production outage where a routine `SENTRY_DSN` variable-set silently redeployed 5 production services from a stale pre-fix snapshot. Separately, real end-to-end Sentry verification (triggering an actual event from the `dev` environment) found every event was tagged `environment: production` regardless of which environment actually produced it.

**Decision:**
- Railway's native git-autodeploy disabled on all three environments (`dev`, `staging`, `production`). The Actions-gated `railway up` step is now the only path that deploys anywhere — this is what actually makes Volume 2 §9's existing "every deploy runs the test suite before it's allowed to promote" claim true, rather than true only for the Actions path while an untested parallel path ran alongside it.
- `ci-cd.yml`'s deploy jobs fixed: `railway up` now runs from the repo checkout root instead of `working-directory: apps/<service>` (each service's own `rootDirectory` config already scopes the build; running from a pre-scoped subfolder broke the snapshot upload), and the `workers` matrix entry split into the two real Railway service names, `worker-scheduled` and `worker-market-monitor`.
- Standing rule added (CLAUDE.md, 2026-08-07): every Railway config/variable mutation call defaults to `skipDeploys: true` unless a deploy is the explicit point of that call, so a routine variable-set can no longer silently redeploy an autodeploy-disabled environment from a stale cached snapshot.
- Sentry environment tagging fixed: `sentry_sdk.init()` in all four backend services (`api-gateway`, `ai-orchestrator`, `sports-intel-layer`, `workers`) now explicitly passes `environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev")`. Without it, the SDK silently defaults every event to `"production"` regardless of which environment actually generated it — verified fixed by re-triggering and confirming `environment: dev` in the Sentry dashboard.

**Alternatives considered:**
- Leaving native autodeploy enabled alongside the Actions pipeline — rejected once the dev dual-trigger race was confirmed as a real, observed defect (not theoretical): two live deployments for the same commit at once is a correctness problem.
- Disabling native autodeploy on `dev` only, since that's where the race was actually observed, and leaving `staging`/`production` as-is — rejected in favor of hardening all three identically, since both were equally exposed to the same class of bug (the production outage this same session was caused by exactly this class of issue) even though it hadn't yet surfaced there by name.
- Patching the `skipDeploys` gap as a one-time fix on the affected call rather than a standing rule — rejected; a one-off fix doesn't prevent recurrence, which is the actual lesson of the production outage.

**Expected impact:**
- Volume 2 §9's CI/CD claim is now accurate end-to-end rather than aspirational — there is exactly one deploy path per environment, which is also what makes Phase 0's testing requirements (failing test blocks deploy; rollback works) verifiable claims instead of claims about a path nothing was actually forced through.
- No other volume is affected — this is deployment and observability mechanics, not a schema, agent, or product decision. MINOR bump, confined to Volume 2.
- §9's body updated in the same pass as this entry (not header-only), continuing the discipline established after the v2.0.1/v2.0.2 lesson.

**Full technical detail:** This entry; also logged operationally in `PROGRESS.md`'s 2026-08-07 notes.

---

## v4.1.1 — 2026-08-07 — PATCH

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Phase 1 Milestone 2 (sports data tables) built `odds_snapshots` with `id uuid primary key default gen_random_uuid()` — standard UUIDv4. This missed the v2.0 amendment's explicit requirement (Volume 3, "UUIDv7 for high-insert append-only tables") that `odds_snapshots`, `recommendation_agent_outputs`, and `market_monitoring_events` specifically generate primary keys via UUIDv7 rather than UUIDv4, for index locality on the schema's highest-insert-volume tables. Caught while researching UUID generation ahead of building `recommendation_agent_outputs` for Milestone 3, before any dependent code existed — not a case of drift discovered after the fact.

**Decision:** Added a custom `uuid_generate_v7()` PL/pgSQL function (dev runs PostgreSQL 17.6, which has no native `uuidv7()` — that lands in PostgreSQL 18) and altered `odds_snapshots.id`'s default to use it instead of `gen_random_uuid()`. The same function is used for `recommendation_agent_outputs.id` when Milestone 3 is built, and will be reused for `market_monitoring_events.id` when Milestone 4 reaches it, satisfying the v2.0 amendment's requirement for all three named tables with one shared implementation.

**Alternatives considered:** Waiting for a future Postgres upgrade to PG18 to use a native `uuidv7()` function — rejected; there's no reason to block an already-approved v2.0 decision on a future Postgres version with no committed upgrade timeline. Leaving `odds_snapshots` on UUIDv4 and only fixing it forward for the two not-yet-built tables — rejected; the v2.0 amendment names `odds_snapshots` specifically, and the table was empty (schema-only, no real data), so there was no cost to fixing it retroactively instead of carrying the gap forward.

**Expected impact:** None. `odds_snapshots` had zero rows in `dev` at the time of the fix (only rolled-back test data from Milestone 2's own verification pass), so no backfill was needed — this is a closed gap in an already-approved decision, not a new architectural decision, hence PATCH rather than MINOR. No other volume references `odds_snapshots`' key generation mechanism directly.

**Full technical detail:** Also logged operationally in `PROGRESS.md`'s Phase 1 notes, alongside the Milestone 3 migration that first makes use of the same function for `recommendation_agent_outputs`.

---

## v4.2 — 2026-08-09 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Phase 2 Milestone 1 (Authentication) implements AC #1 — "a user can sign up, and a corresponding `user_profiles` row is created automatically" — via a database trigger on `auth.users` INSERT, per Mac's explicit decision to match Phase 1's DB-level-enforcement pattern rather than application code. Building that trigger surfaced a real conflict: `user_profiles.jurisdiction_state` was `not null` (Volume 3 §3), but jurisdiction is collected during onboarding (Phase 2 Milestone 4), a separate step that happens *after* signup. A trigger firing at signup has no jurisdiction value yet and cannot satisfy a `not null` constraint at that moment — flagged per CLAUDE.md's blueprint-vs-reality process rather than resolved by inventing a placeholder value.

**Decision:** `user_profiles.jurisdiction_state` relaxed from `not null` to nullable. Volume 1 §10's actual requirement — no bet-relevant action permitted before jurisdiction is known — is now enforced at the application layer instead of the schema layer: every bet-relevant endpoint checks `jurisdiction_state is not null`, and the onboarding-completion endpoint (Phase 2 Milestone 4) is the only code path that ever sets it. Applied via `supabase/migrations/20260809144824_phase2_signup_trigger.sql` on `dev`; verified with a real signup — the trigger-created row has `jurisdiction_state = null` immediately after signup, and a simulated duplicate-trigger-fire (`on conflict (id) do nothing`) confirmed exactly one row persists, satisfying the idempotency requirement.

**Alternatives considered:**
- Insert a placeholder sentinel value (e.g., empty string) instead of relaxing to nullable — rejected. A magic string is a worse idiom than `null` for "not yet known," requires every read path to special-case it instead of using the standard `is null` check, and risks silently passing validation if a code path forgets to check for the sentinel specifically.
- Delay `user_profiles` row creation until onboarding completion (application code, not a trigger), so `jurisdiction_state` could stay `not null` from the row's first instant — rejected; this contradicts Mac's already-made decision to create the row at signup via a DB trigger, and would leave a window between signup and onboarding where no profile row exists at all, which several other Phase 1 tables (e.g., anything that might reference a signed-up-but-not-onboarded user) aren't designed to tolerate.

**Expected impact:** Application code across Phase 2 onward must not assume `jurisdiction_state` is always populated — every bet-relevant code path needs its own `is not null` check, exactly as Phase 2's roadmap Key Tasks already anticipated ("enforce the not null constraint's intent at the application layer too"). No other volume references this column directly, so this stays a MINOR, Volume-3-only bump. Volume 3 §3's body updated in the same pass (not header-only), continuing the discipline established after the v2.0.1/v2.0.2 lesson.

---

## v4.2 — 2026-08-10 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Before any Phase 3 provider purchase, Mac required the same cost-and-cadence discipline applied across the whole Sports Intelligence Layer, not just The Odds API's player-prop cadence (already revised in the Phase 3A credit-projection work). Reviewing each SportsDataIO- and Odds-API-backed category separately against real-world change frequency surfaced that §8's flat 24/7 cadences didn't match actual data volatility for three categories, and that finalized postgame data (final score, final team stats, final player stats) had no named worker at all despite §4.4 already scoping "postgame review generation (triggered by game completion)" as a Background Worker responsibility and §4.5 already defining a `GameFinished` event for exactly this trigger.

**Decision:**
- **Odds Worker** moves from a flat every-5-minutes-24/7 cadence to the same adaptive, game-aware cadence shape already governing the Player Props Worker (ramping frequency as kickoff approaches, stopping at kickoff) — both are the same underlying market-data category with the same volatility pattern, so treating them identically was the inconsistency, not the original 5-minute number in isolation.
- **Injury Worker** moves from a flat every-10-minutes-24/7 cadence to a window-aware cadence, ramping up only during the real injury-report cycle (Wednesday–Friday practice-report windows, the Friday official-designation window, and the ~90-minutes-pre-kickoff inactive-list window) and staying infrequent otherwise.
- **Postgame Ingestion Worker** added as a new, explicitly named §8 row: event-triggered by the existing `GameFinished` event (§4.5), fetching final score/team stats/player stats exactly once per game. This is §1.1 principle #1 ("download once, reuse everywhere") applied to finalized game data, not a new principle — no rewrite of §1.1's text, only a cross-reference from the new row back to it and to §4.5.
- Weather Worker and News Worker cadences are unchanged in this pass — reviewed and found not to be cost-driven at current volume (WeatherAPI's free tier covers current usage regardless of cadence; NewsAPI/GNews pricing is flat-tier, not metered, so cadence doesn't move cost either way) — a candidate NewsAPI→GNews primary/fallback vendor swap was identified on pricing grounds but is explicitly **not** part of this amendment, pending a full coverage/latency/reliability/licensing comparison Mac requested be done as its own procurement decision.

**Alternatives considered:**
- Leaving Odds Worker on its original flat 5-minute cadence while only revising Player Props — rejected; both are the same category (market/odds data) under the same provider cost model, and applying the adaptive shape to only one of them was an inconsistency with no principled justification once reviewed side by side.
- Treating the postgame-ingestion gap as a new architectural principle requiring new text in §1.1 — rejected; §1.1 principle #1 already states the "download once, reuse everywhere" rule in general terms, and §4.4/§4.5 already named the responsibility and the triggering event. The gap was the missing concrete row in §8's cadence table, not missing principle-level guidance — adding a duplicate principle would have been redundant with existing text rather than filling a real gap.
- Making the Postgame Ingestion Worker an open-ended polling worker (checking game status/stats indefinitely on a fixed interval) instead of event-triggered with a bounded reconciliation window — rejected; while a completed game's stats are *mostly* stable once final (Group C), they are not permanently immutable at the moment of initial ingestion — real NFL stat corrections occur in the days following a game (see `PROGRESS.md`'s 2026-08-10 corrections research). Open-ended continuous polling would still violate §1.1 principle #1's intent, but treating the first fetch as permanently final would risk silently grading bets or reconstructing history against data the league itself later corrected. A small, fixed number of bounded reconciliation checks is the design that satisfies both constraints.

**Expected impact:**
- Phase 3B/3C worker implementations (not yet built) must implement the adaptive/window-aware cadence shapes described here for the Odds and Injury Workers, and must implement the Postgame Ingestion Worker as an event subscriber to `GameFinished`, not a new poller — this is a MINOR, Volume-2-only bump, since it revises cadence values and adds one worker row within the section that already owned this content, without touching any other volume's schema, agents, or product decisions.
- No Volume 3 schema change required — the Postgame Ingestion Worker persists into already-existing `games.final_score`/`team_stats`/`player_stats` tables (verified directly against the live `dev` schema before concluding this).
- Provider-provenance persistence and postgame stat-correction/reconciliation behavior are tracked as separate, still-open items (see `PROGRESS.md`'s 2026-08-10 entries) — deliberately not folded into this amendment, since neither changes a cadence or adds a worker; they're schema-provenance and data-correctness questions respectively.
- §8's body updated in the same pass as this entry (not header-only), continuing the discipline established after the v2.0.1/v2.0.2 lesson.

**Full technical detail:** This entry, plus the reasoning inline in Volume 2's v4.2 note and §8. Also logged operationally in `PROGRESS.md`'s 2026-08-10 notes.

**Full technical detail:** Also logged operationally in `PROGRESS.md`'s Phase 2 notes.

---

## v4.3 — 2026-08-10 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** The v4.2 Postgame Ingestion Worker amendment (Volume 2 §8) established that finalized NFL stats can receive real, provider-issued corrections after a game is marked final, and flagged an open question: how should a later stat correction interact with an already-settled wager? Left undocumented, this risked Phase 5 either building bet-grading logic that silently recalculates a wager's outcome from corrected stats (misrepresenting what the bettor actually experienced), or discovering the settlement-history gap identified below as a surprise mid-build rather than a known, planned-for item. Mac reviewed and approved a full six-rule policy governing this relationship, with an explicit instruction that Phase 3 not implement any of it, but that Phase 3's architecture also not be built in a way that makes it impossible to implement later.

**Decision:** Added a new subsection to §6 (Bet Verification & Performance Attribution), **Stat Correction ↔ Bet Settlement Policy**, documenting Mac's six rules verbatim in substance:
1. Sportsbook settlement (`verified_bets.outcome`) and sports-stat truth (`player_stats`/`team_stats`/`games.final_score`) are separate, related records — never automatically equivalent.
2. A wager's graded outcome comes from the official settlement source, never inferred solely from corrected statistics.
3. A provider stat correction updates/supersedes the stat record but preserves the previous version, records that a correction occurred, preserves when it became known, and never silently overwrites an already-settled wager outcome.
4. A sportsbook regrade preserves the original settlement, records the regrade as a new historical event (not an in-place update), updates the current effective outcome, preserves when the regrade became known, and retains enough history to reconstruct both settlements.
5. Performance analytics (`verified_user_performance`, `ai_performance`) use the effective sportsbook-settled outcome, never the stats tables directly, when a settlement record exists.
6. Time Machine reconstruction must distinguish recommendation-time information, initial postgame stats, later corrections and their discovery time, the original settlement, any regrade, and the current effective outcome — none of which a later correction or regrade may rewrite.

A one-line cross-reference was added to §7's `postgame_reviews` description (`outcome_summary` narrates recommendation performance, not wager settlement) pointing back to this policy, since that table is generated on the same `games.status = 'final'` trigger this policy concerns itself with.

**Schema gap check performed before writing anything** (per Mac's explicit instruction to verify existing structures first and report gaps rather than build ahead of Phase 5): rules 1, 2, and 5 are already structurally satisfied by the existing separation between `verified_bets`/`verified_user_performance`/`ai_performance` and the stats tables — no schema change needed. Rule 3's history-preservation half is already possible today without a migration, since `team_stats`/`player_stats` carry no uniqueness constraint blocking a correction from being inserted as a new row; what's missing is an explicit "this row is a correction" marker, folded into the Milestone F provenance migration already proposed (not applied) in `PROGRESS.md`. **Rule 4 surfaced a genuine, real gap:** `verified_bets` is a single mutable row per wager with no append-only/versioning pattern (unlike `odds_snapshots`), so an in-place update on a regrade would destructively overwrite the original settlement today. This is **not being closed now** — per Mac's explicit instruction not to pull Phase 5 implementation backward into Phase 3, it's documented as a known, flagged gap for Phase 5's schema work (most likely an append-only settlement-history table mirroring the `odds_snapshots` pattern) rather than built or migrated here.

**Alternatives considered:**
- Silently deferring this policy to be written when Phase 5 actually starts, rather than documenting it now — rejected; Mac's explicit request was to lock in the policy now, while the reasoning and the schema-gap analysis are fresh, specifically so Phase 3's architecture can be checked against it today rather than risk an incompatible design shipping first.
- Closing the `verified_bets` settlement-history gap with a migration in this same pass, since the gap is already identified — rejected; Mac's instruction was explicit ("do not pull a Phase 5 implementation backward into Phase 3 merely to close a future requirement"), and Phase 3 doesn't touch `verified_bets` at all, so nothing about Phase 3's own scope requires this table to change now.
- Placing the full policy in §7 (`postgame_reviews`) instead of §6 — considered, since the initial framing of "which section owns this" cited §7, but corrected before writing: `verified_bets`, the table this policy is actually about, lives in §6; §7's `postgame_reviews` only narrates recommendation performance and is not itself a settlement record, so it gets a one-line cross-reference, not the primary text.

**Expected impact:**
- This is documentation of a Phase 5 policy, not a schema or Phase 3 implementation change — MINOR, Volume-3-only bump, no migration applied, no other volume touched.
- Phase 5's roadmap scope now has a concrete, pre-approved specification to build against for bet-grading/settlement, including one named schema gap (`verified_bets` settlement history) to design for rather than discover cold.
- Phase 3 requires no architecture change as a result of this policy — its current design (Postgame Ingestion Worker inserting new rows rather than overwriting; no code path touching `verified_bets`) already satisfies the "don't foreclose this later" boundary Mac set.
- §6's body updated in the same pass as this entry (not header-only), continuing the discipline established after the v2.0.1/v2.0.2 lesson.

**Full technical detail:** This entry, plus the reasoning inline in Volume 3's v4.3 note and §6. Also logged operationally in `PROGRESS.md`'s 2026-08-10 notes.

---

## v4.2.1 — 2026-08-13 — PATCH

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Mac's Phase 3E Architecture Decision Checkpoint (Decision 6) identified that §8's Postgame Ingestion Worker row described itself as making §4.4's "postgame review generation (triggered by game completion)" responsibility "concrete with a name and a trigger" — wording that read as though Postgame Ingestion (fetching final score/team stats/player stats, Phase 3) and Postgame Review generation (evaluating already-made recommendations against final results, Phase 5, `engineering-roadmap-build-order.md` Milestone 4) were the same worker. They are not, and conflating them risked Phase 3 work later being read as license to build recommendation-grading logic before the recommendation architecture exists.

**Decision:** Removed the conflating cross-reference from the Postgame Ingestion Worker's cadence-table row and added a new paragraph immediately after the table explicitly separating the two by phase and responsibility: Postgame Ingestion Worker (Phase 3) detects `games.status` transitioning to final, consumes `GameFinished`, fetches/persists final score/team stats/player stats, and performs bounded reconciliation checks — it does not grade recommendations, change agent weights, or produce a review. Postgame Review generation (Phase 5) evaluates recommendations against the final data Ingestion produced, and depends on Phase 5's recommendation architecture existing. §4.4's own category description was left unchanged — it correctly uses "postgame review generation" only as an example of the Background Workers category in general; only the table row's specific cross-reference was wrong.

**Alternatives considered:**
- Leaving the wording as-is on the grounds that a careful reader could infer the phase boundary from context — rejected; Mac's own explicit instruction was to correct the ambiguous wording through the normal documentation process specifically so it can't be misread as Phase 3 scope later, by a future session or by Mac himself working from this document months from now.
- Rewriting §4.4's general category description instead of the table row — rejected; §4.4's text was never actually wrong (it correctly describes "postgame review generation" as one example of the Background Workers category, with no phase claim attached), so rewriting it would have changed correct text to fix a problem that lived entirely in the table row's added cross-reference.

**Expected impact:** Wording-only correction inside a section that already owned this content — PATCH, Volume-2-only, no schema or architecture change. Makes explicit, in the same document a future session will read first, the phase boundary Decision 6 approved: Phase 3 must not grade recommendations, change agent weights, generate recommendation-performance reviews, or determine which agents were right/wrong.

**Full technical detail:** This entry, plus the reasoning inline in Volume 2's v4.2.1 note and §8. Also logged operationally in `PROGRESS.md`'s 2026-08-13 notes (Phase 3E-1).

---

## v4.4 — 2026-08-13 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Building the first real background worker (Phase 3E) surfaced that `games.external_provider_id` carried a hidden, undocumented assumption: `app/persistence/odds_snapshots.py` resolved every game by matching this one column directly against The Odds API's own event id, with no way for a second vendor's id (SportsDataIO's `GameKey`, needed for the Injury/Team-Stats/Player-Stats/Postgame-Ingestion Workers) to ever coexist on the same game. Separately, `games` had no way to record NFL week or season phase (preseason/regular/postseason) at all, which several of those same workers need to resolve which week's data to fetch. Mac's Phase 3E Architecture Decision Checkpoint (Decisions 1 and 2) approved fixing both as a single foundational migration (Phase 3E-1) before any worker touching them is built.

**Decision:**
- **`game_provider_ids` (new table, Decision 2):** the authoritative multi-provider game identity mechanism. One internal game can now carry many `(provider_name, provider_game_id)` rows. `unique(provider_name, provider_game_id)` guarantees a provider's id resolves to exactly one game (the database-level proof that "a provider id can't silently map to two different games"); `unique(game_id, provider_name)` guarantees a game has at most one id per provider. `provider_name` is constrained to `the_odds_api`/`sportsdataio`, the two vendors this codebase actually integrates with today. RLS: public-read, service-role-only writes, matching every other sports data table.
- **`games.season_type`/`games.week` (new nullable columns, Decision 1):** a normalized internal vocabulary (`preseason`/`regular`/`postseason`), checked against the rest of the codebase first and confirmed no existing internal convention existed to reuse — the only prior occurrence of season-phase data anywhere was SportsDataIO's own raw numeric `SeasonType` field inside fixture JSON, never persisted or normalized. `week` is nullable and NFL-specific, following the `player_stats_nfl` extension-table precedent of not forcing one sport's shape onto a shared table.
- **`games.external_provider_id` deprecated, made nullable (follow-up migration, same day):** surfaced while building Schedule ingestion — a new `games` row created from a SportsDataIO Schedule entry has no meaningful value for a column that was always The Odds API's id specifically. Not dropped (per Mac's explicit instruction not to silently delete it), only deprecated via column comment and relaxed from `not null` to nullable so the capability Decision 2 approved (a non-`the_odds_api` source creating a game) isn't blocked at the database level.
- **Backfill:** every pre-existing `games.external_provider_id` value was inserted as a `game_provider_ids` row with `provider_name = 'the_odds_api'`, preserving `odds_snapshots.py`'s prior resolution behavior exactly — no game was duplicated or renumbered, and `seed.sql` was updated to insert the same mapping rows so a fresh `supabase db reset` matches migrated dev data.
- **`odds_snapshots.py` migrated** off the hidden single-column assumption onto a new shared resolver, `app/persistence/game_identity.py` (`resolve_game_ids`/`link_provider_id`), called with the explicit `provider_name="the_odds_api"` this module has always actually meant. A new `app/persistence/schedule.py` uses the same resolver to create/update `games` rows from `ScheduleEntry` data, establishing games and their provider mapping for a Schedule source that isn't The Odds API.

**Alternatives considered (from the Decision 2 checkpoint):** adding a second provider-specific ID column directly to `games` (e.g. `sportsdataio_game_key`) — rejected; doesn't scale past two providers and repeats the exact mistake being fixed. Relying on team-name/date fuzzy matching as the runtime game-resolution mechanism — rejected per Mac's explicit instruction; fuzzy matching is not reliable enough to be a permanent identity mechanism and was never adopted, including for the new Schedule-ingestion "does this game already exist under another provider" question, which remains an explicitly open item (see Expected Impact).

**Expected impact:**
- Unblocks production wiring for the Injury Worker, Team Stats resolution, Player Stats resolution, and Postgame Ingestion Worker's `season_week_for_game`/`current_season_week`/`game_key_for` resolver injection points (all built in Phase 3C-ii against test-only resolvers) — actual worker-level wiring remains later-milestone (3E-3+) scope, not built in this pass.
- **Known, explicitly open gap, not solved here:** if two different providers independently discover the same real-world game (e.g. The Odds API's Odds Worker and SportsDataIO's Schedule ingestion both eventually knowing about the same Sunday matchup) with no prior mapping for either, this migration's Schedule ingestion path creates two separate `games` rows rather than reconciling them — Decision 2 explicitly rules out fuzzy matching as the mechanism to prevent this, and no worker yet exists with the authority to perform that reconciliation. Flagged here rather than silently built around; a candidate owner (a later 3E sub-step, or Master Refresh) needs to be decided before either the_odds_api or sportsdataio Schedule/Odds ingestion runs against overlapping real data.
- Season-type normalization currently only maps SportsDataIO's `SeasonType == 1` (regular season) — the only value CONFIRMED FROM LIVE FREE TRIAL data. Preseason/postseason values are deliberately unmapped (raise rather than guess, matching the existing `_SCHEDULE_STATUS_MAP` precedent) pending a live Schedule call against those season types.
- No live provider calls, hosted Redis, or paid infrastructure were used to build or test this migration — proven entirely with fixtures/fakes plus direct read/write verification against the live `dev` Supabase project (migration applied, backfill verified, both unique constraints proven live via begin/rollback transactions).
- MINOR, Volume-3-only bump: additive table, two new nullable columns, one constraint relaxation on a column already marked for eventual removal — no other volume's schema, agents, or product decisions change as a result.

**Full technical detail:** This entry, plus the reasoning inline in Volume 3's v4.4 note, §4.0's `game_provider_ids`/`games` sections, and §4.1's `public_betting`/`sharp_money` deferred-status note. Also logged operationally in `PROGRESS.md`'s 2026-08-13 notes (Phase 3E-1).

---

## v4.3 — 2026-08-13 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Building Master Refresh (Phase 3E-2) required resolving a real ambiguity in §8's cadence table, surfaced during the 3E-2 planning pass Mac requested: the Master Refresh row's original wording ("Full pull: games, odds, props, injuries, weather, news, rosters, schedule updates") predates the v4.2 revision that gave Odds/Player Props/Injury their own dedicated adaptive/window-aware cadences. Taken literally, that wording is an instruction for Master Refresh to independently re-fetch the same five categories those specialized workers already own — exactly the duplicate-provider-call problem the v4.2 adaptive-cadence work exists to prevent.

**Decision:** Master Refresh's row is rewritten to state its actual scope precisely: it directly fetches/establishes Schedule refresh, game creation/update, season/week context, and the roster/depth-chart morning refresh, and assembles `daily_game_intelligence` from those plus whatever the Odds/Player Props/Injury/Weather/News workers have *already* persisted. It never calls those five adapters itself. If a specialized worker hasn't run yet — true for all five as of this entry, since none are built yet — the corresponding `daily_game_intelligence` field is left null/unavailable, not fabricated and not duplicated via a direct fetch.

**Alternatives considered:**
- Leaving the "full pull" wording as-is and treating it as informal/non-binding — rejected; Mac's own Phase 3E-2 planning process explicitly named this exact ambiguity ("do not let Master Refresh become a giant duplicate fetch of everything if specialized workers already own those categories") and required it resolved before implementation, not left informally understood.
- Having Master Refresh call each specialized adapter once as a "morning snapshot" on the specialized workers' behalf — rejected; the Player Props Worker's own cadence definition already names "1 morning snapshot" as its own first tier, meaning that snapshot is that worker's responsibility already, not a gap Master Refresh needs to fill. Master Refresh calling the adapter first would just be the exact duplicate-fetch problem under a different name.

**Expected impact:**
- Phase 3E-2's actual implementation (`app/master_refresh/`) follows this resolved scope exactly — confirmed structurally, not just by convention: `run_master_refresh`'s own signature only accepts a Supabase client and a SportsDataIO client, so it has no way to call The Odds API/WeatherAPI/NewsAPI even if it tried.
- `daily_game_intelligence.odds`/`.props`/`.injuries`/`.weather`/`.news` will read as null/unavailable in Phase 3E-2's own output until the corresponding worker (3E-4 through a later sub-step) is built and has run at least once — an expected, honest state, not a bug.
- MINOR, Volume-2-only bump: clarifies an existing cadence-table row's scope, no new worker, no schema change.

**Full technical detail:** This entry, plus the reasoning inline in Volume 2's v4.3 note and §8. Also logged operationally in `PROGRESS.md`'s 2026-08-13 notes (Phase 3E-2).

---

## v4.5 — 2026-08-13 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** `daily_game_intelligence.rest`/`.travel` have existed as untyped jsonb columns since v3.0 with no documented semantics anywhere in any volume (confirmed by direct search before writing Phase 3E-2's Master Refresh implementation, which needed to compute real values for both). Mac's Phase 3E-2 Architecture Decision Checkpoint (Decisions 2 and 3) approved exact definitions for both rather than leaving them to be invented ad hoc at implementation time.

**Decision:**
- **`rest`:** days since a team's most recent `status='final'` game before the current game's `scheduled_start`, as a UTC calendar-date difference. Only a finalized game counts as "previous" — scheduled/canceled/never-finalized-postponed games are excluded. A season opener is `rest_days: null` + `season_opener: true` (never a fabricated 0), matching the null-not-neutral principle already established for `public_betting`/`sharp_money`. No separate bye-week flag was added — the elevated `rest_days` number itself is sufficient, per Mac's explicit instruction not to add speculative fields ahead of an actual downstream consumer needing one.
- **`travel`:** distance from the venue of a team's previous final game to the venue of its current game (game-to-game travel burden) — explicitly not home-city-to-current-stadium distance. Defined, but deliberately left null/unavailable in Phase 3E-2's implementation: SportsDataIO's Schedule response does carry venue coordinates (`StadiumDetails.GeoLat`/`GeoLong`, CONFIRMED present in the already-captured live fixture), but neither the `ScheduleEntry` adapter model nor `games` currently persists them past the stadium name. Populating `travel` for real needs a widened `ScheduleEntry` plus durable coordinate storage (new `games` columns or a `stadiums` reference table) — a schema decision deliberately deferred out of 3E-2's scope and tracked as a follow-up architecture item (`engineering-roadmap-build-order.md`'s Technical Debt & Feature Backlog gained a companion entry for the related `team_provider_ids` gap the same day), not solved by fabricating coordinates.

**Alternatives considered:**
- Adding an `is_bye_week_return` boolean alongside `rest_days` now, since the shape was already being designed — rejected per Mac's explicit instruction; no existing consumer needs it yet, and Volume 3's own §1 principles already warn against building for hypothetical future requirements.
- Building the `ScheduleEntry`/schema widening needed for real `travel` values as part of this same pass, since the coordinate data already exists at the provider level — rejected; Mac's explicit instruction was to keep this schema decision out of 3E-2's scope specifically because travel does not block Master Refresh, and a stadium/geo schema decision deserves the same explicit checkpoint treatment `game_provider_ids` got in 3E-1, not a decision folded silently into an unrelated worker's implementation pass.

**Expected impact:**
- Phase 3E-2's `app/master_refresh/rest.py` implements the `rest` definition exactly as documented here; `travel` is always written `null` by 3E-2, consistent with "defined but deliberately unavailable."
- No schema change — both columns already existed as untyped jsonb since v3.0; this entry documents semantics only.
- MINOR, Volume-3-only bump.

**Full technical detail:** This entry, plus the reasoning inline in Volume 3's v4.5 note and §4.1's new `rest`/`travel` semantics paragraphs. Also logged operationally in `PROGRESS.md`'s 2026-08-13 notes (Phase 3E-2).

---

## v4.4 — 2026-08-13 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Phase 3E-2's Master Refresh implementation used a rolling 7-day slate window (`[today, today + 7 days)`) rather than a literal single calendar day, flagged at the time as an interpretive choice within already-approved scope rather than a Blueprint-specified behavior — a literal single-day filter would mean the worker's `daily_game_intelligence` assembly step does almost nothing most days, given NFL games cluster Thursday/Sunday/Monday. Mac reviewed and approved this behavior explicitly when accepting 3E-2, with an instruction to document it as the canonical, non-reinterpretable horizon before 3E-3 begins.

**Decision:** §8 gains an explicit "Master Refresh operating horizon" statement — `[today, today + 7 days)` — directly beneath the cadence table. Scoped narrowly: this horizon governs only Master Refresh's own game-identity/`daily_game_intelligence`-assembly work. It explicitly does not change any specialized worker's own cadence — Odds/Player Props are not polled continuously for 7 days, nor are Injuries/Weather/News; each remains governed exactly by its own existing row in the cadence table.

**Alternatives considered:**
- Leaving the horizon as an implementation detail documented only in `app/master_refresh/slate.py`'s code comments — rejected; Mac's explicit instruction was to document it in the Blueprint precisely so it can't be silently reinterpreted in a future session working from documentation rather than code.
- Redefining "today's slate" narrowly to a literal calendar day and rebuilding 3E-2's filtering to match — rejected; Mac's explicit review approved the rolling-window behavior as built, not a request to change it.

**Expected impact:**
- `app/master_refresh/slate.py`'s docstring updated to reference this note directly, replacing its prior "flagged for correction" framing now that the behavior is approved rather than provisional.
- No schema or worker-cadence change — MINOR, Volume-2-only, documentation of an already-approved and already-implemented behavior.

**Full technical detail:** This entry, plus the reasoning inline in Volume 2's v4.4 note and §8's new operating-horizon paragraph. Also logged operationally in `PROGRESS.md`'s 2026-08-13 notes (Phase 3E-3).

---

## v4.6 — 2026-08-13 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Auditing what the Odds/Player Props Worker (3E-4) will need, per Mac's explicit instruction before that worker is built, surfaced that `teams` has the same single-column identity limitation `games` had before `game_provider_ids` (Phase 3E-1, Decision 2): SportsDataIO identifies teams by abbreviation (`"KC"`), The Odds API by full name (`"Kansas City Chiefs"`) — confirmed directly from this project's own already-captured fixtures. Deterministic cross-provider game linking (matching an incoming Odds API event to an already-existing SportsDataIO-created game by team identity) is impossible without a general team-identity mechanism, and Mac's explicit instruction was not to solve this with ad hoc string normalization scattered through worker code.

**Decision:**
- **`team_provider_ids` (new table):** mirrors `game_provider_ids`'s exact shape and constraint design deliberately — `unique(provider_name, provider_team_id)` (a provider's team id resolves to exactly one team) and `unique(team_id, provider_name)` (a team has at most one id per provider), both proven live against dev via `begin`/`rollback` transactions. `provider_name` constrained to `the_odds_api`/`sportsdataio`, matching `game_provider_ids`'s own convention.
- **`teams.external_provider_id` deprecated via column comment, but *not* made nullable** — unlike `games.external_provider_id` in 3E-1, no follow-up constraint-relaxation migration was needed: the column was already nullable in its original Phase 1 definition, and a direct grep confirmed no code anywhere reads it. This is a materially easier situation than `games` faced, not an oversight.
- **Backfill:** the six teams already seeded in dev were linked to their genuinely correct provider representations — public, standard NFL naming facts (confirmed against this project's own SportsDataIO/The Odds API fixtures), not preserved from `teams.external_provider_id`'s synthetic seed values (`"seed-kc"` etc.), which were never real provider ids for any vendor and would have been a dishonest backfill source. The mapping itself lives in one explicit, documented, tested table (`app/persistence/team_backfill.py`'s `TEAM_BACKFILL`), not scattered across worker code, per Mac's explicit instruction.
- **Odds/Player Props pre-implementation audit performed (code-only, fixture-only, no live calls):** confirmed The Odds API's event payload carries `home_team`/`away_team` as full names (though no current adapter model exposes these fields yet — a real gap for 3E-4 to close, not solved here). Confirmed `games.home_team`/`.away_team` hold SportsDataIO's abbreviation text (plain columns, not FKs to `teams.id`), so resolving a game by team requires a two-hop comparison through `team_provider_ids` (forward via `the_odds_api`, reverse via `sportsdataio`) rather than direct FK equality. Proved via a real fixture-driven test (`tests/test_odds_game_linking_audit.py`) that this two-hop comparison is fully deterministic with zero fuzzy matching in the normal case, and that an unrecognized team name correctly resolves to "unresolved," never a guess.

**Alternatives considered:**
- Deferring `team_provider_ids` until 3E-4 actually starts, since Master Refresh itself never needs cross-provider team matching (it only consumes SportsDataIO's own authoritative Schedule/Roster data) — considered, and explicitly the default per Mac's own instruction ("do not add `team_provider_ids` during 3E-2 unless Master Refresh itself genuinely cannot operate without it"), which is exactly why it stayed out of 3E-2 and became its own foundational checkpoint (3E-3) instead of either being skipped or built prematurely inside a worker that doesn't need it.
- Adding `home_team_id`/`away_team_id` foreign keys to `games` now, replacing the free-text `home_team`/`away_team` columns and removing the need for the two-hop comparison — rejected for this pass; that's a real, larger schema change (touching every existing read/write of those columns across `schedule.py`, `master_refresh/run.py`, and the RLS/reversibility test suites) that Mac did not authorize in this checkpoint, flagged instead as a candidate future simplification once the two-hop pattern proves cumbersome in practice.

**Expected impact:**
- 3E-4 (the Odds/Player Props Worker, not yet started) has a proven, tested, deterministic linking mechanism to build against instead of inventing one under implementation pressure, plus a documented gap list (the missing `home_team`/`away_team` fields on `OddsLine`/`PlayerProp`) to close as part of that work.
- No schema change beyond the additive `team_provider_ids` table and one column comment — MINOR, Volume-3-only bump.
- No live provider calls, no hosted Redis, no Railway cron configured — proven entirely with fixtures plus direct read/write verification against live `dev` Supabase.

**Full technical detail:** This entry, plus the reasoning inline in Volume 3's v4.6 note and §4.0's new `team_provider_ids` section. Also logged operationally in `PROGRESS.md`'s 2026-08-13 notes (Phase 3E-3).

---

## v4.7 — 2026-08-14 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Phase 3E-4A's explicit task: expand `team_provider_ids` coverage to all 32 current NFL teams (`teams` had only the original 6 seed teams), using only provider identifiers this repository's own fixtures actually confirm — no live provider calls, no fabrication from general/public NFL knowledge even where that knowledge is well-established. Auditing the existing `TEAM_BACKFILL` table against this stricter bar (grepping every fixture file directly, not relying on memory of what 3E-3 confirmed) surfaced a real, previously-unflagged gap: two of 3E-3's six entries (Dallas Cowboys → `"DAL"`, Philadelphia Eagles → `"PHI"`, both `sportsdataio`) were not actually backed by any fixture at the time — they had been filled in from standard, well-known NFL abbreviation conventions, which does not meet this project's fixture-only provenance bar for provider identifiers.

**Decision:**
- **`teams` expanded to all 32 current NFL teams** (from 6), via `20260814050000_expand_nfl_teams_and_provider_ids.sql`. Team *names* are not provider-specific data — they're the same public, standard NFL naming already relied on for the original 6 seed teams — so Mac's "do not fabricate provider identifiers" instruction governs `team_provider_ids` rows specifically, not this internal canonical-name column.
- **`team_provider_ids` coverage expanded to exactly what direct fixture inspection confirms:** 9 new `sportsdataio` mappings (ARI, ATL, CAR, CHI, LAR, NE, NO, SEA, TB), bringing sportsdataio coverage to 13 of 32 teams. `the_odds_api` coverage remains unchanged at 6 of 32 (BAL, BUF, DAL, KC, PHI, SF) — zero new fixture evidence exists for any other team on that provider. **19 teams have zero SportsDataIO fixture evidence; 26 teams have zero The Odds API fixture evidence** — both reported here as a real, standing gap, not silently treated as resolved. `resolve_team_ids` already returns "absent" (never a guess) for any of these, and no worker code may assume every `teams` row has a provider mapping.
- **Retroactive provenance correction, disclosed rather than silently fixed:** the DAL/PHI `sportsdataio` entries added in 3E-3 without fixture backing have been removed from `app/persistence/team_backfill.py`'s `TEAM_BACKFILL` (the Python source of truth going forward). Their already-applied `team_provider_ids` database rows from the 3E-3 migration are deliberately left in place rather than retroactively dropped — 3E-3 was already reviewed and accepted, and this session does not unilaterally rewrite an accepted phase's committed data. This is flagged here as a standing discrepancy between the source-of-truth table and the live database for Mac's awareness, not resolved unilaterally.

**Alternatives considered:**
- Filling in the remaining 19/26 teams' provider identifiers from general NFL knowledge (standard abbreviation conventions, full team names) — rejected; this is exactly the practice the stricter 3E-4A provenance bar exists to rule out, even though that knowledge is highly reliable. A provider identifier must trace to this repository's own captured evidence (fixture, live-verified artifact, or provider documentation already present in-repo), not general knowledge, however reliable.
- Silently dropping the DAL/PHI `sportsdataio` database rows to match the corrected `TEAM_BACKFILL` table — rejected; per `CLAUDE.md`'s "if the Blueprint and reality disagree, stop and flag it explicitly" principle, an already-accepted phase's committed data is not unilaterally rewritten mid-session. Flagging the discrepancy here is the correct resolution; deleting those rows (if desired) is Mac's call, not a silent cleanup.

**Expected impact:**
- 15 of 32 teams now have at least one confirmed provider mapping (4 with both providers: BAL, BUF, KC, SF); 17 have none. Any Phase 3E-4 worker resolving a team by name must handle "unmapped" as a legitimate, expected outcome for most of the league today, not an edge case.
- No schema change (same `team_provider_ids` table shape from v4.6) — MINOR, Volume-3-only, data-coverage and provenance-documentation bump only.
- The DAL/PHI database-vs-source-of-truth-table discrepancy is a standing item for Mac to resolve explicitly (drop the two live rows, or accept them as adequately-confirmed after all) — not auto-resolved by this entry.

**Full technical detail:** This entry, plus `app/persistence/team_backfill.py`'s own module docstring (which documents the same finding in code) and the 3E-4 completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-14 notes (Phase 3E-4A).

---

## v4.5 — 2026-08-14 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Phase 3E-4's task: implement the Odds Worker and Player Props Worker (Volume 2 §8's cadence table already named both as "Adaptive, game-aware," but neither had a real implementation before this phase). Building them required resolving three things the Blueprint's prose described but didn't fully specify as executable rules: (1) the exact numeric polling interval within each named ramp window (the Blueprint states window *boundaries* -- 2h/60min/15min/5min -- but never a rate within them), (2) how dynamic cache TTL (Decision 4, carried since Phase 3D) actually derives from that same cadence rather than being a second, independently-invented timing rule, and (3) how a worker discovers a game's own Odds API event identity the first time, since Master-Refresh-created games have no The Odds API linkage until something establishes one.

**Decision:**
- **One shared window-classification module, `app.workers.windows`,** is the single authoritative policy for both adaptive polling cadence and dynamic TTL selection (Decision 4), reused by both Odds Worker and Player Props Worker rather than each computing its own tiers or duplicating the other's. Six tiers: FAR (>2h out, 24h interval), RAMP_2H, RAMP_60M, RAMP_15M, RAMP_5M (2min interval), STOPPED (post-kickoff, never polled). The four ramp boundaries and "stops at kickoff" are CONFIRMED FROM VOLUME 2 §8; the specific interval-within-each-window mapping and the pre-ramp flat-24h interval are an ASSUMED, documented engineering interpretation of "ramping frequency through those windows," flagged explicitly for Mac's confirmation rather than presented as settled Blueprint fact (§8 itself now carries the identical note -- see this volume's own v4.5 update above).
- **Player Props Worker's row is the primary numeric source; Odds Worker's cadence is implemented as literally mirroring it,** per §8's own "Mirrors the Player Props Worker's cadence shape... both are the same market-data category" sentence -- read directly before implementing, not assumed identical without checking, and confirmed to be what the Blueprint's own text already states.
- **Dynamic TTL (Decision 4) implemented:** `app.workers.windows.ttl_seconds` returns each window's poll interval as its cache TTL. Both workers construct `CachingAdapter` with this per-window value; `app/adapters/cache.py`'s flat `CATEGORY_TTL_SECONDS["odds"]`/`["player_props"]` entries are superseded for these two workers (left in place only as dead weight for a hypothetical future flat-TTL caller, of which none exists in-tree). Injury Worker's own dynamic TTL remains explicitly out of scope (Phase 3E-5), per Mac's instruction -- `app.workers.windows` is written generically enough to be reused there without modification when that phase begins.
- **Deterministic game linking promoted to production** (`app.persistence.odds_game_linking`, from the fixture-proven 3E-3 audit mechanism): The Odds API event → home/away identities → `team_provider_ids` → canonical `teams.id` → SportsDataIO team identities → candidate internal game → scheduled-start validation (6-hour tolerance, an ASSUMED, documented judgment call -- no Blueprint-specified number exists) → `games.id`. An event resolves to exactly one game or is UNRESOLVED (logged + returned for the caller to observe) -- never guessed, never a second game auto-created. `OddsLine`/`PlayerProp` widened (Phase 3E-4B) to carry `home_team`/`away_team`/`commence_time` -- the game-identity information this resolution needs, direct-inspection-confirmed as genuinely required (the third field, `commence_time`, was found necessary during 3E-4C's own build, beyond the two fields originally flagged in the 3E-3 audit).
- **Odds Worker discovery mode:** `TheOddsApiOddsAdapter.fetch_odds([])` returns every event unfiltered, since the bulk endpoint always returns the full slate regardless of filter (CONFIRMED cost model: markets × regions, not per-event) -- used to self-discover and link a not-yet-linked game. Player Props Worker has no equivalent (its endpoint is event-specific, requiring an already-known id) and therefore depends on linkage established elsewhere, skipping a due-but-unlinked game for that cycle rather than performing its own discovery -- an explicit architecture decision, not an oversight, flagged for Mac's confirmation.

**Alternatives considered:**
- Inventing per-window poll intervals with no stated reasoning, presented as if directly specified -- rejected; every ASSUMED number here is traceable to a specific textual justification (boundary-as-interval, "every-few-minutes" implying multiple sub-5-minute polls) and explicitly flagged as an interpretation, per `CLAUDE.md`'s "never present an assumption as vendor/Blueprint fact" discipline.
- A second, independent TTL-computation path for Odds/Player Props instead of reusing the polling-cadence classification -- rejected; Mac's explicit Decision 4 instruction was "one authoritative window-classification policy... do not create two independent implementations of the same timing rules."
- Player Props Worker performing its own team-based discovery (duplicating Odds Worker's mechanism) so it never depends on another worker's run -- rejected for this phase; the event-specific endpoint has a real per-call cost (CONFIRMED), and duplicating discovery between two independently-scheduled workers would mean paying that cost twice for the same linkage. Flagged as an assumption for Mac to confirm rather than silently decided as obviously correct.

**Expected impact:**
- `app/workers/windows.py`, `app/workers/odds_worker.py`, `app/workers/player_props_worker.py`, and `app/persistence/odds_game_linking.py` are the real, tested implementations of this volume's Odds/Player Props Worker cadence rows and Decision 4.
- `app/adapters/cache.py`'s `CATEGORY_TTL_SECONDS` entries for `"odds"`/`"player_props"` are now historical/superseded, not the active TTL source for either worker -- documented in that file directly to prevent a future session from assuming they're still load-bearing.
- No live provider calls, no hosted Redis, no Railway scheduler configured -- proven entirely with fixtures (`the_odds_api` bulk/event fixtures) and `InMemoryCacheBackend`, per Mac's explicit 3E-4 cost/provider-safety and scheduling-deferral instructions.
- MINOR, Volume-2-only bump: implements and clarifies already-planned cadence rows and an already-approved Decision 4, no cross-volume contradiction.

**Full technical detail:** This entry, plus the reasoning inline in Volume 2's v4.5 note, the new "Odds/Player Props Worker implementation" paragraph in §8, and the 3E-4 completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-14 notes (Phase 3E-4).

---

## v4.8 — 2026-08-18 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** v4.7 (3E-4A) closed with two open items: 19 teams had zero SportsDataIO fixture evidence, and Dallas Cowboys/Philadelphia Eagles' already-applied `sportsdataio` rows (`DAL`/`PHI`) were flagged as inferred, not fixture-confirmed. Mac authorized one additional live SportsDataIO call — the 11th of the 12-call Free Trial budget, the 12th/final call explicitly withheld — scoped to exactly one endpoint, `/v3/nfl/scores/json/Teams`, to resolve both items with real provider evidence rather than continuing to defer them.

**Decision:**
- **Single-purpose diagnostic capture, same pattern as 3C-ii's:** a temporary, dev-only, token-gated route (`/diagnostics/sportsdataio-capture`) hard-capped at one provider request per process lifetime, deployed, invoked exactly once (`200`, 32 teams returned), its full response captured to a GitHub Actions artifact (never logged), then removed in a follow-up commit — see `PROGRESS.md`'s 2026-08-18 notes for the full round-trip evidence, including the one real obstacle hit along the way: this session's network egress policy blocks GitHub's artifact-storage host directly, so the artifact was retrieved by having Mac download and paste it back rather than by fetching it through the sandboxed session.
- **Deterministic reconciliation, zero fuzzy matching:** all 32 `teams.name` values were matched exactly against the capture's `FullName` field — 32/32 reconciled, zero conflicts, zero orphans on either side. The capture's `Key` field (e.g. `"KC"`) is the real `sportsdataio` team identifier, consistent with every other SportsDataIO category already in this codebase.
- **All 13 previously-confirmed `sportsdataio` mappings matched the live `Key` exactly** — no drift found.
- **Dallas Cowboys/Philadelphia Eagles resolved: CONFIRMED CORRECT.** The live `Key` for both teams (`DAL`, `PHI`) matches the already-applied 3E-3 database rows exactly. `TEAM_BACKFILL` (`app/persistence/team_backfill.py`) restores both entries with this citation, closing the v4.7-flagged discrepancy between the source-of-truth table and the live database.
- **`team_provider_ids` `sportsdataio` coverage taken to 32/32** (from 13/32) via `20260818040000_team_provider_ids_sportsdataio_full_coverage.sql`, adding the 17 remaining teams (CIN, CLE, DEN, DET, GB, HOU, IND, JAX, LAC, LV, MIA, MIN, NYG, NYJ, PIT, TEN, WAS), each citing `tests/fixtures/sportsdataio/teams_active_normal.json` directly. `the_odds_api` coverage is unchanged at 6/32 — this round captured no Odds API evidence, and that gap remains real and unresolved.
- **New fixture:** `tests/fixtures/sportsdataio/teams_active_normal.json` — all 32 teams, full (not a sample, unlike this project's other SportsDataIO fixtures), since full league coverage is the point of this capture. Only `UpcomingOpponent` is scrambled; every identity field is real.

**Alternatives considered:**
- Spending the 12th/final call to double-check the reconciliation — rejected; the capture already reconciled all 32 teams deterministically with zero conflicts, and Mac's instruction was explicit that the final call is not authorized. A budget's worth of margin is preserved rather than spent confirming an already-unambiguous result.
- Retrieving the GitHub Actions artifact by disabling TLS verification or otherwise routing around the session's egress-policy block — rejected outright; the correct response to an org policy denial is to report it and find another path (here, asking Mac to relay the artifact), never to bypass it.

**Expected impact:**
- `team_provider_ids` `sportsdataio` coverage is now complete (32/32) and every entry is either fixture- or live-capture-confirmed — no inferred/general-knowledge entries remain anywhere in `TEAM_BACKFILL`. `the_odds_api` coverage (6/32) is the only remaining team-identity gap, unchanged by this round and tracked as before.
- SportsDataIO Free Trial budget: 11 of 12 calls spent; 1 remains, intentionally unspent.
- No schema change (same `team_provider_ids` table shape since v4.6) — MINOR, Volume-3-only, data-coverage and provenance-resolution bump only.
- The temporary diagnostic route/token/workflow built for this round are removed in the same PR that lands this documentation, per the same cleanup discipline 3C-ii established.

**Full technical detail:** This entry, plus `app/persistence/team_backfill.py`'s own module docstring, `tests/fixtures/sportsdataio/PROVENANCE.md`'s "Team identity verification" section, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes.

---

## v4.6 — 2026-08-18 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Phase 3E-5's task: implement the Injury Worker (Volume 2 §8's cadence table already named it "Window-aware," but no real implementation existed before this phase). Building it required resolving something the Blueprint's own text made explicit but the existing shared timing module (`app.workers.windows`, built for Odds/Player Props in 3E-4) could not represent: Injury Worker's cadence is CONFIRMED day-of-week-anchored ("practice-report updates land roughly once daily Wednesday-Friday... stays infrequent the rest of the week"), not purely kickoff-proximity-anchored like Odds/Player Props' continuous ramp. Mac's explicit Decision 1 for this phase: extend the shared module rather than build a second, competing cadence system.

**Decision:**
- **`app.workers.windows` extended with `classify_injury_window`/`should_poll_injuries`** (plus matching interval/TTL functions) rather than a new, separate module — reuses `classify_window`'s exact UTC-normalization-before-subtracting discipline and `_require_aware` verbatim, the same DST-safety proof Phase 3E-4G already established, applied to a new axis (day-of-week) the original module never needed. Five tiers: INFREQUENT, ACTIVE_WEEK, FINAL_RAMP, INACTIVE_LIST, STOPPED — see this volume's own v4.6 note and §8 update for the full CONFIRMED/ASSUMED breakdown of each tier's boundary and interval.
- **Malformed-injury-row isolation (Decision 3):** `SportsDataIOInjuryAdapter.fetch_injuries`'s original 3C-ii contract wrapped its entire row-parsing loop in one try/except, so a single malformed row invalidated the whole week's response for every other team — changed explicitly for 3E-5 (approved as part of this phase, not a silent behavior change) to per-row isolation: a malformed row is logged (WARNING, with whatever identifying fields it does carry, never fabricated) and skipped, every other row's data survives. The provider/response-level boundary this preserves unchanged: an HTTP failure, non-200, non-JSON body, or non-array top-level shape still fails the whole fetch.
- **Append-only, no de-duplication (Decision 2):** `app/persistence/injury_reports.py` mirrors `odds_snapshots.py` exactly — every successful poll writes a new snapshot row, even if the underlying injury status hasn't changed, matching every other snapshot table's existing "every movement is a new row" convention and `injury_reports`' own append-only DB trigger (already in place since the Phase 1 migration, now actually exercised by real writes for the first time).
- **Identity resolution, zero fuzzy matching:** SportsDataIO's Injuries response carries no game identifier at all (only `Team`/`Opponent`/`Season`/`Week`), so the adapter's existing resolver-injection contract (`game_key_for`, established 3C-ii, same pattern as `WeatherAPIWeatherAdapter.location_for_game`) requires the worker to pre-resolve every in-scope game's own SportsDataIO GameKey before calling `fetch_injuries` — since that resolver must be synchronous, the worker builds it from data already fetched (candidate games + one batched `game_provider_ids` reverse-resolve), not a per-row async DB call. A row that can't be resolved (bye week, or not yet linked) is skipped by the adapter's own existing behavior, never guessed.
- **`daily_game_intelligence` integration deliberately untouched:** `app.persistence.snapshots.latest_injury_report` and `daily_game_intelligence.py`'s `injuries` field assembly were both already built in 3E-2, speculatively ahead of this worker existing — inspection confirmed both already correctly read whatever `injury_reports` holds, so this phase adds a writer, changes no reader.

**Alternatives considered:**
- Reusing `classify_window`'s existing kickoff-proximity tiers unchanged for Injury Worker, treating "roughly once daily" as adequately covered by the FAR tier's already-daily cadence — considered as the zero-new-code option, but rejected because it cannot represent the Blueprint's explicit Mon/Tue/Sat-vs-Wed/Thu/Fri asymmetry at all, which Mac's Decision 1 explicitly asked to be represented, not approximated away.
- A wholly separate injury-timing module, independent of `app.workers.windows` — rejected; Mac's explicit instruction was to extend the shared system, and the day-of-week logic needs nothing from the existing module except its already-proven aware-datetime/DST-safety primitives, which extension reuses directly.
- Leaving the adapter's original whole-call-raises behavior in place and building isolation only at the worker layer (catching the raised exception and treating a whole week as failed) — rejected; Mac's explicit Decision 3 was per-row isolation, which is only achievable inside the adapter's own row loop, not by catching a failure after the fact once the whole batch is already lost.

**Expected impact:**
- `app/workers/injury_worker.py`, `app/persistence/injury_reports.py`, and the extended `app/workers/windows.py` are the real, tested implementation of this volume's Injury Worker cadence row and Decision 2/3.
- `app/adapters/cache.py`'s `CATEGORY_TTL_SECONDS["injuries"]` entry is now historical/superseded, not the active TTL source, matching `"odds"`/`"player_props"`'s identical 3E-4F precedent.
- No live SportsDataIO calls anywhere in this phase's build or tests (budget unchanged at 11 of 12); no hosted Redis provisioned; no Railway scheduler configured. `SportsDataIOInjuryAdapter`'s existing tests were updated (not just extended) to match the new per-row-isolation contract, since the old whole-call-raises test asserted behavior this phase deliberately changed.
- MINOR, Volume-2-only bump: implements an already-planned cadence row and extends (never replaces) an already-approved shared policy module, no cross-volume contradiction. Volume 3 is unaffected — `injury_reports`' table shape and `daily_game_intelligence`'s read integration were both already fully specified and already correct before this phase.

**Full technical detail:** This entry, plus the reasoning inline in Volume 2's v4.6 note, the new "Injury Worker implementation" and "Malformed-injury-row isolation" paragraphs in §8, `app/workers/windows.py`'s own extended module docstring, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes (Phase 3E-5).
