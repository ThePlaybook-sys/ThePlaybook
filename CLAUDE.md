# The Playbook — Project Instructions (CLAUDE.md)

This file is read automatically at the start of every Claude Code session in this repository. It is the supreme law of this project — if anything in a conversation conflicts with this file, this file wins unless Mac explicitly overrides it in that session.

---

## What This Project Is

The Playbook is an AI-powered sports betting operating system — not a picks app. Full specification lives in `/docs/blueprint/`:

- `volume-1-business-product-ux.md` — business model, pricing, personas, journeys, chat-first positioning
- `volume-2-system-architecture.md` — backend stack, Railway deployment, API strategy, Redis, vendor picks, architecture principles, Recommendation Worker
- `volume-3-database-architecture.md` — full schema, RLS, migrations, daily_game_intelligence, normalized multi-sport core
- `volume-4-ai-intelligence.md` — the 22-agent committee, consensus, weighting, Kelly Criterion, session memory, dual entry points
- `volume-5-frontend-ux.md` — dashboards, components, notifications, chat-first navigation
- `v2.0-amendments-architecture-review.md` — schema/architecture additions from the external review, referenced throughout the volumes above
- `v3.0-amendments-conversational-intelligence.md` — chat-first UX, intelligence pipeline, and schema additions, referenced throughout the volumes above
- `engineering-roadmap-build-order.md` — **this is the file that governs how you work.** 12 phases (0–11), each with milestones, tasks, dependencies, acceptance criteria, and testing requirements.
- `CHANGELOG.md` — version history. Every architectural decision has a reason, what changed, alternatives considered, and expected impact.

Each file's own header states its current version — this manifest doesn't track versions separately. Check `docs/blueprint/README.md` for the live version table, or the file's own header, rather than relying on this list.

Read the relevant volume section(s) before writing any code for a task — don't rely on memory of a prior session's summary of these documents. They're the source of truth, not this file.

---

## The One Rule That Overrides Everything Else: Phase Gating

**We build in the exact phase order defined in `engineering-roadmap-build-order.md`. We do not start Phase N+1 until Phase N's acceptance criteria are fully met and Mac has explicitly confirmed the phase is closed.**

This means, concretely:

