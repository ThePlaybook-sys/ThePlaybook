# Build Progress

## Current Phase: 0 — Repository, Environments, CI/CD

## Phase Status
- [ ] Phase 0 — Repository, Environments, CI/CD — IN PROGRESS
      - [x] Milestone 1: Repo structure decided and initialized (monorepo; `apps/api-gateway`, `apps/ai-orchestrator`, `apps/sports-intel-layer`, `apps/workers`, `apps/frontend`, each with a working health check and passing test)
      - [x] CI/CD workflow written (`.github/workflows/ci-cd.yml`) — test jobs verified in GitHub Actions (all green on PR #1); deploy jobs still skipped, see Notes
      - [x] Secrets management convention documented (`docs/ops/secrets-management.md`)
      - [x] Milestone 2: Three Railway environments (dev/staging/production) provisioned — project `theplaybook`, all 6 services (`api-gateway`, `ai-orchestrator`, `sports-intel-layer`, `worker-market-monitor`, `worker-scheduled`, `frontend`) exist across dev/staging/production
      - [x] Milestone 3: dev and staging verified live — all 6 services in both environments building via Dockerfile and passing healthchecks (`SUCCESS`) as of 2026-08-06. Production not yet deployed/verified (not blocking; can be done on request)
      - [ ] Sentry (or equivalent) wired to all services — NOT STARTED, blocked on Mac creating a Sentry account/DSN per CLAUDE.md Credentials & Connections
      - [ ] Acceptance criteria verified end-to-end — dev/staging deploy + healthcheck criterion met; CI-gates-deploy and rollback criteria still open, see Notes
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
- **Railway is connected and provisioned.** Project `theplaybook` (workspace `theplaybook-sys's Projects`) has dev/staging/production environments and all 6 services, each with `rootDirectory` correctly scoped to its `apps/<service>` subdirectory.
- **2026-08-06 — Deploy-blocking bugs found and fixed (all 6 services, dev + staging):**
  1. **Builder misconfiguration.** All deployments failed with "Detected Python / Using pip / No start command detected." Root cause: Railway's `dockerfilePath` setting alone is not sufficient — the separate `build.builder` field must be explicitly set to `DOCKERFILE`, or Railway silently defaults to Railpack auto-detection regardless of `dockerfilePath`. Fixed directly on all 6 Railway services in both environments (Railway-side config, not a repo change).
  2. **Frontend CVE block.** `next@14.2.15` carried two HIGH-severity CVEs (CVE-2025-55184, CVE-2025-67779); Railway's dependency scanner refused to build until patched. Fixed in PR #1: bumped to `next@14.2.35`.
  3. **Healthcheck failures post-build.** Once the builder fix took effect, all 4 Python services' Dockerfiles still failed their `/health` checks — they hardcoded `--port 8000` instead of reading Railway's injected `$PORT`, so Railway's healthcheck (which always probes `$PORT`) timed out. Fixed in PR #1: `CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]` in all 4 Python Dockerfiles.
  - PR #1 (`claude/playbook-phase0-railway-h5ohzr` → `dev`) merged 2026-08-06; CI green (5/5 test jobs); merge auto-triggered fresh deploys. All 12 dev+staging deployments confirmed `SUCCESS` via both the Railway API and the dashboard.
- **Supabase connector not yet installed.** Not required for Phase 0, but will block Phase 1 (Database Foundation) at that phase's start.
- Sentry account/DSN has not been set up — this is an API-key-category credential per CLAUDE.md (Mac creates the account and key himself); needed before Phase 0's error-tracking acceptance criterion can be verified.
- `RAILWAY_TOKEN` still not set as a GitHub Actions secret, so `ci-cd.yml`'s deploy jobs remain skipped (dev/staging deploys currently happen via Railway's own GitHub integration auto-deploy, not through the Actions workflow). Needed before the CI-gates-deploy acceptance criterion can be verified.
- "Wait for CI" / "disable autodeploy" toggles are dashboard-only settings, not exposed via the Railway MCP tools available in this session — needed so a failing test actually blocks a dev/staging deploy per Phase 0's testing requirements. Not yet configured; will need Mac to set these in the Railway dashboard, or a fallback approach flagged if that turns out to be blocking.
- Production environment has the same builder/dockerfilePath fix applied at provisioning time but has not been deployed or verified live — out of scope unless requested.
- Logged per CLAUDE.md's blueprint-vs-reality process: the builder-field and `$PORT` gotchas above are infra/build-tool behavior, not a blueprint deviation, so no CHANGELOG entry — Volume 2 §5/§9's Dockerfile-per-service approach is unchanged, this was purely a Railway configuration correction.
