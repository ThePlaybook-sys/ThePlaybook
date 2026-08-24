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

---

## v4.9 — 2026-08-18 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Phase 3E-6's Weather Worker needed two things Volume 3's v4.5 travel-semantics note already identified as missing and explicitly deferred: precise venue coordinates for WeatherAPI location resolution, and an authoritative indoor/outdoor signal for the previously-approved dome optimization. Direct inspection (not assumed) confirmed the exact same gap that note described: `StadiumDetails.GeoLat`/`.GeoLong`/`.Type` are genuinely present in SportsDataIO's live Schedule response (CONFIRMED in this project's own already-captured fixture), but `SportsDataIOScheduleAdapter` discards all three during normalization, and `games` has nowhere to hold them even if it didn't.

**Decision:**
- **`games` gains three nullable columns — `venue_lat`, `venue_long`, `venue_type`** (`20260818050000_games_venue_fields.sql`), populated from `StadiumDetails.GeoLat`/`.GeoLong`/`.Type` during the existing Schedule-ingestion write path. `ScheduleEntry` widened correspondingly, scoped to exactly these three fields — no other `StadiumDetails` fields (capacity, playing surface, city/state/country) carried, since nothing downstream needs them yet.
- **Option A (direct nullable columns) chosen over Option B (a dedicated `stadiums` reference table),** both presented to Mac before implementation per his explicit "STOP before a schema decision" instruction. Option A matches the `season_type`/`week` precedent (3E-1: direct nullable columns on `games`, not a new table) more closely, and is smaller for a first cut; Option B is more normalized (NFL has ~30 unique venues, reused across many games) but adds a new table/FK/backfill for a real but modest win at this scale. Mac's explicit approval: Option A.
- **`venue_type` is normalized internal vocabulary** (`outdoor`/`dome`/`retractable_dome`), never SportsDataIO's raw `StadiumDetails.Type` string directly in business logic — same discipline `season_type`'s `_SEASON_TYPE_MAP`/`games.status`'s check constraint already established. `_VENUE_TYPE_MAP` is CONFIRMED FROM LIVE FREE TRIAL: exactly three distinct raw values ("Outdoor", "Dome", "RetractableDome") observed across this repo's own already-captured fixtures (`schedules_normal.json`, `teams_active_normal.json`) — an unrecognized raw value raises rather than being silently passed through or guessed, same as an unrecognized `Status`/`SeasonType`.
- **All three columns nullable, never fabricated when missing** — a response with no `StadiumDetails` at all is a legitimate "unknown," not malformed, and stays `null` all the way through persistence (proven by a dedicated test at both the adapter and persistence layers).

**Alternatives considered:**
- A `stadiums` reference table (Option B) — considered seriously (it's the more normalized design, and Volume 3's own v4.5 note already floated it), but not chosen for this first cut given the league's small venue count makes the denormalization cost of Option A genuinely small; may be reconsidered "when multi-sport scale actually justifies it" (Mac's own words, approving Option A).
- Hardcoding a stadium-to-dome-status list as a workaround instead of a schema change — explicitly rejected per Mac's own instruction not to do this without his approval; the provider already supplies this information, so a manually maintained list would be redundant, error-prone, and exactly the kind of fabricated-certainty shortcut this project's data-quality convention exists to prevent.
- Treating `RetractableDome` as either definitively indoor or definitively outdoor — rejected; SportsDataIO's Schedule/Teams responses report the stadium's *type*, not its roof state on any given game day, which a retractable roof can change. Modeling this as `is_dome: null` (unknown) rather than guessing either extreme is the correct application of this project's existing null-not-neutral convention (`public_betting`/`sharp_money`/`rest_days`), not a new principle invented for this case.

**Expected impact:**
- `app/workers/weather_worker.py`'s dome/indoor optimization and location resolution are now correctly grounded in real provider data, not a fabricated signal or a discarded one.
- `WeatherConditions.is_dome` changed from a hard `bool = False` default to `bool | None = None` — closes a real, pre-existing null-not-neutral gap in the 3C-i model (it could never represent "unknown" before this phase).
- The travel-distance computation Volume 3's v4.5 note deferred is not built by this entry — but the durable coordinate storage that note said travel would eventually need now exists, built for a different (weather) consumer first. `daily_game_intelligence.travel` remains `null`, unchanged.
- MINOR, Volume-3-only, purely additive schema bump — no column removal, no type change, no existing data touched.

