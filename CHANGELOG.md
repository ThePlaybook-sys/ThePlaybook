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
