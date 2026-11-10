# The Playbook (MANSA)

The Playbook, later branded **MANSA**, is an AI sports-analysis product. It gathers game and market data, runs a committee of specialized AI agents, and shows a recommendation — or a deliberate pass — with the reasoning behind it. A "Time Machine" feature is built to replay what the system knew when a decision was made.

This repository is under active development. It is not a finished public product.

> Status refreshed 2026-11-10 from the `dev` tree at `63be04f` (2026-11-10, 5:42 PM ET, PR #111). An earlier read-only audit covered `fcf96696` (2026-09-18, 21:43 UTC / 5:43 PM ET). Railway health and the GitHub Actions result for `63be04f` were not re-checked and stay **UNVERIFIED**.

---

## What this is / is not

> **For lawyer review.** This section is a plain-language product description, not legal advice. Please review before this README, the GitHub repo description, or public site copy is published.

**What this is**

- A subscription-style software product that analyzes sports games and market prices and presents explainable recommendations (or a pass) to a signed-in user.
- An internal engineering monorepo for that product: APIs, data workers, the AI committee, and a Next.js web app (the MANSA Command Center and public marketing pages).

**What this is not**

- Not a sportsbook, not a betting operator, and not a service that places, accepts, or processes bets.
- Not a guarantee of results. Confidence is how strongly the committee agreed; it is not a promise that an outcome will occur, and it is not financial or betting advice.
- Not a complete 22-agent committee yet. The blueprint describes 22 agents; **12 agent modules** exist in code today.
- Not a live chat, Telegram, or parlay product. Those appear in plans and in some marketing previews; they are not shipped as live features.
- Not a billed checkout flow. The pricing page shows Core $19.99 / Pro $34.99 / Elite $69.99, but payment processing is not wired.

---

## Current development status

Live status of record in the repo is `PROGRESS.md` on `dev` (a long running log). This README summarizes what the `dev` tree and recent commits support as of the refresh above.

- **Product brand in the app:** MANSA (Command Center at `/today`).
- **Last product workstream:** Phase 8 (contextual performance intelligence and live data/recommendation-worker autonomy), after Phase 6 (frontend) was recorded closed on 2026-09-02. Product commits on that stream stop at 2026-09-18 (`fcf96696`). The tip commit (`63be04f`, 2026-11-10) only repairs stale odds-cadence tests. It does not close Phase 8.
- **Roadmap:** `docs/blueprint/engineering-roadmap-build-order.md` now lists phases **0–14** (the old "12 phases" line is stale).
- **First confirmed live recommendation:** none in the repository. A first live run was armed for a 2026-09-19 scheduled tick; no later commit confirms that it produced a recommendation. Treat this as not yet confirmed.
- **CI:** On `fcf96696`, a 2026-11-10 audit reported that 5 `sports-intel-layer` tests failed (`apps/sports-intel-layer/tests/test_odds_cadence_persistence.py`) and `deploy-dev` was skipped, while api-gateway, ai-orchestrator, workers, and the frontend passed. That audit's clock for the run ("4:44 PM ET") does not match the commit timestamp (5:43 PM ET); the Actions time was not re-checked, so it stays **UNVERIFIED**. The same audit's last fully green CI on `dev` was reported as 2026-09-14, 8:09 AM ET — also **UNVERIFIED** on re-check. `63be04f` changes only those five tests (kickoff relative to now; the commit states there is no production code change). Whether GitHub Actions on `63be04f` passed, and whether `deploy-dev` ran, is **UNVERIFIED**. Current Railway deploy state is **UNVERIFIED**.
- **`main` (staging path):** last commit 2026-08-09; `dev` is 389 commits ahead and `main` has 2 commits not in `dev`. Staging/production freshness is **UNVERIFIED**.

### Phase checklist (matches the `dev` tree and `PROGRESS.md`, with gaps called out)

| Phase | Name | Status on `dev` |
|---|---|---|
| 0 | Repository, environments, CI/CD | **Closed** 2026-08-07 (tag `v0.0.1-phase0` recorded in `PROGRESS.md`; the tag exists in this clone) |
| 1 | Database foundation | **Closed** 2026-08-08 |
| 2 | Authentication | **Closed** 2026-08-10 (tag `v0.0.2-phase2` recorded; the tag exists in this clone) |
| 3 | Sports intelligence layer | **Mostly built** (adapters, workers, persistence). The formal checklist still leaves acceptance-suite item 3G open. |
| 4 | AI orchestrator | **Closed** 2026-08-25 for milestones 4.1–4.9. **12 of 22** planned agents have modules in `apps/ai-orchestrator/app/agents/`. Checklist still lists milestone 4.10 (first live-model validation) as not formally closed. |
| 5 | Recommendation pipeline | Milestones 5.1–5.5 (strategy, explainability, Time Machine snapshots, postgame grading, propose-only adaptive weighting) are in code. The historical header in `PROGRESS.md` calls Phase 5 closed 2026-08-27. The phase checkbox stays open because **Recommendation Lifecycle (5.6) is a locked specification only** — not implemented. |
| 6 | Product / UI / UX frontend | **Closed** 2026-09-02 (Mac visual sign-off recorded). Command Center, marketing pages, sign-in/sign-up, onboarding, account, recommendations, history/Time Machine, track record, and pricing UI are in the app. |
| 7 | Market integrity & anomaly intelligence | 7.0 / 7.0A / 7.0B Gate A recorded complete. **Line-move / unexplained-movement detection (7.1) exists as pure functions** (`apps/ai-orchestrator/app/features/market_integrity.py`) plus an orchestration helper that is **explicitly not wired** into the recommendation worker, cron, or an HTTP endpoint. 7.2–7.3 are not authorized. The `PROGRESS.md` historical header still leads with an older "Gate B blocked on credential" line; later notes describe odds capture work after that — treat that header as partly stale. |
| 8 | Contextual performance intelligence | **In progress.** Product and ops work through 2026-09-18 (`fcf96696`). The 2026-11-10 tip is a test-only repair, not a phase close. |
| 9 | Twilio integration | **Not started** |
| 10 | OCR / bet slip verification | **Not started** |
| 11 | Analytics | **Not started** |
| 12 | Growth & acquisition intelligence | **Not started** (and recorded as not authorized to build) |
| 13 | Beta | **Not started** |
| 14 | Production launch | **Not started** |

---

## What's in the product today (code on `dev`)

**Web app (`apps/frontend`, Next.js 14):** public marketing pages (home, about, features, how-it-works, pricing); email/password sign-in and create-account (`/sign-in`, including `?mode=sign-up`); onboarding (jurisdiction); account page that *displays* subscription fields when present; Command Center (`/today`); recommendation list/detail; history / Time Machine; track record. There is a dev-only populated preview at `/dev/command-center-preview`. A `/demo` area also exists. Checkout/Stripe is not in the frontend dependencies or pages.

**Backend:** four FastAPI services — `api-gateway`, `ai-orchestrator`, `sports-intel-layer`, `workers` — each with its own Dockerfile. Railway is set up in CI for six deployable services (the four above plus `worker-scheduled` and `worker-market-monitor`). Supabase (PostgreSQL) migrations and RLS tests live under `supabase/`.

**Data and analysis pipeline:** provider adapters (schedules, rosters, injuries, odds, weather, news, and related stats), scheduled workers, and a recommendation worker with safety gates. Error tracking: Sentry is documented and tested for the four Python services and cron dispatch; **the frontend has no Sentry package**.

**What is not live / not built yet (do not describe these as shipping):** Telegram companion, intelligent parlays, conversational chat as a product surface, Recommendation Lifecycle state changes, line-move detection in the running worker, payment checkout, Privacy/Terms pages, and a confirmed first live recommendation.

---

## Repository structure

```
ThePlaybook/
├── apps/
│   ├── api-gateway/         # FastAPI — public API surface
│   ├── ai-orchestrator/     # FastAPI — agent committee, consensus, recommendations
│   ├── sports-intel-layer/  # FastAPI — sports data ingestion & normalization
│   ├── workers/             # FastAPI — scheduled jobs and worker dispatch
│   └── frontend/            # Next.js — Command Center, marketing, auth
├── docs/
│   ├── blueprint/           # Product and engineering specification
│   ├── business/            # Business / entitlement planning docs
│   └── ops/                 # Operational runbooks and dated audits
├── supabase/                # Migrations, seed, database tests
├── scripts/                 # e.g. Phase 2 E2E helper
├── backups/                 # Dev data-recovery snapshots (ops)
├── .github/workflows/       # CI/CD
├── CHANGELOG.md
├── CLAUDE.md                # Project working agreement
└── PROGRESS.md              # Live (and very long) build log
```

Each service under `apps/` is intended as an independently deployable Railway service with its own Dockerfile. There is no local `docker-compose` in this repo.

---

## Quick start

Each service is self-contained. To run one locally:

```bash
# Python services (api-gateway, ai-orchestrator, sports-intel-layer, workers)
cd apps/<service>
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
uvicorn app.main:app --reload --port 8000

# Frontend
cd apps/frontend
npm install
npm test
npm run dev
```

---

## Technology stack

- **Backend:** Python / FastAPI (four services listed above)
- **Frontend:** Next.js 14 / React / TypeScript (Vitest for tests)
- **Database:** Supabase (PostgreSQL), with Row-Level Security on user-data tables
- **Cache / queue:** Redis is in the architecture docs; a hosted Redis was previously deferred — current provisioning is **UNVERIFIED**
- **Deployment:** Railway, Dockerfile-based builds, three environments (dev / staging / production)
- **CI/CD:** GitHub Actions (`.github/workflows/ci-cd.yml`)
- **Error tracking:** Sentry on the four Python services and cron; not on the frontend

---

## High-level architecture

```
                 ┌────────────┐
   Users ──────► │  frontend  │  (Next.js — Command Center + marketing)
                 └─────┬──────┘
                       │
                 ┌─────▼──────┐
                 │ api-gateway│  (public API surface)
                 └─────┬──────┘
                       │
        ┌──────────────┼───────────────┐
        │              │               │
┌───────▼──────┐ ┌─────▼───────┐ ┌─────▼─────┐
│ai-orchestrator│ │sports-intel-│ │  workers  │
│ (agent         │ │   layer     │ │(scheduled │
│  committee,    │ │(data ingest,│ │ jobs)     │
│  consensus)    │ │ normalize)  │ │           │
└────────────────┘ └─────────────┘ └───────────┘
                       │
                 ┌─────▼──────┐
                 │  Supabase  │
                 │ (Postgres) │
                 └────────────┘
```

This is orientation only. The authoritative architecture is in `docs/blueprint/`, especially volume 2 (system architecture) and volume 4 (AI intelligence).

---

## Documentation

The specification lives in **`docs/blueprint/`**. Start with **`docs/blueprint/README.md`**. Dated operational reports are in `docs/ops/`. This README stays high-level and does not duplicate those documents.

---

## Development workflow

1. Work happens on a feature branch, not directly on `dev` or `main`.
2. Open a pull request into `dev`. CI (`test-python-services`, `test-frontend`) must pass before merge.
3. On merge to `dev`, GitHub Actions is configured to deploy all six Railway services to the **dev** environment — **but only if tests pass**. On `fcf96696` the audit reported that deploy was skipped because sports-intel-layer tests failed. The current tip (`63be04f`) is the in-repo repair for those tests. Whether that commit's Actions run passed and deployed is **UNVERIFIED**.
4. Promotion to **staging** is configured via merge to `main`.
5. Promotion to **production** is configured only via a `v*` tag push.

See `.github/workflows/ci-cd.yml` for the exact gating logic.

### Branch strategy

- `dev` — integration branch; intended to deploy to the dev environment on every push
- `main` — staging branch; intended to deploy to staging on every push
- `v*` tags — production releases
- Feature branches — short-lived, merged into `dev` via pull request

---

## Contributing

This is currently a single-team build following the phase-gated roadmap in `docs/blueprint/engineering-roadmap-build-order.md`. If that changes, contribution guidelines will be added here.

## License

_Placeholder — no license has been selected yet._

## Contact / ownership

_Placeholder — repository ownership contact to be added._