**Full technical detail:** This entry, plus the reasoning inline in Volume 3's v4.9 note, the new `venue_lat`/`venue_long`/`venue_type` paragraph in §4.0, the updated `travel` semantics paragraph, Volume 2's own v4.7 note and §8 update (Weather Worker's consumption side), and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes (Phase 3E-6).

---

## v4.7 — 2026-08-18 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Phase 3E-6's task: implement the Weather Worker (Volume 2 §8's cadence table already named "Every 15 minutes," but no real implementation existed before this phase), including the dome/indoor optimization Mac had previously approved in principle. Unlike Injury (3E-5), Weather's cadence is CONFIRMED flat — no day-of-week or kickoff-proximity ramp language exists anywhere in this section for this worker, so no extension of `app.workers.windows` was needed, only two DERIVED reuses of conventions already established by every other specialized worker.

**Decision:**
- **Flat 900-second cadence, no adaptive tiers invented** (`app.workers.weather_worker._POLL_INTERVAL_SECONDS = 900`) — CONFIRMED to already match `app.adapters.cache.CATEGORY_TTL_SECONDS["weather"]` exactly, verified by direct inspection before reusing it rather than assumed. Two boundaries this section never states explicitly are DERIVED, not invented: the 7-day candidate-game window (the same scoping decision Odds/Player Props/Injury each independently adopted, documented identically in each worker's own module) and stop-at-kickoff (reusing `app.workers.windows.classify_window`'s existing `Window.STOPPED` classification directly — never its ramp-tier intervals, which this worker never touches at all).
- **Dome/indoor optimization implemented against real provider data** (Volume 3 v4.9's new `games.venue_type`): a `'dome'` venue is never polled (WeatherAPI call skipped entirely — outdoor weather is structurally irrelevant to a fixed roof); `'outdoor'` polls normally; `'retractable_dome'` or a missing `venue_type` polls *if* coordinates are available (regional weather is still useful context even with an unknown roof state) but the persisted `is_dome` stays `null`, never coerced to `false` just because polling happened.
- **No `game_provider_ids` identity hop, a genuine architectural asymmetry with Odds/Player Props/Injury, checked before assuming symmetry:** WeatherAPI has no native game/event concept at all — `game_provider_ids.provider_name`'s own check constraint doesn't even permit `'weatherapi'`. `WeatherConditions.game_external_id` is this project's own internal `games.id`, supplied directly by the worker; `app.persistence.weather_snapshots` does not call `resolve_game_ids`, unlike its sibling snapshot-persistence modules.
- **Per-game isolation** (mirroring `player_props_worker.py`'s exact reasoning, since WeatherAPI's endpoint is per-game like Player Props', not bulk like Injury's): one fetch call per due game, so one game's provider failure or malformed response can never take another's already-fetched weather down with it.

**Alternatives considered:**
- Building adaptive Weather polling tiers mirroring Odds/Player Props' ramp shape — rejected; Volume 2 §8 states no ramp language at all for Weather, and Mac's explicit instruction was not to invent tiers where the Blueprint specifies a flat cadence.
- Reusing `app.workers.windows.should_poll` directly (which internally derives its interval from `classify_window`'s ramp tiers) — rejected; that would silently apply Odds/Player Props' ramping intervals (3600/900/300/120s) instead of Weather's flat 900s, so this worker reuses only `classify_window`'s STOPPED classification, with its own trivial flat-interval-elapsed check alongside it.
- Treating a `retractable_dome`/missing venue type as `is_dome=False` (outdoor) to simplify the polling decision — rejected; would silently fabricate certainty this project's data-quality convention explicitly forbids (Mac's own instruction: "Do not treat unknown as false").

**Expected impact:**
- `app/workers/weather_worker.py` and `app/persistence/weather_snapshots.py` are the real, tested implementation of this volume's Weather Worker cadence row and the previously-approved dome optimization.
- No live SportsDataIO or WeatherAPI calls anywhere in this phase's build or tests (SportsDataIO budget unchanged at 11 of 12; zero WeatherAPI calls made); no hosted Redis provisioned; no Railway scheduler configured.
- MINOR, Volume-2-only bump: implements an already-planned cadence row and an already-approved optimization against newly-available real data (Volume 3 v4.9), no cross-volume contradiction beyond the schema dependency itself.

**Full technical detail:** This entry, plus the reasoning inline in Volume 2's v4.7 note, the new "Weather Worker implementation" paragraph in §8, `app/workers/weather_worker.py`'s own module docstring, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes (Phase 3E-6).

---

## v4.8 — 2026-08-18 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Phase 3E-7's task: implement the News Worker (Volume 2 §8's cadence table already named "Every 15 minutes," but no real implementation existed before this phase). Two blockers were identified and stopped on, per Mac's explicit instruction, before any implementation began: (1) the NewsAPI-vs-GNews provider decision, explicitly deferred by Mac on 2026-08-11 and never revisited — still unresolved (`PROGRESS.md`), and (2) Volume 3's still-real absence of a `news_snapshots`-style history table (confirmed again by direct re-inspection: §4's snapshot-table list still names only `injury_reports`/`weather_snapshots`/`depth_chart_snapshots`/`referee_assignments`; `news` lives only as `daily_game_intelligence.news` jsonb). Both were presented to Mac as required stop-and-decide points, not resolved silently.

**Decision:**
- **Provider decision remains a BLOCKER, unaffected by this phase.** This worker is built provider-neutrally against the existing `NewsAdapter`/`NewsArticle` interface — the same adapter-pattern guarantee every other category relies on — with `NewsAPINewsAdapter` (3C-i) wired in only because it is the only concrete adapter that exists (no GNews code exists anywhere in this repository). Swapping it for a future `GNewsNewsAdapter` requires zero change to `app/workers/news_worker.py`.
- **Persistence: Option A, the smallest additive move** — no new table. `app.persistence.daily_game_intelligence` gains `write_news`, a narrowly-scoped upsert touching only `game_id`/`news` (same `on_conflict=game_id`/`resolution=merge-duplicates` idiom as `upsert_daily_game_intelligence`, never clobbering odds/weather/injuries/etc.). Option B (an append-only `news_snapshots`/`news_reports` table) was presented and explicitly deferred, not ruled out: nothing in Phase 3's acceptance criteria requires News history, and a correctly-designed version of it would need to be team-keyed rather than game-keyed (`NewsArticle` carries no game identity at all, only `related_teams`) — a genuine schema departure from Odds/Injuries/Weather's game-keyed convention, not a template copy, and one that inherits the same commercial-storage-terms question the original Milestone F deferral was about. Remains available future work, gated on the same provider decision above.
- **Cadence: CONFIRMED flat 900s** (`app.workers.news_worker._POLL_INTERVAL_SECONDS`), matching `CATEGORY_TTL_SECONDS["news"]` exactly (already correct, verified not assumed). **A deliberate, explicitly-flagged DEPARTURE from Weather's stop-at-kickoff convention:** this worker never imports `app.workers.windows` at all. News about a team has no natural "market closes at kickoff" boundary the way pregame odds/weather do — injury updates, postgame reactions, and next-week previews are all still legitimately "news about that team" after its own kickoff. The only boundary reused from existing convention is the 7-day candidate window itself (same `_CANDIDATE_WINDOW_DAYS` every other specialized worker independently adopted), which already bounds which teams get polled at all without needing a second, game-specific stop condition.
- **Polling unit is a resolved `teams.id`, not a game** (`last_polled_at` keyed accordingly) — the correct extension of "each worker's `last_polled_at` matches its own real fetch granularity" (Weather/Odds/Player Props: per-game; Injury: one bulk timestamp) to News's genuinely different, team-scoped `fetch_news(team=...)` contract.
- **Identity resolved by the worker, never guessed:** `games.home_team`/`.away_team` (SportsDataIO abbreviations) are resolved to `teams.id` via the existing `team_identity.resolve_team_ids` (now 32/32-confirmed for `sportsdataio`, Volume 3 v4.8), then to the canonical `teams.name` `fetch_news` expects via a new, minimal `app.persistence.teams.list_teams_by_id`. An abbreviation with no mapping is `teams_unresolved`, excluded from that cycle, never fuzzy-matched. This worker also never calls the bare, unscoped `fetch_news(team=None)` "NFL" query at all — its results carry no trustworthy team relationship (`related_teams=[]`), and true league-wide news is therefore out of scope for this worker's game-keyed persistence target, a real model/table-shape mismatch flagged rather than papered over. A defensive check (`_validate_articles`) additionally confirms every returned article's own `related_teams` actually contains the team it was queried for, before attribution — not a blind trust of `NewsAPINewsAdapter`'s existing guarantee, since a future/different adapter isn't obligated to preserve it.
- **Failure/stale-data handling:** a team whose fetch fails this cycle is excluded from that cycle's results; any game depending only on that team is skipped this cycle -- `write_news` is simply not called, so whatever `news` already held is left untouched, never overwritten with an empty/neutral value. A team whose fetch *succeeds* with zero articles is a distinct, positive result ("checked, genuinely nothing") and **is** written, as an empty `value: []` with fresh `last_updated`/`status` -- exactly what makes it distinguishable at read time from a stale/unwritten value.
- **Malformed-article isolation left as a known asymmetry with Injury Worker's 3E-5 Decision 3, not silently matched:** `NewsAPINewsAdapter.fetch_news` still wraps its whole article-parsing loop in one try/except (unchanged from 3C-i) -- a malformed article invalidates that team's entire fetch for the cycle, handled identically to any other provider failure (skip, preserve last-known-good). Changing the adapter to per-row isolation was not authorized as part of this phase's scope and is flagged as available future work.

**Alternatives considered:**
- Waiting for the NewsAPI-vs-GNews decision before building anything — rejected; the adapter pattern already makes the worker provider-neutral, so waiting would block real, useful work on a vendor question this phase doesn't need answered.
- Building the append-only history table now (Option B) — rejected for this phase; no Phase 3 acceptance criterion needs News history, and the correct shape (team-keyed) is different enough from every other snapshot table's game-keyed convention that building it ahead of the provider/commercial-terms decision risked designing it around the wrong constraints.
- Reusing `app.workers.windows`'s stop-at-kickoff convention for consistency with Weather — rejected; would silently stop tracking real, still-relevant news (e.g., an injury update landing during or after a game) for no reason grounded in News's actual real-world behavior, unlike Weather/Odds/Player Props where the underlying data itself becomes meaningless post-kickoff.
- Trusting `NewsAPINewsAdapter`'s `related_teams=[team]` guarantee without a worker-side check — rejected; "no fuzzy matching, no guessed identity" is a standing project-wide instruction, not a per-adapter one, and the check costs nothing given the adapter interface a different provider could implement.

**Expected impact:**
- `app/workers/news_worker.py`, `app/persistence/teams.py`, and `app/persistence/daily_game_intelligence.write_news` are the real, tested implementation of this volume's News Worker cadence row.
- No live NewsAPI, GNews, SportsDataIO, or WeatherAPI calls anywhere in this phase's build or tests (SportsDataIO budget unchanged at 11 of 12; zero News-provider live calls); no hosted Redis provisioned; no Railway scheduler configured.
- Two items remain explicitly open, unaffected by this phase's own completion: the NewsAPI-vs-GNews provider decision, and the news-history persistence question (Option B), both re-flagged here rather than closed.
- MINOR, Volume-2-only bump: implements an already-planned cadence row without any schema change (Volume 3 is unaffected -- `daily_game_intelligence.news`'s column shape was already correct and unchanged) and without resolving either previously-deferred decision.

**Full technical detail:** This entry, plus the reasoning inline in Volume 2's v4.8 note, the new "News Worker implementation" paragraph in §8, `app/workers/news_worker.py`'s own module docstring, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes (Phase 3E-7).

---

## v4.10 — 2026-08-18 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Phase 3E-8's task (Pregame/Postgame Ingestion Workers) surfaced a real, load-bearing schema gap: `player_stats.player_id` is a `not null` FK, but `players` had never been populated by any existing code (Roster data only ever lands in `daily_game_intelligence.players`, a jsonb working field), and `players.external_provider_id` had the exact same single-vendor-assumption defect `games.external_provider_id`/`teams.external_provider_id` both had before `game_provider_ids` (3E-1)/`team_provider_ids` (3E-3) fixed it. Mac's explicit Decision 1 (Option B) approved solving this the same way, rather than deferring PlayerStats persistence. Separately, Postgame Worker's game-final detection needed a stable anchor for "when did this game become final," which nothing in the existing schema provided.

**Decision:**
- **`player_provider_ids` (new table), mirroring `game_provider_ids`/`team_provider_ids` exactly** -- `unique(provider_name, provider_player_id)`, `unique(player_id, provider_name)`, FK `players(id) on delete cascade`, same `provider_name` check constraint, same public-read/service-role-write RLS. `players.external_provider_id` deprecated via column comment, same convention as the other two tables' deprecation comments.
- **`games.finalized_at` (new nullable column)** -- set once, the first time a game's status is observed to transition to `'final'`. A dedicated anchor rather than reusing `games.updated_at`, since a later Schedule re-poll can legitimately re-PATCH an already-final game's other fields, which would silently drift `updated_at` away from the true finalization moment. Postgame Worker's bounded reconciliation schedule (`app.workers.reconciliation`, Volume 2 v4.9) measures elapsed time against this column as a pure function, with no other new persisted state required.
- **Fixture-backed player population, not fabricated.** `app.persistence.player_backfill.PLAYER_BACKFILL` contains exactly four real players -- the entire universe of player identity evidence this project has ever captured (`rosters_normal.json`'s 2 rows, `player_stats_week_bulk_normal.json`'s 2 rows), each PlayerID/Name/Team/Position confirmed by direct fixture read. No live provider call was made or authorized to expand this. Coverage gaps are reported (`unresolved_players`), never guessed by name-matching, never auto-created during ingestion.

**Alternatives considered:**
- Deferring PlayerStats persistence entirely until a live call could establish broader player coverage -- rejected per Mac's explicit Decision 1: build the architecture and fixture-backed population provable now, report remaining coverage honestly, rather than blocking the whole PlayerStats half of 3E-8 on a purchase decision.
- Auto-creating a `players` row opportunistically from live PlayerGameStatsByWeek response data at ingestion time (not just from the curated backfill list) -- considered and rejected: SportsDataIO Free Trial data is confirmed scrambled for several PlayerStats fields (DEFERRED PRODUCTION VERIFICATION), and expanding `players` silently at ingestion time would be exactly the "expand identity data without an explicit, reviewable backfill" pattern Mac's team-identity discipline (`team_backfill.py`'s own docstring) already rejected once.
- Repurposing `games.updated_at` as the reconciliation anchor instead of a new column -- rejected; a Schedule re-poll's own unconditional PATCH (unrelated to finalization) would silently move the anchor forward, corrupting every subsequent reconciliation-checkpoint calculation for that game.

**Expected impact:**
- `app/persistence/player_identity.py`, `app/persistence/player_backfill.py`, `app/persistence/team_stats.py`, and `app/persistence/player_stats.py` are the real, tested implementation this schema addition supports.
- `player_stats`/`team_stats` themselves are unchanged (no new column, no new constraint) -- the correction-aware, no-duplicate-row persistence design (insert only when incoming stats differ from the existing `created_at`-latest row) is an application-layer decision, not a schema one; a DB-level append-only trigger (reusing the already-existing `block_snapshot_updates()` function) remains available future hardening, explicitly not applied this phase.
- MINOR, Volume-3-only, purely additive schema bump -- no column removal, no type change, no existing data touched.

**Full technical detail:** This entry, plus the new `player_provider_ids`/`games.finalized_at` paragraphs in Volume 3 §4.0, Volume 2's own v4.9 note and §8 update (Pregame/Postgame consumption side), `app/workers/postgame_worker.py`'s own module docstring, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes (Phase 3E-8).

---

## v4.9 — 2026-08-18 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Phase 3E-8's task: implement the Pregame Worker and Postgame Ingestion Worker (Volume 2 §8's cadence table already named both rows, but neither had a real implementation before this phase). Extensive pre-implementation research (per Mac's explicit "research first, do not begin implementation immediately" instruction) found that Pregame's stated purpose was partially already delivered by 3E-4/3E-5's own final-ramp cadence tiers, that Postgame's stats-fetch adapters already existed unused since 3C-ii, and that game-final detection had no working mechanism at all -- three genuine architecture findings, not assumptions, that shaped every decision below.

**Decision:**
- **Pregame Worker is a coordination/orchestration worker, not a new provider category (Decision 3).** It fetches nothing itself. It forces one more, unconditional pass of the four already-existing per-game/bulk workers -- Odds, Player Props, Injury, Weather -- for exactly the game entering its final 5-minute pre-kickoff window, via a new `target_game_ids` parameter added to each of those four workers (backward-compatible; `None` preserves every existing caller's behavior unchanged, verified by the full pre-existing regression suite passing unmodified). **T-minus-5-minutes is the trigger, reusing the already-CONFIRMED `Window.RAMP_5M` boundary from Odds/Player Props' own window architecture (`app.workers.windows`)** rather than inventing a new timing concept -- no Blueprint-stated number existed for "T-minus kickoff" otherwise. **News Worker is deliberately excluded, not overlooked:** it never stops polling a team at that team's own kickoff (v4.8's own explicit design), so there is no "last-minute value" specific to T-minus-5 the way there is for line moves and inactive lists.
- **The targeted `daily_game_intelligence` refresh (Decision 4).** Master Refresh's own per-game assembly logic was extracted into `app.master_refresh.game_refresh.refresh_daily_game_intelligence_for_game` (behaviorally identical, proven by the full pre-existing Master Refresh test suite passing unmodified) so Pregame Worker can reuse it for one targeted game immediately after its refresh, rather than waiting for the next 6 AM Master Refresh run. Roster/`players` composition is read back verbatim (`read_existing_players`, mirroring `read_existing_news`'s identical pattern), not re-fetched -- out of scope for a T-minus-5 refresh.
- **Postgame Worker's game-final detection uses the smaller polling/status-scan approach (Decision 2), not the full `GameFinished` event infrastructure** -- no code anywhere in this codebase publishes a real Postgres LISTEN/NOTIFY event yet, confirmed before deciding this. The worker re-polls the same `SportsDataIOScheduleAdapter`/`persist_schedule_entries` Master Refresh already uses (reused, not duplicated), scoped to a backward-looking window instead of Master Refresh's forward-looking one, and structured so a future real `GameFinished` event handler can call the same ingestion function directly (`_ingest_final_stats_for_game`) without redesigning the pipeline.
- **SportsDataIO's live completed-game status string is ASSUMED / DEFERRED LIVE VERIFICATION, explicitly not presented as confirmed.** `_SCHEDULE_STATUS_MAP["Final"]` has never been observed live -- the 2026 season hadn't started as of the last live capture. The remaining SportsDataIO Free Trial call was deliberately NOT spent to verify this now, since spending it before a real game has finished would very likely resolve nothing.
- **Postgame Worker reuses the existing 3C-ii `SportsDataIOTeamStatsAdapter`/`SportsDataIOPlayerStatsAdapter` unchanged** -- both were built and fixture-tested in 3C-ii and never wired into a worker until now. `final_score` is derived from `TeamGameStats`' own `Score`/`HomeOrAway` fields, never a separate Scores/BoxScore endpoint.
- **Bounded reconciliation (Decision 5): a fixed, approved schedule -- `initial`, `+10m`, `+30m`, `+2h`, `+24h`, `+72h`** -- implemented in one place (`app.workers.reconciliation`) so the intervals can be changed centrally without rewriting the worker, per Mac's explicit instruction. **Explicitly an APPROVED PRODUCT/ARCHITECTURE DECISION, not a SportsDataIO-confirmed requirement** -- PROGRESS.md's 2026-08-10 research cited a *range* from secondary-source vendor guidance, and this schedule is a concrete policy decision related to but not identical to that range.
- **Idempotent, correction-aware TeamStats/PlayerStats persistence, a real design decision presented and applied, not silently invented.** `team_stats`/`player_stats` have neither a uniqueness constraint nor an append-only DB trigger (confirmed before deciding this; Volume 3 §6 already flags this as a standing, unclosed gap). `app.persistence.team_stats`/`app.persistence.player_stats` insert a new row only when incoming stats differ from the existing `created_at`-latest row for that (game, team)/(game, player) pair -- reusing the same "latest row" read pattern `app.persistence.snapshots` already established elsewhere, no new schema. A DB-level append-only trigger (reusing the already-existing `block_snapshot_updates()` function) remains available future hardening, explicitly flagged, not applied.

**Alternatives considered:**
- Building the full Postgres LISTEN/NOTIFY `GameFinished` event infrastructure now -- rejected per Mac's explicit Decision 2; out of 3E-8's scope, and the status-scan approach is structured to be swapped in later without redesigning ingestion.
- Having Pregame Worker call each coordinated worker's full entrypoint unfiltered (`last_polled_at=None`, no game targeting) -- rejected; on a real NFL Sunday, up to ~13 games could independently cross T-minus-5 within minutes, and re-fetching each worker's entire 7-day candidate slate that many times in a row would be genuinely wasteful, unlike the `target_game_ids` filter which costs nothing extra for Odds Worker's already-bulk discovery call and saves real provider calls for Player Props/Weather's per-game ones.
- Spending the remaining SportsDataIO Free Trial call now to confirm the live `"Final"` status string -- rejected; the 2026 season hadn't started as of the last capture, so the call would very likely still only observe `"Scheduled"` and resolve nothing, a calendar-timing problem independent of budget.

**Expected impact:**
- `app/workers/pregame_worker.py`, `app/workers/postgame_worker.py`, `app/workers/reconciliation.py`, and the `target_game_ids` widening on `odds_worker.py`/`player_props_worker.py`/`injury_worker.py`/`weather_worker.py` are the real, tested implementation of both cadence rows.
- No live NewsAPI/GNews/SportsDataIO/WeatherAPI/The Odds API calls anywhere in this phase's build or tests (SportsDataIO budget unchanged at 11 of 12); no hosted Redis provisioned; no Railway scheduler configured.
- Postgame Review (Phase 5, `postgame_reviews`), bet/result settlement (Phase 5, `verified_bets`), agent weighting, and recommendation grading remain entirely untouched -- confirmed structurally, not just by intent.
- MINOR, Volume-2-only bump: implements two already-planned cadence rows; the schema dependency (Volume 3 v4.10) is a separate, cross-referenced entry per this changelog's own convention.

**Full technical detail:** This entry, plus the reasoning inline in Volume 2's v4.9 note, the new "Pregame Worker implementation"/"Postgame Ingestion Worker implementation" paragraphs in §8, `app/workers/pregame_worker.py`'s and `app/workers/postgame_worker.py`'s own module docstrings, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes (Phase 3E-8).

---

## v4.11 — 2026-08-18 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Phase 3F reconciliation (accepted 2026-08-18) identified two real, unclosed schema gaps from 3E: `players.team_id` has no history mechanism at all (a team change silently loses the prior membership), and `depth_chart_snapshots` (created 2026-08-07, never written to by any code) was designed `game_id`-keyed on a generic one-line Volume 3 description, but direct fixture inspection (`tests/fixtures/sportsdataio/depth_charts_normal.json`) confirms SportsDataIO's real DepthCharts payload is genuinely team-scoped with no game reference anywhere. Mac's Decisions 1 and 2 (3F reconciliation) approved fixing both.

**Decision:**
- **`roster_memberships` (new table), Decision 1/Option B:** `players.team_id` remains the fast/current team reference; `roster_memberships` is a separate, append-only historical record. Mirrors `team_stats`/`player_stats`' insert-on-change/latest-row convention (Phase 3E-8) applied to a new entity — a row is inserted only when the observed team differs from the player's latest known membership. First observation, a team change, and a rejoin are all the same case at the persistence layer ("observed != latest"); each just inserts a fresh row, no special-casing needed. Unlike `team_stats`/`player_stats`, this table carries the `block_snapshot_updates()` append-only trigger from creation, live-proven to reject an `UPDATE` against real dev Supabase. **Release/free-agent state is explicitly not representable**: `RosterAdapter.fetch_roster` only ever returns players currently on a roster, never an explicit release event, and this design does not infer one from a player's absence in a later fetch (that would require full-roster-diffing logic out of this phase's scope, with real false-positive risk from provider quirks or injured-but-still-rostered players).
- **`depth_chart_snapshots` corrected to team-scoped, Decision 2/Option A:** dropped and recreated as `(id, team_id references teams(id), depth_chart_data jsonb, captured_at)` — safe to drop/recreate rather than migrate in place, since the table had zero rows and zero writers under its original shape. Keeps the original odds_snapshots/injury_reports/weather_snapshots convention (one snapshot per capture, written unconditionally, no latest-row comparison) rather than team_stats/player_stats' different insert-on-change one, since it already carried (and keeps) the same append-only trigger those three siblings use. A future "depth chart as of game X" need should be derived from the latest team snapshot at/before that game's kickoff, not a second, competing game-keyed history table (Mac's explicit instruction) — deliberately not built this phase.
- **Durable roster ingestion pipeline (Decision 3):** `app.persistence.roster_ingestion.persist_roster` turns one team's `RosterAdapter.fetch_roster` result into `players`/`player_provider_ids` (via the existing `ensure_player`, unchanged), `roster_memberships`, and one `depth_chart_snapshots` row — wired into Master Refresh's existing per-team roster fetch loop, isolated the same way roster-fetch failures already are (one team's ingestion failure never blocks another team or `daily_game_intelligence` assembly). Identity is always provider-backed (`player_external_id`), never name-matched. A roster whose own team abbreviation has no `team_provider_ids` mapping writes nothing and reports every player as unresolved, rather than creating a player anchored to a null/guessed team.

**Alternatives considered:**
- A single combined `players.team_id` + separate history table where the history table also owns "current" (no separate fast column) — rejected; every existing reader already expects `players.team_id` to be the current-state column, and Decision 1 explicitly named keeping it as the fast lookup.
- Deriving depth-chart-as-of-game data by keeping the original `game_id`-keyed shape and populating it via a join at write time — rejected (Option B in the 3F reconciliation report); adds a derivation step nothing today needs, and doesn't match the real provider payload shape at all.
- Inferring player release/free-agency from roster-fetch absence — rejected; not safely derivable from a single team's roster pull without full-roster-diffing this phase does not build, and Mac's explicit instruction was not to fabricate roster transitions the provider data does not establish.

**Expected impact:**
- `app/persistence/roster_ingestion.py` and the two-table migration (`20260818070000_roster_memberships_and_depth_chart_redesign.sql`) are the real, tested implementation.
- No live SportsDataIO/The Odds API/WeatherAPI/NewsAPI/GNews calls anywhere in this phase's build or tests (SportsDataIO budget unchanged at 11 of 12); no hosted Redis provisioned; no Railway scheduler configured.
- Both new tables' schema and append-only protection were live-proven against real dev Supabase (`nhwjtsdebgiwskshzqiq`): controlled insert, `UPDATE` rejection confirmed, cleanup delete, plus a full first-observation → team-change lifecycle proof (old membership row confirmed untouched, `players.team_id` confirmed synced) — all live-proof rows removed afterward, dev Supabase left in its original state.
- `daily_game_intelligence.players` is unchanged this phase — still the raw roster-fetch passthrough, not yet reading from the new durable tables; that reconciliation is explicitly 3F-4's job, not silently pulled forward.
- MINOR, Volume-3-only bump: one corrected table (safe, zero-row drop/recreate) and one new additive table; no existing data touched.

**Full technical detail:** This entry, plus the new `roster_memberships`/corrected `depth_chart_snapshots` paragraphs in Volume 3 §4.0, `app/persistence/roster_ingestion.py`'s own module docstring, the migration's own inline comments, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes (Phase 3F-1).

---

## v4.12 — 2026-08-18 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Phase 3F-3's two approved items: (1) close the `team_stats`/`player_stats` DB-level append-only gap Volume 3 has flagged since 3E-8 (application-layer correction-aware logic was already correct — insert new row on change, never touch the old one — but nothing at the database level prevented a different, less careful writer from issuing a destructive `UPDATE`); (2) surface `games.venue_lat`/`.venue_long`/`.venue_type` (stored since 3E-6/v4.9, never read back anywhere) into `daily_game_intelligence.stadium`, which previously exposed only `name`.

**Decision:**
- **`team_stats`/`player_stats` gain `block_snapshot_updates()`, reused verbatim** — the same function `odds_snapshots`/`injury_reports`/`weather_snapshots`/`depth_chart_snapshots`/`referee_assignments` already carry. No uniqueness constraint added (would have blocked the correction-row INSERTs the existing application logic depends on — a correction is a second, later row for the same `(game,team)`/`(game,player)` pair, by design); only `UPDATE` is blocked, `INSERT` remains completely unrestricted. Live-proven against real dev Supabase: a controlled `UPDATE` attempt on both tables was rejected (`P0001: ... is append-only and cannot be modified`), a subsequent correction `INSERT` still succeeded, the original row was confirmed unchanged — all proof rows removed afterward.
- **`daily_game_intelligence.stadium` shape:** `{"name", "latitude", "longitude", "venue_type"}`, each field independently `null` when the underlying `games` column is `null` (never fabricated), the whole value `null` only when nothing about the venue is known at all — matching every other category's existing "no data → null" convention in this table. Assembled by one new pure helper, `app.master_refresh.game_refresh._build_stadium` — the single already-shared per-game refresh path both Master Refresh's daily run and Pregame Worker's targeted T-minus-5 refresh call, so both pick up the new shape from one change, no duplicate assembly logic anywhere.
- **Travel remains explicitly deferred, unaffected by this phase** — this is current-state venue metadata surfacing, not the travel-distance calculation v4.5/v4.9's notes already describe as still not built.

**Alternatives considered:**
- Adding a uniqueness constraint on `team_stats`/`player_stats` alongside the trigger, for a stronger "one row per pair" guarantee — rejected; that is a fundamentally different design (would force an UPSERT-then-history pattern) than the correction-history-as-multiple-rows design already built and tested in 3E-8, and would have broken the existing correction-INSERT behavior outright.
- Building a dedicated `stadiums` reference table or a `daily_game_intelligence.travel`-style distance calculation as part of this phase — rejected; out of 3F-3's explicit two-item scope, travel stays deferred per Mac's explicit instruction.

**Expected impact:**
- `supabase/migrations/20260818080000_team_stats_player_stats_append_only.sql`, `app/master_refresh/game_refresh.py`'s new `_build_stadium`, and the tests in `tests/test_team_stats_persistence.py`/`tests/test_player_stats_persistence.py`/`tests/test_game_refresh.py`/`tests/test_master_refresh.py`/`tests/test_pregame_worker.py` are the real, tested implementation.
- No live SportsDataIO/The Odds API/WeatherAPI/NewsAPI/GNews calls anywhere in this phase's build or tests (SportsDataIO budget unchanged at 11 of 12); no hosted Redis provisioned; no Railway scheduler configured.
- MINOR, Volume-3-only bump: one purely additive trigger pair (no column change, no existing data touched) and one documented jsonb shape addition to an already-existing column.

**Full technical detail:** This entry, plus the new trigger comment block and `stadium` shape paragraph in Volume 3 §4.0/§4.1, `app/master_refresh/game_refresh.py`'s own `_build_stadium` docstring, the migration's own inline comments, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes (Phase 3F-3).

---

## v4.10 — 2026-08-18 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Mac's review of new SportsDataIO provider documentation confirmed the full 9-value game status vocabulary and upgraded `"Final"` from ASSUMED to CONFIRMED (logged separately, no CHANGELOG bump needed for that alone). That review's own required inspection step (Postgame Worker + status normalization, before any change) surfaced a real, then-unfixed architectural gap: `_SCHEDULE_STATUS_MAP` recognized only 2 of the 9 documented statuses. `"F/OT"` (completed overtime) never reached `"final"` at all — Postgame Worker would never detect an overtime game as final. More severely, any of the other 7 unmapped values — most critically `"InProgress"`, which every live game passes through — raised `ProviderDataError` from `fetch_schedule` in a way that was not row-isolated, aborting the *entire* full-season Schedule fetch and cascading to fail the whole Master Refresh or Postgame Worker run. Reported and stopped on in a prior turn; Mac reviewed the finding and approved the fix this turn.

**Decision:**
- **`_SCHEDULE_STATUS_MAP` expanded to all 9 documented values**, each mapped to this project's existing 5-value internal vocabulary (`scheduled`/`live`/`final`/`postponed`/`canceled` — the `games.status` check constraint, confirmed sufficient by direct inspection, not widened): `Scheduled`→`scheduled`, `InProgress`→`live`, `Final`→`final`, `F/OT`→`final`, `Postponed`→`postponed`, `Canceled`→`canceled`, `Delayed`→`scheduled` (Mac's reasoning: hasn't started, still expected to be played — closest existing state), `Suspended`→`live` (play began, temporarily halted — closest existing state), `Forfeit`→`final` (a completed result).
- **Row isolation in `SportsDataIOScheduleAdapter.fetch_schedule`**: a single row's normalization failure (unrecognized status/season_type/venue_type, or a structurally malformed row) is now logged (`_logger.warning`, includes the raw `GameKey`/`Status` for debugging) and skipped, rather than raising for the whole batch. Every other valid row in the same response still becomes a `ScheduleEntry`. HTTP failure, invalid top-level JSON, or a non-array payload still fail the whole call, unchanged — those happen before the per-row loop starts. This is a deliberate, tested resilience behavior, not silently swallowed data loss: skipped rows are always observable via logs and covered by tests proving the isolation.
- **`app.master_refresh.run`'s own failure-isolation documentation corrected** to match: Schedule row-level malformation moved from the BLOCKING list to the NON-BLOCKING list, since the adapter itself now absorbs it before this worker ever sees it.

**Alternatives considered:**
- Mapping `Suspended`/`Delayed`/`Forfeit` to new, dedicated internal status values (widening the `games.status` check constraint) — rejected; direct inspection confirmed the existing 5-value vocabulary already has a semantically correct closest state for each (`live`/`scheduled`/`final` respectively), so widening the constraint would have been an unnecessary schema change for no functional gain.
- Leaving `fetch_schedule` batch-fatal on any per-row failure and only fixing the map — rejected; the map alone doesn't fix the underlying availability risk (a single future unrecognized value, or any genuinely malformed row, would still take down the whole fetch), which was found to be the more severe half of the original report.

**Expected impact:**
- `app/adapters/providers/sportsdataio.py` (map + row isolation), `app/master_refresh/run.py` (docstring correction), and the tests in `tests/adapters/test_sportsdataio_adapters.py`, `tests/test_master_refresh.py`, and `tests/test_postgame_worker.py` are the real, tested implementation.
- `"F/OT"` and `"Final"` are now regression-tested to both reach Postgame Ingestion identically. A mixed-status Schedule batch (valid games alongside `InProgress`/unrecognized rows) no longer fails Master Refresh or Postgame Worker — also regression-tested.
- No live SportsDataIO/The Odds API/WeatherAPI/NewsAPI/GNews calls anywhere in this phase's build or tests (SportsDataIO budget unchanged at 11 of 12); no hosted Redis provisioned; no Railway scheduler configured.
- MINOR, Volume-2-only bump: corrects worker-behavior documentation and closes a real availability/correctness gap; no schema change (Volume 3 unaffected).

---

## v4.13 — 2026-08-18 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Mac's explicit "Data Dictionary reconciliation" request — a strict inspect-first sweep of every provider adapter's data handling, no code changes until conflicts were presented. That inspection found the exact same batch-fatal-on-one-row defect the v4.10 Schedule fix had just closed, independently present in six more places: `TheOddsApiOddsAdapter.fetch_odds`, `TheOddsApiPlayerPropsAdapter.fetch_player_props`, `SportsDataIOTeamStatsAdapter.fetch_team_stats`, `SportsDataIOPlayerStatsAdapter.fetch_player_stats`, `SportsDataIORosterAdapter.fetch_roster`, and `_get_depth_chart_lookup`. Mac reviewed the inspection report and approved the corrective pass with an explicit priority order and a core rule: a malformed provider row must not destroy otherwise valid data from the same response or batch.

**Decision:**
- **`fetch_odds` (two isolation tiers):** a malformed event (missing `id`/teams/`commence_time`) is logged and skipped; a malformed market within an otherwise-valid event is logged and skipped, that event's other valid markets still process. Previously, one bad event or market anywhere in the bulk multi-game response aborted every game in that response.
- **`fetch_player_props` (three isolation tiers):** a malformed per-game event response is logged and skipped, moving to the next `game_id`; a market with no usable `outcomes` is logged and skipped; a malformed individual outcome is logged and skipped, that market's other valid Over/Under pairs still process. **Known characteristic, not a defect, documented rather than silently accepted:** because a `PlayerProp` is inserted into the grouping dict before its `over_odds`/`under_odds` assignment runs, a malformed field that fails *after* that insertion (e.g. a missing `price` on the first outcome seen for a given bookmaker/market/player/point key) leaves that prop in the result with the affected side still `None`, rather than removing the entry outright — consistent with the model's own optional-field design and the project's null-not-neutral convention, not fabricated data.
- **`fetch_team_stats`/`fetch_player_stats` (two-stage isolation):** because `rows` is the whole week's bulk payload shared across every game via `_WeeklyBulkCacheMixin`, a malformed row could previously abort the fetch for *every* game that week, not just the one requested — the most severe instance found. Fixed with a filtering stage (isolates malformed rows while narrowing to the requested game) followed by a model-building stage (isolates malformed rows while constructing `TeamStatLine`/`PlayerStatLine` objects), each logging and skipping independently.
- **`fetch_roster`/`_get_depth_chart_lookup` (single-tier per-row isolation):** a malformed player row or depth-chart entry is logged and skipped; every other valid row in the same response still returns.
- **Unchanged, per Mac's explicit scope boundary:** HTTP failure, invalid top-level JSON, and non-array/non-object payloads still fail the whole call in every adapter (`_get`/`_parse_json_array`/`_parse_json_object` untouched). `_SEASON_TYPE_MAP`, `_VENUE_TYPE_MAP`, and `InjuryReport.status` vocabulary were left unchanged — no repo-existing provider documentation conclusively established any missing value. No live provider calls were made; the SportsDataIO Free Trial budget is unchanged at 11 of 12.

**Alternatives considered:**
- Leaving the ghost-partial-`PlayerProp` behavior as an unstated side effect of the fix — rejected; it is real, observable output behavior a future reader could mistake for a bug, so it is documented explicitly in code-adjacent PROVENANCE rather than left implicit.
- Reordering `fetch_player_props`' outcome-processing so a `PlayerProp` is only inserted into `grouped` after all its fields are known to be valid, eliminating the ghost-partial case entirely — rejected as out of this pass's scope; that is a deeper semantic change to the model-building order, not a row-isolation fix, and risked exceeding the corrective pass's explicit boundaries.
- Treating `player_stats_nfl` wiring as in-scope "Data Dictionary" cleanup since it surfaced in the same inspection sweep — rejected per Mac's explicit instruction to STOP and report on that item separately before any schema/persistence change, addressed as its own deliverable, not folded into this entry.

**Expected impact:**
- `app/adapters/providers/the_odds_api.py` and `app/adapters/providers/sportsdataio.py` (row isolation across all six methods listed above) and the tests in `tests/adapters/test_the_odds_api_odds_adapter.py`, `tests/adapters/test_sportsdataio_adapters.py`, and `tests/test_postgame_worker.py` are the real, tested implementation — 12 new/rewritten tests proving mixed valid/malformed responses preserve valid data while genuine top-level failures still behave correctly.
- No live SportsDataIO/The Odds API/WeatherAPI/NewsAPI/GNews calls anywhere in this phase's build or tests (SportsDataIO budget unchanged at 11 of 12); no hosted Redis provisioned; no Railway scheduler configured.
- MINOR, Volume-2-only bump: closes a real availability/correctness gap across six adapter methods; no schema change (Volume 3 unaffected), no provider vocabulary expanded.

**Full technical detail:** This entry, plus the "Row isolation" sections appended to `tests/fixtures/the_odds_api/PROVENANCE.md` and `tests/fixtures/sportsdataio/PROVENANCE.md`, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes (Data Dictionary reconciliation corrective pass).

---

## v4.12.1 — 2026-08-18 — PATCH

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** The Data Dictionary reconciliation's inspection phase surfaced `player_stats_nfl` as a real, previously-undocumented Blueprint-vs-reality gap: the table has existed since v4.0 but no code anywhere in this codebase has ever written to it. Rather than leave it silently orphaned, Mac reviewed the STOP-and-report recommendation (Volume 3's own extension-table rationale is purely about multi-sport column bloat, irrelevant at NFL-only scope; no Volume 4/5 documented consumer; the typed table covers only 5 of ~100+ real fields, so jsonb remains necessary regardless; wiring both would add a genuine duplicate-source-of-truth risk) and confirmed it.

**Decision:** `player_stats_nfl` stays **UNWIRED, DEFERRED** — schema unchanged, not dropped, no code writes to it. `player_stats.stats` jsonb is confirmed as the source of truth for NFL player statistics. §4.0 gains a "Status" note directly below the table's existing "Why extension tables" rationale, recording the decision, its four-point rationale, and the concrete conditions that would justify revisiting it (multi-sport expansion actually beginning, a concrete documented downstream consumer needing typed/indexed access, or a demonstrated query-performance requirement — not preemptively).

**Alternatives considered:** Wiring `player_stats_nfl` now on the theory that "it's already built, might as well populate it" — rejected; a currently-undemonstrated benefit against a real, immediate dual-write-consistency cost is the wrong trade, and doing so during a documentation/reconciliation pass rather than a deliberate architectural decision would have been exactly the kind of undocumented drift this changelog exists to prevent. Dropping the table outright — rejected; a future NFL-specific typed need remains plausible, and the table costs nothing sitting empty.

**Expected impact:**
- No code, schema, or persistence change — this is a documentation-only PATCH closing a real gap between what the Blueprint implied (an active extension table) and what the codebase actually does (never writes to it).
- Any future PlayerStats-related work should continue treating `player_stats.stats` jsonb as authoritative and complete; `player_stats_nfl` requires no maintenance and should not be silently wired up as a side effect of unrelated work.

**Full technical detail:** This entry, plus the new "Status" paragraph in Volume 3 §4.0 directly below `player_stats_nfl`'s table definition, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-18 notes.

---

## v4.14 — 2026-08-19 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Phase 3F-4 (`daily_game_intelligence` reconciliation audit), scoped since 3F-1's own close: `daily_game_intelligence.players` was still the raw roster-fetch passthrough, never reading anything from the durable `players`/`roster_memberships`/`depth_chart_snapshots` tables 3F-1 built. Mac's own inspect-and-report checkpoint confirmed the gap and approved a minimal reconciliation (Option A) over a full durable-table read path (Option B), per an explicit tradeoff analysis: Option A preserves the freshest-possible roster data and costs zero extra per-team/per-game round trips (the same in-memory fetch already feeds both the working table and the durable tables); Option B would have added real round-trip cost for a benefit Option A delivers just as well.

**Decision:**
- **`app.master_refresh.game_refresh._enrich_roster`** (new) adds the resolved internal `players.id` to each roster entry passed into `daily_game_intelligence.players`, alongside every field already exposed (`team`/`player_external_id`/`player_name`/`position`/`depth_chart_rank`, unchanged). No redesign of the rest of the payload.
- **`app.master_refresh.run.run_master_refresh`** resolves the mapping via **one batched `player_identity.resolve_player_ids` call for the entire slate**, run once after every team's `persist_roster` attempt (not per-team, not per-player -- no N+1). A player absent from the mapping (never durably ingested, or this cycle's `persist_roster` failed before reaching them) gets `player_id: null` -- never fabricated, never name-matched. A failure of the batched lookup itself is non-blocking (`MasterRefreshResult.player_id_resolution_failed`): fresh roster data still reaches `daily_game_intelligence.players`, just with every `player_id` left null that cycle.
- **Pregame Worker's call site needed no change** -- it already reads back whatever Master Refresh last wrote (`read_existing_players`), so the enrichment carries forward automatically without a second identity resolution.
- **A real, pre-existing exception-isolation gap found and reported, not fixed.** `persist_roster` calls `ensure_player`/`resolve_player_ids`/`resolve_team_ids` without catching their own exception types (`PlayerIdentityError`, `TeamIdentityError`); only `RosterIngestionError` is actually isolated by `run_master_refresh`. Confirmed by direct test execution (not just static reading): a `PlayerIdentityError` from `ensure_player` crashes the whole `run_master_refresh` call rather than being isolated per-team as the module's own comments describe. Out of 3F-4's explicit scope to fix -- flagged for Mac's decision.