1. At the start of any work session, state which phase is currently active (check `PROGRESS.md`, described below, first).
2. Before writing code, restate that phase's milestones, key tasks, and — most importantly — its **acceptance criteria** and **testing requirements**, so both of us are looking at the same finish line.
3. Do the work for that phase only. If a task naturally pulls you toward something that belongs to a later phase (e.g., building Phase 3's Sports Intelligence Layer while working Phase 1's database migrations), stop, name which future phase it belongs to, and don't build it early — note it and return to the current phase's scope.
4. When you believe the phase's acceptance criteria are met, don't declare it done unilaterally. Present a checklist mapping each acceptance criterion to how it was verified (test run, manual check, etc.) and explicitly ask Mac to confirm before moving to the next phase.
5. If Mac asks you to skip ahead or work out of order, flag that this breaks the phase-gating rule and name the specific risk (per the roadmap's own reasoning — e.g., "Phase 6 depends on Phase 5's recommendation pipeline being real, not placeholder data"), then follow his explicit instruction if he confirms he wants to proceed anyway. The rule is default behavior, not an unbreakable constraint — but it should never be broken silently.

---

## Track Progress in PROGRESS.md

Maintain a `PROGRESS.md` file at the repo root as the single source of truth for where the build actually stands. Update it every time a phase (or a milestone within a phase) changes state. Structure:

```markdown
# Build Progress

## Current Phase: [N — Name]

## Phase Status
- [x] Phase 0 — Repository, Environments, CI/CD — CLOSED 2026-XX-XX
- [ ] Phase 1 — Database Foundation — IN PROGRESS
      - [x] Milestone 1: Core user/account tables live
      - [ ] Milestone 2: Sports data tables live
- [ ] Phase 2 — Authentication — NOT STARTED
...

## Notes
[Any deviations from the blueprint, decisions made mid-build, or things flagged back to Mac for a changelog update]
```

Update this file as part of the same work that closes a milestone — not as an afterthought at the end of a session.

---

## If the Blueprint and Reality Disagree

Building real code will surface things five volumes of planning didn't catch — that's normal, not a failure of the blueprint. When it happens:

1. **Stop and flag it explicitly** rather than quietly improvising a fix that isn't reflected anywhere.
2. Explain the specific conflict: what the blueprint says, what reality requires, and why.
3. Propose a resolution.
4. Once Mac confirms, treat it exactly like any other architecture change: log it in `CHANGELOG.md` using the same four-field format already established (Reason, Decision, Alternatives Considered, Expected Impact), and determine whether it's a PATCH, MINOR, or MAJOR bump per the scheme at the top of that file. Update the relevant volume file's version header to match.

Do not let undocumented drift accumulate between what the blueprint says and what the code actually does — that gap is exactly what the versioning discipline across all five volumes was built to prevent, and it applies just as much during implementation as it did during planning.

---

## Testing Discipline

Every phase in the roadmap has explicit testing requirements — treat them as part of the phase's definition of done, not a separate QA pass to get to later. Specifically:

- Write tests as part of the same work that implements a feature, not after the fact.
- Before presenting a phase as ready for Mac's sign-off, actually run the tests listed in that phase's "Testing Requirements" section and show the results — don't assert they'd pass.
- Pay special attention to Phase 5's reproducibility test (Time Machine reconstruction) — this is called out in the roadmap as the single most important test in the entire build, since it's the mechanical proof of the product's core trust claim.

---

## Credentials & Connections

Two different things happen here, and they're not interchangeable — never treat one as covering the other.

**Platform connections (Railway, GitHub, Supabase):** These use OAuth — a one-time authorization click. When a phase first needs one (Railway in Phase 0, Supabase in Phase 1), stop and explicitly prompt Mac to authorize it rather than assuming a connection exists or silently trying to proceed without one. Once authorized, it persists — don't re-ask for the same connection in a later session unless it actually fails.

**API keys (OpenAI, Anthropic, any sports/odds data provider, Twilio):** These are not something you can obtain or generate. Mac has to create the account and generate the key himself on each provider's own site, outside of this session entirely. Your job is to:
1. Tell him clearly which key is needed, when it's actually needed (not preemptively — e.g., don't ask for Twilio credentials during Phase 1), and where to get it (which provider's dashboard).
2. Once he provides it, set it as a Railway environment variable (Volume 2 §9's secrets management) — never hardcode it, never commit it to the repo, and don't echo the full key value back in conversation once it's been set.
3. If a key is missing when a phase needs it, that phase is blocked — say so plainly and name exactly which key is missing, rather than building around it with a placeholder that could accidentally ship.

**Never assume a credential exists.** If a task needs Railway access, a specific API key, or any other external connection and you're not certain it's already set up, ask before proceeding — this is the same "stop and flag rather than silently improvise" principle as the blueprint-vs-reality section above, just applied to credentials instead of architecture.

---

## Railway Config Mutations: Default to skipDeploys: true

Any Railway MCP call that mutates a service's config or variables (`set-variables`, `update-service`, and equivalents) redeploys that service by default unless told not to. On an environment where autodeploy is intentionally disabled — production, per Volume 2 §9 — that default redeploy pulls from whatever stale cached build snapshot Railway last had, not current code, which is exactly what caused the 2026-08-07 production outage: a routine `set-variables` call (setting `SENTRY_DSN`) silently redeployed 5 production services from a snapshot that predated every Phase 0 fix.

**Rule: pass `skipDeploys: true` on every Railway config/variable mutation unless a deploy is the explicit, specific point of that call.** This applies everywhere, not just production — dev and staging just happen to tolerate a stale-snapshot redeploy better because their autodeploy is live and self-corrects on the next push. Treat this as a default habit, not a case-by-case judgment call: if a call sets a variable or updates config and you haven't deliberately decided you want a redeploy to happen as a result, add `skipDeploys: true`.

---

- Build complete, working code — not scaffolding with TODOs unless a task is explicitly phased for later.
- Match the stack decisions already locked in Volume 2 (FastAPI/Python backend, Next.js/React frontend, Supabase/PostgreSQL, Railway deployment) — don't introduce a different framework or pattern without flagging it as a blueprint deviation per the section above.
- Follow the database patterns established in Volume 3 exactly — snapshot/frozen-copy tables for anything Time Machine-relevant, append-only enforcement via triggers (not convention), RLS on every user-data table.
- When in doubt about a detail, check the blueprint before guessing.
