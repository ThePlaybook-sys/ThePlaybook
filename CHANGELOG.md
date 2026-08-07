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