**Alternatives considered:**
- Full durable-table read path (Option B) -- rejected per Mac's explicit approval of Option A; would have added a per-team/per-game query cost the existing in-memory `rosters` dict doesn't need, for a benefit (internal `player_id`) Option A delivers without it.
- Reordering `_enrich_roster`'s resolution to run before `persist_roster` so it could avoid the "possibly-stale" framing -- rejected; running it after is what lets a brand-new player's just-created mapping resolve within the same cycle, which running before would miss entirely.
- Silently fixing the `PlayerIdentityError`/`TeamIdentityError` isolation gap discovered while testing -- rejected; out of 3F-4's explicit "complete 3F-4 only" scope, reported instead per this project's stop-and-flag discipline.

**Expected impact:**
- `app/master_refresh/game_refresh.py` (`_enrich_roster`, widened `refresh_daily_game_intelligence_for_game` signature), `app/master_refresh/run.py` (batched resolution, widened `MasterRefreshResult`), and 15 new tests across `tests/test_game_refresh.py`/`tests/test_master_refresh.py` are the real, tested implementation -- covering resolved/unresolved/mixed players, the persist_roster-failure case (fresh data preserved, `player_id` not fabricated), batching (one query for a 4-team/4-player slate, not four), the lookup-failure-is-non-blocking case, and both Master Refresh's and Pregame Worker's call sites.
- Live dev-Supabase proof (`nhwjtsdebgiwskshzqiq`): a durably-linked player resolved to its real internal `players.id` via the exact batched-query shape; a never-linked player correctly resolved to nothing (no fabrication); both round-tripped correctly through a real `daily_game_intelligence` row; all proof rows removed afterward, dev state confirmed returned to its exact prior counts.
- No live SportsDataIO/The Odds API/WeatherAPI/NewsAPI/GNews calls anywhere in this phase's build or tests (SportsDataIO budget unchanged at 11 of 12); no hosted Redis provisioned; no Railway scheduler configured; no schema change (Volume 3 unaffected -- `daily_game_intelligence.players` is jsonb, already permissive of the new key).
- MINOR, Volume-2-only bump: closes the 3F-4 gap named at 3F-1's close; surfaces (does not fix) one real exception-isolation defect for a separate decision.

