# The Blueprint — Documentation Hub

The Blueprint is the authoritative specification for The Playbook. It is the source of truth for what the product is, how it's architected, and how it's built — code implements the Blueprint, not the other way around. If code and Blueprint ever disagree, that's a drift to resolve per `CLAUDE.md`'s "If the Blueprint and Reality Disagree" process, not a signal to quietly follow the code.

This file is the entry point into that specification: how to read it, how its documents relate to each other, and what actually exists in this repository right now.

---

## How to Use the Blueprint

Read the relevant volume section(s) before writing code for a task — don't rely on a summary of these documents from memory or from a prior session. Each volume carries its own `**Version:**` line in its header; that line, not this file, is the record of what version a document is currently at. This hub reads those headers directly rather than maintaining a separate list, so it can't go stale the way a hand-maintained version table would.

## Reading Order

1. **`volume-1-business-product-ux.md`** — What The Playbook is from a product and business standpoint: the business model, pricing, target personas, user journeys, and the chat-first positioning that shapes every other volume. Start here to understand *why* the system is built the way it is before reading *how*.
2. **`volume-2-system-architecture.md`** — The backend system as a whole: the FastAPI/Next.js/Supabase/Railway stack, API strategy, Redis usage, vendor selections, the Core Architecture Principles, environment data-source policy, and the Recommendation Worker that proactively generates recommendations outside of a user request.
3. **`volume-3-database-architecture.md`** — The full database schema: table definitions, Row-Level Security policies, migration conventions, the `daily_game_intelligence` cache table and its per-category data-quality metadata, and the normalized multi-sport core (`sports`, `leagues`, `seasons`, `teams`, `players`, and sport-specific stats extension tables).
4. **`volume-4-ai-intelligence.md`** — The intelligence layer: the 22-agent AI committee, how consensus is formed and weighted, Kelly Criterion stake sizing, session memory, and the two entry points (proactive worker and on-demand conversational) that both converge on the same recommendation pipeline.
5. **`volume-5-frontend-ux.md`** — The user-facing product: dashboards, UI components, notifications, and the chat-first navigation model, including the AI Transparency Meter that surfaces data quality and confidence to the user.
6. **`v2.0-amendments-architecture-review.md`** — Schema and architecture additions from an external architecture review, referenced throughout Volumes 1–5 wherever a v2.0-originated detail applies.
7. **`v3.0-amendments-conversational-intelligence.md`** — Chat-first UX, the conversational intelligence pipeline, and the schema additions that support it, referenced throughout Volumes 1–5 wherever a v3.0-originated detail applies.
8. **`engineering-roadmap-build-order.md`** — The file that governs how the team actually works: 12 phases (0–11), each with milestones, tasks, dependencies, acceptance criteria, and testing requirements. This is read continuously during implementation, not just once.
9. **`../../CHANGELOG.md`** (repo root) — The version history for the Blueprint itself. Every architectural decision recorded here has a Reason, a Decision, Alternatives Considered, and an Expected Impact. When a volume's header and this changelog disagree, the changelog wins.

There is no separate `v4.0-amendments-*.md` document — that was a deliberate choice for the v4.0 round, not a missing file. Full v4.0 reasoning lives directly in `CHANGELOG.md`'s v4.0 entry and inline in each affected volume's own v4.0 note.

**`demo-simulation-environment.md`** sits outside this reading order on purpose — it is an approved, authoritative supporting architecture document (Mac, 2026-08-19), but it describes a cross-cutting demo/simulation capability rather than a core product volume, so it isn't part of the volume 1→5 dependency chain above. Read it when working on Demo Mode specifically; it in turn depends on Volume 2 §5/§7/§8/§9, Volume 3, and the roadmap's phase definitions, exactly as its own header states.

## Document Dependency Graph

```
                    volume-1 (business/product/UX)
                          │
                          │ informs
                          ▼
                    volume-2 (system architecture)
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        volume-3      volume-4      volume-5
       (database)   (AI intelligence) (frontend/UX)
              ▲           ▲           ▲
              │           │           │
      v2.0-amendments ────┼───────────┤
      v3.0-amendments ────┴───────────┘
      (both amend volumes 1–5 wherever cited)

  engineering-roadmap-build-order.md
      │  sequences the build of all volumes above into 12 phases
      ▼
  CHANGELOG.md
      │  records every version change to every document above
      ▼
  CLAUDE.md (repo root)
      governs how work on all of the above is actually carried out
```

Volumes 3, 4, and 5 each depend on Volume 2's architecture decisions; Volume 2 depends on Volume 1's product framing. The amendments documents are cross-cutting — each one modifies specific sections across multiple volumes rather than standing alone. The roadmap sequences implementation of everything above it; the changelog is the append-only record of how everything above it got to its current state.

---

## Repository Structure

```
ThePlaybook/
├── apps/                     # Implementation — see repo root README.md
├── docs/
│   ├── blueprint/            # This directory — the specification
│   └── ops/                  # Operational runbooks (e.g. secrets management)
├── .github/workflows/        # CI/CD pipeline definitions
├── CHANGELOG.md              # Blueprint version history
├── CLAUDE.md                 # Project instructions and working agreement
└── PROGRESS.md               # Live build status against the roadmap
```

## Environment Strategy

The Blueprint is built and validated across three Railway environments — dev, staging, production — with a formal policy (Volume 2 §5) governing which data sources each environment is permitted to use. Production is the only environment real user data ever touches; dev and staging use the data sources that policy specifies. See Volume 2 §5 for the full table.

