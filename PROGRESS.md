# Build Progress

## Current Phase: 0 — Repository, Environments, CI/CD

## Phase Status
- [ ] Phase 0 — Repository, Environments, CI/CD — IN PROGRESS
      - [x] Milestone 1: Repo structure decided and initialized (monorepo; `apps/api-gateway`, `apps/ai-orchestrator`, `apps/sports-intel-layer`, `apps/workers`, `apps/frontend`, each with a working health check and passing test)
      - [x] CI/CD workflow written (`.github/workflows/ci-cd.yml`) — test jobs verified locally; not yet run in GitHub Actions
      - [x] Secrets management convention documented (`docs/ops/secrets-management.md`)
      - [ ] Milestone 2: Three Railway environments (dev/staging/production) provisioned — BLOCKED, see Notes
      - [ ] Milestone 3: CI/CD pipeline deploying to `dev` automatically, verified live — BLOCKED on Milestone 2
      - [ ] Sentry (or equivalent) wired to all services — NOT STARTED
      - [ ] Acceptance criteria verified end-to-end — NOT STARTED
      - [ ] Testing requirements run (failing-test-blocks-deploy check, manual rollback test) — NOT STARTED
- [ ] Phase 1 — Database Foundation — NOT STARTED
- [ ] Phase 2 — Authentication — NOT STARTED
- [ ] Phase 3 — Sports Intelligence Layer — NOT STARTED
- [ ] Phase 4 — AI Orchestrator — NOT STARTED
- [ ] Phase 5 — Recommendation Pipeline — NOT STARTED
- [ ] Phase 6 — Dashboard / Core Frontend — NOT STARTED
- [ ] Phase 7 — Twilio Integration — NOT STARTED
- [ ] Phase 8 — OCR / Bet Slip Verification — NOT STARTED
- [ ] Phase 9 — Analytics — NOT STARTED
- [ ] Phase 10 — Beta — NOT STARTED
- [ ] Phase 11 — Production Launch — NOT STARTED

## Notes

- Full blueprint document set is complete: all five volumes, `v2.0-amendments-architecture-review.md`, `engineering-roadmap-build-order.md`, and `CHANGELOG.md` are in place and internally consistent as of CHANGELOG v2.0.2.
- **Blocked on Railway access.** The Railway MCP connector is not yet installed/authorized for this Claude.ai workspace (confirmed via connector search — `installState: "not_installed"`). Mac is in the process of installing/authorizing it. Until it's connected (or a Railway API token is provided as a fallback), Milestone 2, Milestone 3, and Phase 0's acceptance criteria (real environments existing and network-isolated, a trivial push actually deploying, rollback tested) cannot be completed — CI/CD deploy jobs in `ci-cd.yml` reference `secrets.RAILWAY_TOKEN`, which does not exist yet.
- **Supabase connector also not yet installed** (`installState: "not_installed"`). Not required for Phase 0, but will block Phase 1 (Database Foundation) at that phase's start.
- Sentry account/DSN has not been set up — this is an API-key-category credential per CLAUDE.md (Mac creates the account and key himself); needed before Phase 0's error-tracking acceptance criterion can be verified.
- Once Railway access exists: still need (a) `RAILWAY_TOKEN` set as a GitHub Actions secret, scoped per GitHub Environment (`dev`/`staging`/`production`), and (b) those three GitHub Environments actually created in repo settings, matching the branch/tag mapping the workflow already assumes.
- No blueprint/reality deviations logged yet — Phase 0 scaffolding has followed Volume 2 §5/§9 as written.