**Full technical detail:** This entry, plus the new "`daily_game_intelligence.players` reconciliation" and exception-isolation-gap paragraphs in Volume 2 §8, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-19 notes (Phase 3F-4).

---

## v4.15 — 2026-08-19 — PATCH

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Fixes the exception-isolation gap v4.14's `daily_game_intelligence.players` reconciliation work surfaced and reported (not fixed, per that substep's explicit "complete 3F-4 only" scope). Mac reviewed the finding and approved the smallest safe fix as the prerequisite for 3F-5.

**Decision:** `run_master_refresh`'s per-team `try: await persist_roster(roster_response) except RosterIngestionError` boundary widened to `except (RosterIngestionError, PlayerIdentityError, TeamIdentityError)` -- the two additional exception types `persist_roster` can actually raise via its calls into `player_identity`/`team_identity`, caught at the exact same per-team boundary `RosterIngestionError` already used. No generic `except Exception`, no change to `persist_roster` itself, no fabricated identity on failure -- a failed team's `player_id` still correctly resolves to `null` in `daily_game_intelligence.players`, never guessed.

**Alternatives considered:**
- Having `persist_roster` itself catch `PlayerIdentityError`/`TeamIdentityError` internally and re-raise as `RosterIngestionError` -- rejected as a slightly larger change (touches `roster_ingestion.py`, not just the orchestration boundary) for the same observable effect; the orchestration-level fix is the smaller, safer change and keeps each module's own exception type meaningful to its own callers.
- Catching generic `Exception` at this boundary -- explicitly rejected per Mac's instruction; would silently swallow genuine programming errors alongside the two known identity-failure classes, confirmed still-propagating via a dedicated test.