## CI/CD Pipeline (High Level)

Implementation of the Blueprint is validated on every push via GitHub Actions: Python services are tested with `pytest`, the frontend is built as its test gate, and passing builds deploy automatically — `dev` branch pushes to the dev environment, `main` branch pushes to staging, and `v*` tags to production. Full detail is in the repo root `README.md` and `.github/workflows/ci-cd.yml` itself; this hub only orients the reader to where CI/CD fits relative to the specification.

---

## Documentation Rules

1. **Volumes are authoritative.** Volumes 1–5 are the source of truth for what the product is and how it's built. Nothing else in the repo overrides them.
2. **Amendments modify volumes.** The `v*.0-amendments-*.md` documents are not standalone specifications — they are changes applied to specific sections of specific volumes. Read them alongside the volumes they cite, not instead of them.
3. **The roadmap references current architecture.** `engineering-roadmap-build-order.md` sequences the build; it does not redefine architecture. If the roadmap and a volume ever disagree on what something *is* (as opposed to *when* it gets built), the volume wins and the disagreement gets flagged per `CLAUDE.md`.
4. **READMEs summarize but never replace the Blueprint.** This file and the repo root `README.md` exist for orientation and navigation only. Neither is a substitute for reading the actual volume — when in doubt, the volume's own text governs, not a summary of it.

## Documentation Index

| Document | Purpose |
|---|---|
| `volume-1-business-product-ux.md` | Business model, product, UX |
| `volume-2-system-architecture.md` | System architecture |
| `volume-3-database-architecture.md` | Database schema |
| `volume-4-ai-intelligence.md` | AI committee and recommendation pipeline |
| `volume-5-frontend-ux.md` | Frontend and UX |
| `v2.0-amendments-architecture-review.md` | v2.0 architecture review amendments |
| `v3.0-amendments-conversational-intelligence.md` | v3.0 conversational intelligence amendments |
| `engineering-roadmap-build-order.md` | Build sequencing across 12 phases |
| `demo-simulation-environment.md` | Demo/Simulation Environment architecture — supporting document, not part of the core reading order (see note below) |
| `../../CHANGELOG.md` | Blueprint version history |
| `../ops/secrets-management.md` | Operational runbook — not part of the versioned Blueprint |

### Reserved for Future Documents

The following are placeholders only — space reserved in the documentation structure, not yet created. Do not treat their absence as a gap to fill without an explicit request:

- **API Reference** — endpoint-level documentation for `api-gateway`, once the API surface stabilizes
- **Developer Guide** — onboarding and local-development walkthrough beyond the Quick Start in the repo root README
- **Operations Manual** — day-to-day operational procedures beyond `docs/ops/secrets-management.md`
- **Deployment Runbook** — step-by-step deploy and rollback procedures
- **Disaster Recovery** — backup, restore, and incident response procedures
- **Security Handbook** — security policies, threat model, and incident response

---

## Current Versions

Generated by reading each document's own `**Version:**` header line directly — not maintained as a separate list. If this table and a document's own header ever disagree, re-scan the header; the header is the source of truth, and this table is just a cached view of it.

| Document | Version (from header) |
|---|---|
| `volume-1-business-product-ux.md` | v3.0 |
| `volume-2-system-architecture.md` | v4.16 |
| `volume-3-database-architecture.md` | v4.12.1 |
| `volume-4-ai-intelligence.md` | v4.0 |
| `volume-5-frontend-ux.md` | v4.0 |
| `v2.0-amendments-architecture-review.md` | v2.0 |
| `v3.0-amendments-conversational-intelligence.md` | v3.0 |
| `engineering-roadmap-build-order.md` | v4.0 |
| `demo-simulation-environment.md` | v1.1 |

_Last scanned: 2026-08-19, against the repository state on `claude/new-session-fqsad5`. Volume 2 and Volume 3 corrected from a stale v4.0 to their actual current headers (v4.16, v4.12.1) — all other rows re-checked against their own `**Version:**` header lines and already matched._

## Known Documentation Gaps

None found as of the last scan above — every document referenced by name in `CLAUDE.md`'s manifest and throughout the volumes above exists in `docs/blueprint/` with a readable `**Version:**` header. This section is where a future scan should list any document that's cited but missing, or present but missing a version line, rather than guessing at its status.

---

## Change Management

Architecture changes follow one direction only: **Blueprint first, roadmap second, implementation third.** Never the reverse.

1. **The Blueprint changes first.** A proposed architecture change is written into the relevant volume (or a new amendments document, for a review-driven batch of changes), with the volume's version header bumped and a corresponding entry added to `CHANGELOG.md` using its four-field format (Reason, Decision, Alternatives Considered, Expected Impact).
2. **The roadmap is updated second**, if the change affects build sequencing, a phase's acceptance criteria, or its testing requirements.
3. **Implementation happens third**, against the now-updated Blueprint and roadmap — never the other way around. Code is never written first and reconciled with the Blueprint afterward; if reality forces a deviation during implementation, that's handled via `CLAUDE.md`'s "If the Blueprint and Reality Disagree" process, which still resolves back through the Blueprint before the change is considered final.

This ordering is what keeps the Blueprint authoritative in practice, not just in name — see `CLAUDE.md` for the full phase-gating and blueprint-vs-reality rules this depends on.