**Expected impact:**
- `app/master_refresh/run.py` (widened except clause + docstring correction) and 3 new tests in `tests/test_master_refresh.py` (`PlayerIdentityError` isolation, `TeamIdentityError` isolation, unrelated-exception-still-propagates) are the real, tested implementation. 454/454 full regression passing (451 pre-existing + 3 new).
- No live SportsDataIO/The Odds API/WeatherAPI/NewsAPI/GNews calls; no hosted Redis; no Railway scheduling; no schema change.
- PATCH, Volume-2-only: corrects a real availability defect in already-shipped 3F-4/3F-1 orchestration code; no new capability, no architecture change.

**Full technical detail:** This entry, plus the corrected exception-isolation-gap paragraph in Volume 2 §8, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-19 notes (Phase 3F-5 prerequisite fix).

---

## v4.16 — 2026-08-19 — MINOR

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** Phase 3 acceptance closure, gaps #1/#2 of the 4 identified at 3F-5's close (Mac's explicit instruction: proceed only with these two; #3/#4 stay deferred). Gap #1: `app/adapters/cache.py` had no cache hit-rate metric at all, despite Volume 2 §8's own acceptance criterion #3 requiring one. Gap #2: the Sunday-slate load/concurrency test (Phase 3B) only ever covered Odds/Player Props, predating every SportsDataIO-adapter worker and the Pregame/Postgame Workers built since.

**Decision:**
- **Cache metrics, instrumented at `CachingAdapter` (the one call-site every backend shares), not per-backend.** `CacheMetrics` (hits/misses/sets) is owned per-`CachingAdapter` instance -- since every worker already constructs one instance per category, per-category independence is inherent, not a special case. A `hit` is `CacheBackend.get` returning non-`None`; a `miss` is `None` for any reason (new key, expiry, or a fail-open read error); a `set` is one write *attempt*, not a confirmed durable write. `hit_rate` returns `None` at zero samples, never a fabricated percentage. A separate `CacheBackend.errors` counter (incremented only by `RedisCacheBackend`'s own existing exception handling; `InMemoryCacheBackend` has no failure mode) tracks backend-level fail-open events distinctly from ordinary misses. Purely additive -- zero change to existing cache-aside semantics, confirmed by a dedicated test re-running the miss/hit/expiry sequence and checking actual returned values, not just counters.
- **Full-fleet load extension, same ~13-game Sunday-slate scale as the original 3B test, new file (`tests/test_load_concurrency_full_fleet.py`), not a rewrite of the original.** Covers Injury Worker (bulk stays one call), Weather Worker (per-game bounded, one provider failure isolated), News Worker (calls scale with distinct teams, not games), Master Refresh (Schedule/DepthCharts bulk stay one call, Roster bounded to 26 distinct teams, one team's identity-write failure isolated at full-league scale), SportsDataIO TeamStats (weekly-bulk stays one call across a 13-game week), and Pregame Worker (5 simultaneous triggers stay bounded to those 5 games, not a full-slate rescan). Explicitly classified **INTERNAL PIPELINE LOAD PROVEN**, not production provider throughput/rate-limit proof -- fixtures/fakes only, zero live provider calls, same discipline as the original 3B test.
- **A real efficiency finding surfaced while building the Postgame Worker load test, documented not fixed, per explicit scope.** `_ingest_final_stats_for_game` constructs a fresh `SportsDataIOTeamStatsAdapter`/`SportsDataIOPlayerStatsAdapter` per game with no shared `cache_backend` -- proven at scale: 5 games from the same week finalizing in the same Postgame Worker cycle produce 5 redundant identical weekly-bulk fetches instead of 1. Correctness is unaffected (each game's own rows still filter correctly from each redundant response); only the "download once, reuse everywhere" principle is not followed here. Flagged for a future decision.

**Alternatives considered:**
- Instrumenting metrics inside each `CacheBackend` subclass instead of at `CachingAdapter` -- rejected; would produce two different hit/miss definitions to reconcile (or duplicate bookkeeping) instead of one consistent one at the single shared call-site, per Mac's own explicit preference.
- Silently fixing the Postgame Worker bulk-reuse finding as part of this pass -- rejected; out of the explicit "gaps #1/#2 only" scope, reported instead per this project's stop-and-flag discipline.
- Extending the original `tests/test_load_concurrency.py` in place rather than adding a new file -- rejected; that file's own scope (Odds/Player Props specifically) is still valid and complete, a new file for the newer categories keeps each file's own docstring/scope claim accurate rather than overloading one file with an ever-growing, harder-to-navigate mixed scope.

**Expected impact:**
- `app/adapters/cache.py` (`CacheMetrics`, `CacheBackend.errors`, `CachingAdapter.metrics`/`.errors`) and `tests/test_load_concurrency_full_fleet.py` (new, 9 tests) plus extended assertions in `tests/adapters/test_cache_boundary.py`/`tests/adapters/test_redis_cache_backend.py` (4 new tests) are the real, tested implementation. 467/467 full regression passing (454 pre-existing + 13 new).
- No live SportsDataIO/The Odds API/WeatherAPI/NewsAPI/GNews calls; SportsDataIO budget unchanged at 11/12; no hosted Redis provisioned; no Railway scheduling configured; no schema change.
- Phase 3 acceptance criteria now stand: gaps #1 (cache hit-rate measurability) and #2 (full-fleet load coverage) CLOSED; gap #3 (live-cadence freshness) DEFERRED -- RUNTIME SCHEDULING; gap #4 (Time Machine/`recommendation_snapshots` separation) DEFERRED -- PHASE 5 DEPENDENCY. Neither deferred item is a failure -- both are structurally blocked on work outside Phase 3's own scope, per Mac's explicit classification.
- MINOR, Volume-2-only bump: closes two real acceptance-criteria gaps with new capability (measurable cache metrics) and new test coverage; no schema change, no architecture change.

**Full technical detail:** This entry, plus the new "Cache metrics" and "Full-fleet load acceptance" paragraphs in Volume 2 §8, and the completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-19 notes (Phase 3 acceptance closure).

**Corrective note (2026-08-19):** this changelog file was found, in the course of this entry, to carry a stray orphan "Full technical detail" fragment at its prior end (a leftover from an earlier edit in this same session that duplicated part of the v4.10 entry's own closing line without a heading). Removed here as a documentation-accuracy correction — no version bump of its own, since it was never a real entry.

---

## v4.16.1 — 2026-08-19 — PATCH

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** DEMO-1 (isolation foundation) of the approved Demo/Simulation Environment (`docs/blueprint/demo-simulation-environment.md`, approved by Mac 2026-08-19 with five decisions). A fourth Railway environment and isolated Supabase project needed to exist, with structural — not conventional — protection against a demo deployment ever reaching real data or a real deployment ever reaching demo data.

**Decision:**
- **New Railway environment `demo`**, same `theplaybook` project, isolated from dev/staging/production by never sharing variables or a database.
- **New Supabase project `theplaybook-demo`** (`tbxzecbopoxcexggesmk`, org `ywghsgpylgeajjgmuuow`, region `us-east-1`, $10/month, cost confirmed and approved before creation), given the exact same 17-migration set dev/staging/production draw from.
- **Genuine pre-existing gap discovered and resolved for demo only:** the 17 checked-in migrations create the `sports`/`leagues`/`teams` tables but never insert the `sports`/`leagues` rows or the original 6 teams (Kansas City Chiefs, Buffalo Bills, San Francisco 49ers, Philadelphia Eagles, Dallas Cowboys, Baltimore Ravens) that dev's own schema has today — those were seeded into dev at some point outside the tracked migration history, using deliberately fixed, human-readable UUIDs (`a2000000...`/`a3000000...`) and synthetic `external_provider_id` placeholders (`seed-kc` etc.). Two downstream migrations (`team_provider_ids_backfill`, `team_provider_ids_sportsdataio_full_coverage`) depend on this seed and silently no-op (zero rows, no error) without it; a third (`expand_nfl_teams_and_provider_ids`) hard-fails outright on a null `league_id`. Replicated the identical bootstrap into `theplaybook-demo` (same fixed IDs, same public NFL team names/synthetic placeholders as dev) as an explicit, separately-named, documented step — not a checked-in migration file, since it fills a gap in the *existing* migration history rather than adding new schema. This is reference/taxonomy data, not real operational data, so it does not conflict with the "no copied data from dev" isolation requirement. **Recommended, not unilaterally decided:** a proper migration should be added to the repo to close this gap for every future environment, not just demo — flagged for Mac, separate from Demo Mode's own scope.
- **Structural startup isolation guard**, `app/environment_safety.py`'s `assert_demo_isolation`, wired into `app/main.py` before Sentry init and `FastAPI()` construction: hard-fails if `RAILWAY_ENVIRONMENT_NAME=demo` and `SUPABASE_URL` doesn't contain the demo project's ref, and the reverse (non-demo environment pointed at the demo project). No warn-and-continue path either direction, per Mac's explicit instruction.
- **Zero provider credentials configured on `demo`** — no SportsDataIO/The Odds API/WeatherAPI/NewsAPI/GNews/Twilio/Telegram keys, matching Decision 6 of the approval. `SUPABASE_SERVICE_ROLE_KEY` also intentionally not yet requested from Mac, since nothing deployed in DEMO-1 needs to write to Postgres yet (`/health` returns a static payload) — least-privilege, requested only when DEMO-2/DEMO-3 actually need it.
- **No hosted Redis, no dedicated Railway token, no Sentry DSN configured for `demo`** at this stage, per Decisions 7/8/9 of the approval — `InMemoryCacheBackend` and the existing shared deploy-token pattern are sufficient until a concrete need proves otherwise.

**Alternatives considered:** none new — this entry implements the isolation model, credential policy, and Redis/Sentry/token defaults already decided and approved in the Demo/Simulation Environment design document; no fresh architectural choice was made here beyond the migration-gap bootstrap approach (data-only bootstrap vs. a new checked-in migration file — bootstrap chosen for DEMO-1 itself, new migration recommended as separate follow-up).

**Expected impact:**
- `apps/sports-intel-layer/app/environment_safety.py` (new), `apps/sports-intel-layer/app/main.py` (guard wired in), `apps/sports-intel-layer/tests/test_environment_safety.py` (new, 15 tests) — 482/482 full regression passing (467 pre-existing + 15 new), zero regressions.
- New infrastructure: 1 Railway environment, 1 Supabase project ($10/month, confirmed and approved).
- **Closing update (2026-08-19):** Mac manually completed the one step no available tool could safely perform (a service's first deployment into a brand-new environment — confirmed by `railway-agent` itself declining, since its only deploy tool takes no environment parameter). `sports-intel-layer` is now live in `demo` (deployment `1c790e82`, commit `72bf7a0`, root directory `/apps/sports-intel-layer`, matching dev/staging/production's source exactly except for one noted build-path difference — `RAILPACK` vs. their `DOCKERFILE`/`Dockerfile`, not a blocker). The isolation guard's live pass is evidenced by a clean, complete, exception-free uvicorn startup in the deployment's own runtime logs — a mismatch would have crashed the import before any of those lines could log. A literal HTTP `/health` response was not independently captured (this session's own outbound network policy blocked the generated domain; not evidence of an application problem). DEMO-1 is closed — see PROGRESS.md's 2026-08-19 closing entry for the full evidence trail, with unit/CI proof, live Railway proof, and live Supabase proof kept explicitly distinct.
- No provider calls of any kind; SportsDataIO budget unchanged at 11/12; no schema change to dev/staging/production; no data of any kind copied from dev/staging/production/real users into demo.
- PATCH, Volume-2-only bump: a new environment and a structural safety mechanism, not a change to any existing environment's behavior or any cross-volume architecture.

**Full technical detail:** This entry, plus the new "Fourth environment: `demo`" paragraph in Volume 2 §5, and the DEMO-1 completion report delivered to Mac. Also logged operationally in `PROGRESS.md`'s 2026-08-19 notes.

---

## v4.16.2 — 2026-08-20 — PATCH

**Volume affected:** Volume 2 (System Architecture) only.

**Reason:** A pre-existing production bug in `app/persistence/daily_game_intelligence.py`, discovered incidentally while building DEMO-3 (the Demo Scenario Engine) — not a Demo-specific defect. `build_payload`'s player-props branch called `_freshness_status(..., category="props")`, but `CATEGORY_TTL_SECONDS` (`app/adapters/cache.py`) only defines the category as `"player_props"` (matching `app.adapters.models.DataCategory.PLAYER_PROPS`). The mismatch produced an unconditional `KeyError: 'props'` any time `daily_game_intelligence` assembly ran for a game that had an actual player-prop odds snapshot on file — a live-impacting defect in already-deployed code, never caught before because every pre-existing test in `tests/test_daily_game_intelligence_assembly.py` happened to pass `props_row=None`. Flagged to Mac before any fix was applied, per this project's stop-and-report discipline for real production defects found outside a task's own approved scope; Mac reviewed and approved fixing it immediately, with a required regression test and a search for other instances of the same naming mismatch.

**Decision:**
- `build_payload`'s props `_metadata(...)` call site: `category="props"` → `category="player_props"`.
- The co-located `_DEFAULT_VENDOR` lookup dict (used by the same `category` argument, for the assembled metadata's `source` field) had its `"props"` key renamed to `"player_props"` to match — both dicts are keyed by the identical `category` value passed into `_metadata`, so leaving one unrenamed would have just moved the `KeyError` rather than fixing it.
- Searched the full `apps/sports-intel-layer` codebase for any other `category="props"` / `CATEGORY_TTL_SECONDS["props"]` occurrence — none found; this was the only call site with the mismatch.
- No alias added to `CATEGORY_TTL_SECONDS` for backward compatibility — direct inspection found no other real caller depends on a bare `"props"` key, so an alias would only have hidden the bug's real cause rather than fixing it, per Mac's explicit instruction.

**Alternatives considered:**
- Adding `"props"` as a second key in `CATEGORY_TTL_SECONDS` pointing at the same TTL value, instead of renaming the call site — rejected per Mac's explicit instruction, since it would paper over the naming inconsistency rather than correcting it, and nothing else in the codebase actually needs a `"props"` key.
- Leaving the bug unfixed and working around it only inside DEMO-3's own scenario (e.g. never letting a props snapshot exist when Pregame Worker's targeted refresh runs) — rejected; this is a real production defect independent of Demo Mode, and DEMO-3's own approved scope is to exercise the *real* pipeline, not a pipeline with a known bug quietly routed around.

**Expected impact:**
- `apps/sports-intel-layer/app/persistence/daily_game_intelligence.py` (two-line fix, with an explanatory comment on `_DEFAULT_VENDOR` recording why the two dicts must share the same category vocabulary) and one new regression test, `tests/test_daily_game_intelligence_assembly.py::test_props_row_present_assembles_without_raising` (asserts the corrected payload's `props.status`/`props.source`, that `CATEGORY_TTL_SECONDS["player_props"]` genuinely drives the freshness computation — verified by mutating it and observing the status flip — and that the old `category="props"` value still raises `KeyError`, so the fix isn't a coincidental pass).
- Full regression suite green after the fix (561/561, including this new test and DEMO-3's own new tests from the same work session).
- No live SportsDataIO/The Odds API/WeatherAPI/NewsAPI/GNews calls; no schema change; no Railway/Supabase infrastructure mutation; dev/staging/production untouched (a code-only fix, not yet deployed as of this entry).
- PATCH, Volume-2-only bump: corrects a real availability defect in already-shipped 3E-2/3E-8 assembly code; no new capability, no architecture change, no schema change.

**Full technical detail:** This entry, plus `PROGRESS.md`'s 2026-08-20 DEMO-3 entry (which documents this fix as a dated sub-note distinct from DEMO-3's own narrative, per Mac's instruction) and the DEMO-3 completion report delivered to Mac.

---

## v5.0 — 2026-08-20 — MAJOR

**Volumes affected:** Volume 2 (System Architecture, §8) and Volume 4 (AI Intelligence, new §1.1). CLAUDE.md unaffected — no change to phase-gating, credential policy, or working conventions.

**Reason:** A real commercial finding, not a planning-stage foresight item: SportsDataIO quoted approximately $10,000-$15,000 per NFL season for the collection of feeds Volume 2 §8's original vendor table assumed The Playbook would license directly for stats/injuries/rosters/schedules. Mac's decision, delivered as a combined business-and-architecture directive: do not make that purchase at this stage, and prevent the sourcing gap from derailing Phase 4 by replacing the assumption "every intelligence field comes from a purchased provider" with a multi-source + internally-derived-intelligence strategy — buy/ingest raw facts only where genuinely necessary, calculate deterministically whatever the product's own already-held data supports, and reserve the AI layer strictly for reasoning/interpretation, never fact-fabrication or manual arithmetic. This is exactly the kind of decision Section 1 of CLAUDE.md's "if the Blueprint and reality disagree" process anticipates — a real-world cost constraint discovered mid-build, requiring a documented resolution rather than silent improvisation or an undocumented pivot.

**Decision:**
- **SportsDataIO purchase declined for now, adapter architecture retained.** No code removed; `SportsDataIOScheduleAdapter`/`RosterAdapter`/`TeamStatsAdapter`/`PlayerStatsAdapter`/`InjuryAdapter` and every fixture/test built against them (Phase 3C-ii, 3E) stay exactly as shipped. SportsDataIO remains documented as a candidate future premium/consolidated provider, reconsidered only if revenue and provider reliability/coverage/latency/operational-simplicity trade-offs later justify it — never silently ruled out permanently.
- **V1 candidate source architecture (Volume 2 §8's own updated note carries the full detail):** nflverse as the candidate primary NFL historical/statistical foundation (schedules, rosters, depth charts, play-by-play, player/team stats, advanced stats, snap counts, historical data, officials data where available) — exact field availability/freshness/licensing/field-contract explicitly NOT yet verified, no implementation authorized on an unverified assumption. The Odds API remains the leading odds candidate, with SportsGameOdds as a second candidate requiring a documented, evidence-based bake-off before either is permanently selected (recorded as a new pre-purchase validation task in the roadmap's Technical Debt & Feature Backlog, not run now). OpenWeather as the current weather candidate, provider abstraction intact either way. Current-injury sourcing and news/narrative sourcing both remain explicitly unresolved, separately-evaluated categories — nflverse is explicitly NOT assumed to solve current injury reporting, and no scraping dependency will be built merely to mark either field complete.
- **`public_betting`/`sharp_money` reaffirmed, not loosened:** both stay `null` in `daily_game_intelligence` until a legitimate vendor is selected (Volume 3 §4.1, unchanged); line movement is evidence an agent may reason over, never proof of or a substitute for actual sharp-money/public-betting-percentage data.
- **New Volume 4 §1.1 — "Data Sourcing, Derived Intelligence & the Deterministic Calculation Boundary":** codifies the RAW FACT → DETERMINISTIC FEATURE/CALCULATION → AI REASONING → CONSENSUS → RECOMMENDATION STRATEGY pipeline as an explicit, volume-wide principle, generalizing the deterministic-math discipline Milestone 4.2's real implementation already locked in for EV/Kelly (`app/agents/contract.py`'s no-nullable-field, resolve-before-output design) to every feature category a fan-out agent might otherwise be tempted to have a model estimate or recall: travel distance, line-movement metrics, usage shares, situational/coaching tendencies, and any other objectively computable metric. An agent whose deterministic feature is unavailable must degrade explicitly (`evidence_classification: "assumption"`, lower `confidence`, a `would_change_mind_if` naming the gap) — never fabricate a plausible-sounding number.
- **Derived-score-table/`daily_game_intelligence`-field ownership deliberately still NOT decided.** The 13 derived score tables (Volume 3 §4.2) and `daily_game_intelligence`'s `ai_scores`/`momentum`/`matchup_ratings`/`ev_calculations`/`confidence_scores`/`recommendation_candidates` fields stay exactly as flagged at Milestone 4.1's close — an open architecture question, not resolved by this entry. Mac's explicit direction: a dedicated data-contract impact inspection immediately precedes Milestones 4.4/4.5 (the first milestones that would actually need this answered), classifying at minimum Travel & Fatigue, Referee Tendencies, Offensive/Defensive Matchup, Historical Trends, Team Form, Coaching Tendencies, Motivation, Playoff Importance, Player Prop, Vegas Line, Closing Line Movement, Sharp Money, and Public Betting Agents' required data as AVAILABLE RAW / DERIVABLE / EXTERNAL SOURCE REQUIRED / DEGRADED BUT USABLE / BLOCKED. Assigning ownership now, merely because a table already exists, is exactly the premature decision that inspection exists to prevent.
- **Phase 4 open decisions reconfirmed, unchanged in substance, two given sharper edges:** Recommendation Worker stops at the Phase 4 consensus boundary (Phase 5 owns Explainability/Recommendation Strategy/final shape); `ai-orchestrator` direct-Supabase-read architecture approved in principle, contingent on environment isolation/service-role security staying correct; dev's Phase-1 fixture agent rows get an FK-safe cleanup/reseed when the real 22-agent roster is actually seeded (not before); partial fan-out agent failure is isolated (recorded as missing, never fabricated, never silently treated as full participation), with a minimum-viable-participation/catastrophic-failure quorum rule still to be defined before production behavior is finalized (not invented now, absent Blueprint specification); postponed/canceled games stay excluded from proactive generation, with live/final games' own eligibility lifecycle to be explicitly inspected (not assumed scheduled-only forever) before Milestone 4.9 builds the Recommendation Worker; live OpenAI/Anthropic calls remain gated behind Milestone 4.10's own cost-estimate-then-approval checkpoint; deterministic math (EV, Kelly, travel distance, line-movement, usage/statistical feature engineering, consensus arithmetic) stays application code, never LLM arithmetic — reconfirming Decision 8 from Milestone 4.1/4.2's own approval trail.

**Alternatives considered:**
- Proceeding with the SportsDataIO purchase to avoid a sourcing-strategy pivot mid-build — rejected by Mac on cost grounds; the product has not yet proven it needs a five-figure seasonal commitment.
- Silently substituting an unverified nflverse assumption for SportsDataIO without a documented sourcing strategy or verification step — rejected; this is precisely the kind of undocumented drift CLAUDE.md's Blueprint-vs-reality process exists to prevent, and several nflverse-dependent fields (current injuries specifically) are explicitly NOT assumed solved by this pivot.
- Deciding derived-score-table/DGI-field ownership now, since Milestone 4.1 already surfaced the question — rejected per Mac's explicit instruction; ownership decided before real consumers/agents exist risks exactly the "assigned because the table exists" mistake this entry's own principle warns against.
- Treating this as a MINOR, single-volume bump — rejected; the decision genuinely ripples across Volume 2's vendor strategy and Volume 4's agent-design principle as one coordinated change, the literal MAJOR-bump example this scheme's own table gives ("restructuring the AI Orchestrator hits Vol 2, 4").

**Expected impact:**
- Volume 2 (`v4.16.2` → `v5.0`): §8 gains the vendor-strategy revision paragraph (new candidates, SportsDataIO status, public_betting/sharp_money reaffirmation) directly below the existing named-vendor-candidates table; the table itself is unchanged, since it still accurately describes what Phase 3's already-built code integrates against today.
- Volume 4 (`v4.0` → `v5.0`): new §1.1, the first substantive content this volume has gained since its original v4.0 draft — Phase 4 hadn't yet reached implementation against it until this build session.
- **Zero code changes.** No Phase 3 worker, cadence, adapter, or persisted schema is touched by this entry — this is a sourcing-strategy and future-agent-design principle, not a build change. Milestone 4.2's already-merged implementation (`app/agents/contract.py`/`harness.py`, PRs #71-#72) was re-inspected against this new principle and found to already conform with zero modification needed (see `PROGRESS.md`'s corresponding entry).
- No Railway/Supabase mutation, no live provider calls (SportsDataIO budget unchanged at 11/12; nflverse/OpenWeather/SportsGameOdds: zero calls, nothing purchased or credentialed).
- New forward-looking task recorded, not executed: the Odds API vs. SportsGameOdds bake-off, added to `engineering-roadmap-build-order.md`'s Technical Debt & Feature Backlog.
- MAJOR, two-volume bump: a coordinated sourcing-strategy and agent-design-principle decision spanning Volume 2 and Volume 4, per the scheme's own definition.

**Full technical detail:** This entry, plus Volume 2 §8's new vendor-strategy paragraph, Volume 4's new §1.1, the new Technical Debt & Feature Backlog entry in the engineering roadmap, and `PROGRESS.md`'s corresponding Phase 4 notes entry (2026-08-20).

---

## v4.13 (Volume 3) — 2026-08-21 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Milestone 4.3 (provider-neutral AI model layer) found neither `model_registry` nor `model_routing_rules` stores explicit vendor identity — `ModelRouter.infer_provider` had to guess a model's provider from its name string (`"claude-"` → anthropic, `"gpt-"` → openai), flagged at the time as acceptable temporary scaffolding but not permanent architecture. Mac's pre-Milestone-4.4 review confirmed this needed a real fix before real agents are built against routing data.

**Decision:** `model_registry` gains `provider text not null` (no default value carried forward — added, backfilled, then set `not null` in one migration, `20260821150000_model_registry_provider.sql`). Deliberately **not** a `check (provider in ('openai','anthropic'))` constraint — Mac's explicit instruction: the architecture is intentionally provider-neutral, and hardcoding today's two vendors into a DB constraint would require a schema migration for every future provider, repeating the exact tradeoff `game_provider_ids`/`team_provider_ids`/`player_provider_ids.provider_name` already accepted (each needs its own follow-up migration for a new vendor). Validity is enforced at the application layer instead: `app.models.router.AdapterRegistry.get()` already raises `UnknownProviderError` for any unregistered provider (Milestone 4.3) — a DB `CHECK` would enforce the identical rule twice, in two different failure modes, for one validation concern. `model_routing_rules` does **not** get its own provider column — provider resolves by joining through `model_registry.model_name`, avoiding storing the same fact in two places (`primary_model`/`fallback_model` remain plain, non-FK model-name references, unchanged). Dev's 2 existing rows (`claude-sonnet-5`, `claude-opus-5`) backfilled `provider = 'anthropic'`, confirmed correct before migrating, not assumed.

**Alternatives considered:**
- A `check (provider in ('openai','anthropic'))` constraint — presented as a real tradeoff per Mac's own request ("if you believe a DB CHECK is still materially safer, present the tradeoff"); not applied, since `model_registry` is service-role-only/admin-configured (not a untrusted write path) and the real validation consequence already lives correctly at the application layer.
- A reference table (`ai_model_providers(code text primary key)`, `model_registry.provider` FK'd to it) — a legitimate middle-ground (DB-level referential integrity, still additive-only for a new vendor) but rejected as an unnecessary second table for a problem application code already solves cleanly.
- Adding `provider` to `model_routing_rules` as well — rejected; no lifecycle reason to duplicate the fact in two tables when one already owns it per model name.

**Expected impact:** `apps/ai-orchestrator/app/models/router.py` updated to resolve provider via `model_registry` (canonical) with `infer_provider`'s name-prefix mapping retained only as an explicitly-deprecated fallback, per Mac's instruction that it "must not silently rescue missing production model-registry configuration forever." No other Phase 3/4 code, cadence, or table touched. Dev migration applied and verified (`provider` column present, correctly backfilled for both existing rows). Staging/production unaffected (staging still lacks the whole Milestone-3/4 AI-intelligence table set, per Milestone 4.1's own finding — this migration will need to be part of whatever eventually promotes that full table set to staging).

**Full technical detail:** This entry, plus the updated `model_registry` definition in Volume 3 §8, and `PROGRESS.md`'s Milestone 4.4 entry.

## v4.14 (Volume 3) — 2026-08-22 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Milestone 4.6 introduced a sequential Decision & Advisory chain (Probability Modeling → Expected Value → Risk Manager → Bankroll Coach) that must evaluate a specific betting candidate (e.g. "KC moneyline -125"), not "the game" abstractly — `AgentOutput.directional_lean` can only speak to one side at a time. A required pre-implementation inspection (Mac's explicit "do not solve this silently" instruction) found `recommendation_agent_outputs` has no unique constraint blocking multiple rows per `(recommendation_id, agent_id)`, but also no column identifying which candidate a row belongs to — that identity would have had to live entirely inside the unindexed `raw_output` jsonb, with no query support, no index, and no guard against ambiguous duplicates.

**Decision:** `recommendation_agent_outputs` gains a nullable `candidate_key text` column (migration `20260822140000_recommendation_agent_outputs_candidate_key.sql`) plus a partial index `(recommendation_id, candidate_key) where candidate_key is not null`. Backward-compatible: every existing game-level fan-out output (Milestones 4.4/4.5) stays `NULL`; only the new sequential chain's candidate-level outputs populate it. **Deliberately no uniqueness constraint** — Mac's explicit instruction: multiple evaluations of the same candidate may legitimately exist over time, and retry/versioning semantics for this identity are not yet designed strongly enough to justify enforcing uniqueness at the database level. `candidate_key` and `recommendation_id` remain conceptually distinct and not interchangeable: the former identifies the wager being evaluated, the latter identifies the overall recommendation-analysis cycle it was evaluated within — one cycle may (and is expected to) contain many evaluated candidates, which Phase 5 later compares to decide the actual recommendation shape.

**Alternatives considered:**
- No schema change — embed `candidate_key` only inside `raw_output` JSON. Rejected: no index, no query support, no guard against ambiguous duplicate candidate evaluations; workable for tests, not "clean" as a real production design.
- One `recommendations` row per candidate. Rejected — fights directly against Phase 5's actual job (comparing many evaluated candidates down to few final recommendation objects) and would pollute a customer/audit-facing table (`display_id`, `status`) with internal evaluation artifacts.
- A uniqueness constraint on `(recommendation_id, agent_id, candidate_key)`. Rejected for now, per Mac's explicit instruction — premature given undesigned retry/versioning semantics; revisit once that design exists.

**Expected impact:** `apps/ai-orchestrator/app/persistence/recommendations.py` gains `persist_candidate_agent_output` (parallel to the existing game-level `persist_agent_output`, unchanged). `apps/ai-orchestrator/app/orchestration/cycle.py` gains `run_candidate_evaluation`, callable multiple times against one already-existing `recommendation_id`. No other Phase 3/4 table or cadence touched. Dev migration applied and verified. Staging/production unaffected (staging still lacks the whole Milestone-3/4 AI-intelligence table set).

**Full technical detail:** This entry, plus the updated `recommendation_agent_outputs` definition in Volume 3 §5, and `PROGRESS.md`'s Milestone 4.6 entry.

## v4.15 (Volume 3) — 2026-08-22 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Milestone 4.7 built the deterministic Consensus Engine, candidate-anchored per Decision I (see the paired Volume 4 v5.1 entry below). Three real gaps surfaced in the same live-schema inspection pattern already established for `recommendation_agent_outputs` (v4.14): `consensus_snapshots` had no candidate identity, no column for the post-adjustment `final_aggregate_confidence` (distinct from the existing pre-adjustment `aggregate_confidence`), and no column for the internal 0.55-threshold result.

**Decision:** four nullable columns added (migration `20260822153000_consensus_snapshots_candidate_and_final_confidence.sql`): `candidate_key text` (mirrors `recommendation_agent_outputs.candidate_key` exactly — same no-uniqueness-constraint reasoning, same partial index pattern), `final_aggregate_confidence numeric`, `below_confidence_floor boolean`, and `participation_metadata jsonb`. The last of these is required because a failed or deferred fan-out agent leaves zero trace in `recommendation_agent_outputs` — without persisting participation metadata separately, a future reader could never distinguish "0.71 confidence from a complete 17-agent committee" from "0.71 confidence while only 6 of 17 intended agents existed yet." All backward-compatible; existing rows (none yet exist in practice, but the column additions are additive regardless) are unaffected.

**Alternatives considered:**
- Overloading `aggregate_confidence` to mean the post-adjustment value. Rejected — Mac's explicit instruction to keep `aggregate_confidence`/`final_aggregate_confidence` numerically distinct and auditable; overloading would lose the pre-adjustment number entirely.
- Writing `final_aggregate_confidence`/`below_confidence_floor` into `recommendations` instead. Rejected — `recommendations` columns for this purpose (`confidence_score`) are explicitly Phase-5-owned per the standing boundary established at Milestone 4.5; Phase 4 does not write to them.
- Hiding participation inside `model_routing_used` (already existed, jsonb, no schema change needed). Rejected per Mac's explicit instruction — participation is a structurally distinct concern from "which model handled which agent," and deserves its own named column, not overloading an existing one for two purposes.

**Expected impact:** `apps/ai-orchestrator/app/persistence/consensus_snapshots.py` (new) reads game-level `recommendation_agent_outputs` rows and writes one `consensus_snapshots` row per successfully-computed candidate consensus (never one when consensus is undefined — see that module's own docstring for the real `aggregate_confidence NOT NULL` conflict this resolves, via the same "no result, no row" pattern already established for a failed fan-out agent). No other Phase 3/4 table or cadence touched. Dev migration applied and verified. Staging/production unaffected.

**Full technical detail:** This entry, plus the updated `consensus_snapshots` definition in Volume 3 §5, and `PROGRESS.md`'s Milestone 4.7 entry.

## v5.1 (Volume 4) — 2026-08-22 — MINOR

**Volume affected:** Volume 4 (AI Intelligence Architecture) only.

**Reason:** Section 4.1's "majority lean" wording predates Milestone 4.6's `MarketCandidate` concept entirely, and a literal implementation would compute directional agreement incoherently once a specific wager is in play (e.g. a totals-relevant agent's lean outvoting moneyline-relevant ones for a spread candidate). Separately, implementing Section 4.3's `agreement_variance > 0.25` Elite second-pass trigger for the first time in real code surfaced a genuine mathematical property of Section 4.1's own specified `0.3` fractional disagreement penalty that no prior planning pass had checked against the threshold it feeds.

**Decision:** Section 4.1 is updated to document candidate-anchored consensus as an intentional Blueprint evolution (Mac's explicit instruction) — `directional_agreement[i]` now compares each agent against the specific candidate's own resolved direction (home/away for moneyline/spread, over/under for totals, resolved by exact match against `home_team`/`away_team`, never inferred from array position or ordering), not a self-referential committee majority. The three-state rule (matches/opposes/no-vote) is documented explicitly, including that "no directional opinion" (either `directional_lean = "none"` or an off-axis lean) is excluded from the calculation entirely, never coerced into support or opposition. Player-prop candidates are excluded from this calculation for now — no directional mapping exists, and none was invented. Separately, Section 4.1 and 4.3 both now document a real finding: with only two possible `directional_agreement` values (`1.0`, `0.3`), the maximum possible population variance is `0.1225` (at a 50/50 split) — meaning `agreement_variance > 0.25` can never fire from any real computed input under this section's own specified penalty value, independent of the candidate-anchoring change. This is documented as an open question (whether the penalty, the threshold, or the variance formula should change), not resolved unilaterally. Section 4.3 also now documents that Elite reconciliation's own output is a dedicated, minimal contract, deliberately not `MetaAgentOutput` — the two review a candidate's consensus for different reasons and stay semantically separate, per Mac's explicit instruction.

**Alternatives considered:**
- Maintaining a separate game-level "majority lean" score alongside the new candidate-anchored one, to preserve Section 4.1's original pre-candidate wording literally. Rejected per Mac's explicit instruction — no functional use for a second score existed once every actual consumer (Probability Modeling, EV, Risk Manager, Bankroll Coach) is candidate-scoped.
- Silently lowering the fractional disagreement penalty (e.g. to `0.0`) to make the `0.25` threshold reachable. Rejected — this would be an unauthorized, silent change to Section 4.1's own specified number to paper over a newly-discovered inconsistency, exactly the kind of improvisation flagged as out of bounds; the trigger logic is implemented and tested correctly in isolation, and the reachability question is left open for an explicit future decision.

**Expected impact:** `apps/ai-orchestrator/app/features/consensus.py`, `app/orchestration/consensus.py`, `app/agents/{meta_agent,elite_reconciliation_agent,elite_reconciliation_output,consensus_review_base,consensus_review_context}.py` implement the above. No live model/provider calls; `FakeModelAdapter` only. See `CHANGELOG.md` v4.15 (Volume 3) entry above for the paired schema change, and `PROGRESS.md`'s Milestone 4.7 entry for the full test evidence.

**Full technical detail:** This entry, plus the updated §4.1/§4.2/§4.3 text in Volume 4, and `PROGRESS.md`'s Milestone 4.7 entry.

## v4.16 (Volume 3) — 2026-08-24 — MINOR

**Volume affected:** Volume 3 (Database Architecture) only.

**Reason:** Milestone 4.8 (Phase 4 Closeout Remediation) wired `prompt_registry` in as the actual production source of every agent's system prompt (`prompt_name = agent_name`, each independently versioned). The required pre-implementation inspection (Mac's explicit instruction) found that `recommendations.prompt_version` — the only existing prompt-provenance field — was written when `prompt_registry` modeled one prompt per recommendation cycle (the pre-existing `nfl_single_v1.0`/`nfl_parlay_v1.0` fixture concept), a concept that predates per-agent prompts entirely. A single scalar column cannot truthfully represent multiple agents' independently-versioned prompts coexisting in one cycle (e.g. `injury_intelligence_agent → v3`, `weather_agent → v2` in the same run) without being semantically false — exactly the condition Mac's instruction said to stop and report rather than force.

**Decision:** `recommendation_agent_outputs` gains two nullable columns, `prompt_name text` and `prompt_version integer`, plus a composite foreign key to `prompt_registry(prompt_name, version)` (migration `20260824161000_recommendation_agent_outputs_prompt_provenance.sql`) — the canonical per-agent-output Time Machine provenance, frozen at persist time exactly like `weight_applied`, populated only from the exact `prompt_registry` row the orchestration layer actually resolved and used (never a caller-supplied guess, never the currently-active prompt re-read after the fact, never `agent_name` plus an assumed version, never copied from `recommendations.prompt_version`). `recommendations.prompt_version` remains unchanged in shape — not repurposed, not removed — but is now documented as legacy/non-authoritative for per-agent reconstruction. Separately, `prompt_registry` gains a partial unique index, `idx_prompt_registry_one_active_per_name` (migration `20260824160000_prompt_registry_one_active_per_name.sql`), enforcing at most one active version per `prompt_name` at the database level — an application-side "highest version wins" convention alone was explicitly rejected as insufficient, since it would silently tolerate an invalid multi-active-row state instead of refusing to create one.

**Alternatives considered:**
- A global prompt-release/version number spanning all agents. Rejected per Mac's explicit instruction — no authoritative architecture supports this concept, and inventing one to force a single-scalar shape back into `recommendations.prompt_version` would misrepresent independently-versioned agent prompts as a coordinated release they are not.
- A derived "prompt-set fingerprint" (e.g. a hash of every `agent_name:version` pair used in a cycle) stored on `recommendations`. Rejected — opaque, not independently queryable per agent, and not described anywhere in the Blueprint; a larger invention than the per-output column approach for no clear benefit over it.
- Repurposing or removing `recommendations.prompt_version`. Rejected per Mac's explicit instruction — a breaking change to a column Phase 5 may still reference, for no benefit once per-output provenance exists as the real mechanism.
- Adding `task_type` to `prompt_registry` as a second agent-mapping key alongside `prompt_name`. Rejected per Mac's explicit instruction — model routing and prompt routing are separate concerns; `agent_name` already uniquely identifies each agent and is reused as `prompt_name` directly, so a second mapping layer would be pure duplication.

**Expected impact:** `apps/ai-orchestrator/app/persistence/model_config.py` gains `resolve_active_prompt`/`ResolvedPrompt`/`PromptConfigError` (deterministic, fail-loud resolution — never a silent fallback to hardcoded text). `apps/ai-orchestrator/app/persistence/recommendations.py`'s `persist_agent_output`/`persist_candidate_agent_output` gain `prompt_name`/`prompt_version` parameters. `app/orchestration/{fanout,sequential,consensus,cycle}.py` resolve and thread prompt provenance at the orchestration/harness boundary (never inside an agent class). Both migrations applied and verified live against dev, including a real insert/verify/cleanup proof against the actual live schema (Supabase MCP `execute_sql`, mirroring the exact payload shapes `persist_candidate_agent_output`/`persist_consensus_snapshot` construct — `SUPABASE_SERVICE_ROLE_KEY` was not available in this session to run the live Python persistence path directly, consistent with Milestone 4.1's own decision not to configure that credential on this service; flagged honestly rather than claimed as a literal live-code-path proof). No other Phase 3/4 table or cadence touched. Staging/production unaffected.

**Full technical detail:** This entry, plus the updated `recommendations`/`recommendation_agent_outputs`/`prompt_registry` definitions in Volume 3 §5/§8, and `PROGRESS.md`'s Milestone 4.8 entry.

## v5.2 (Volume 4) — 2026-08-24 — MINOR

**Volume affected:** Volume 4 (AI Intelligence Architecture) only.

**Reason:** Two items required resolution before Milestone 4.8 (Phase 4 Closeout Remediation) could proceed: (1) Section 4.3's `agreement_variance > 0.25` Elite second-pass threshold, already documented in v5.1 as structurally unreachable, needed an actual corrected value, derived from product meaning rather than picked arbitrarily; (2) whether Section 6 (Adaptive Agent Weighting) belongs to Phase 4 at all needed a decisive answer, since Phase 4's roadmap entry cites this section in passing but a live-schema/code inspection found zero real historical performance data and zero code writing `agents.current_weight` anywhere in the codebase.

**Decision:** (1) `ELITE_VARIANCE_THRESHOLD` corrected from `0.25` to `0.10` (Decision L) — derived by hand-calculating `agreement_variance` across representative voting splits (90/10 through 50/50) and choosing the smallest threshold that reads as "a meaningful minority of the committee in confident opposition": reachable at a 70/30 split (`≈0.1029`) and closer, not reachable at 75/25 (`≈0.0919`) or looser. The `1.0`/`0.3` directional-agreement factors, `aggregate_confidence`'s semantics, and the variance formula itself are explicitly unchanged — confirmed and documented that `agreement_variance` remains an unweighted committee-polarization signal (agent weight affects `aggregate_confidence`, never this statistic), with whether it should eventually become weight-aware left as an open, deferred question. (2) Section 6 is confirmed Phase 5 scope, per `engineering-roadmap-build-order.md`'s own explicit assignment of the weighting write/learning loop to Phase 5 — Phase 4's only weighting obligation (consuming `current_weight` correctly) was already satisfied in Milestone 4.7. Section 6.1's three guardrails (200 minimum sample size, ±10% max change, 90-day window) remain explicitly provisional, not finalized in this pass — finalizing them now, with no real performance data to validate against, would itself be inventing parameters to make an unbuilt system look decided.

**Alternatives considered (threshold correction):**
- Widening the `1.0`/`0.3` factor spread to raise the variance ceiling instead of lowering the threshold. Rejected per Mac's explicit instruction — this would also change `aggregate_confidence`'s already-shipped, already-tested semantics for every user-facing number, a far larger blast radius than correcting one internal constant.
- Decoupling `agreement_variance` from `lean_factor` entirely (a new, independent disagreement statistic). Rejected for this milestone — the largest option, requiring its own from-scratch specification and test suite; not justified when the smaller threshold correction resolves the actual defect (an unreachable threshold).
- Leaving the threshold unreachable and documenting Elite second-pass as a known, deferred product gap. Rejected — Elite-tier users are nominally promised second-pass reconciliation under serious disagreement; leaving it permanently unreachable was judged worse than a small, well-derived constant correction.

**Alternatives considered (Phase 4/5 boundary):**
- Building the adaptive-weighting write loop now, in Phase 4, running against Phase-1 seed-fixture data until real outcomes exist. Rejected per Mac's explicit instruction — would silently produce a system that looks adaptive while actually learning from fixtures, exactly the fabrication the roadmap's testing discipline exists to prevent.
- Building the write loop's mechanism now but leaving it structurally inert (never called from any live path). Rejected — likely throwaway work once Phase 5's real settlement/postgame data model exists to design against; smaller benefit than the risk of maintaining unintegrated code.
- Finalizing the three guardrail numbers now so Phase 5 has settled values. Rejected per Mac's explicit instruction — no evidence exists today to validate any specific number; Phase 5's own inspection, with real early-outcome data available, is better positioned to set them.

**Expected impact:** `apps/ai-orchestrator/app/features/consensus.py`'s `ELITE_VARIANCE_THRESHOLD` and `should_trigger_elite_second_pass` docstring updated; `tests/features/test_consensus.py`'s threshold tests updated to the new boundary plus real hand-calculated 70/30 and 75/25 examples. No Adaptive Agent Weighting code written — Milestone 4.8 explicitly does not begin it, per Mac's instruction. No live model/provider calls; `FakeModelAdapter` only.

**Full technical detail:** This entry, plus the updated §4.1/§4.3/§6 text in Volume 4, and `PROGRESS.md`'s Milestone 4.8 entry.
