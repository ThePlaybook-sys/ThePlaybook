# The Playbook

An AI-powered sports betting operating system — not a picks app.

The Playbook runs a committee of 22 specialized AI agents over normalized sports data to produce transparent, explainable betting recommendations, sized with Kelly Criterion staking, delivered through a chat-first interface. Every recommendation is reconstructable after the fact: the "Time Machine" capability replays exactly what the system knew and recommended at any point in the past, which is the mechanical proof behind the product's core trust claim.

This repository is under active development, building out from Phase 0 of a 12-phase roadmap. It is not yet a running product.

---

## Current Development Status

- **Active phase:** Phase 0 — Repository, Environments, CI/CD (see `PROGRESS.md` for the live checklist)
- **Live status of record:** `PROGRESS.md` at the repo root — updated as part of the same work that closes each milestone, not after the fact
- **Governing plan:** `docs/blueprint/engineering-roadmap-build-order.md` — 12 phases, each gated behind the previous phase's acceptance criteria being met and explicitly signed off

Phases are built strictly in order. Nothing from a later phase ships early, even if it would be convenient to build alongside current work — see `CLAUDE.md` for the full phase-gating rule.

---

## Repository Structure

```
ThePlaybook/
├── apps/
│   ├── api-gateway/         # FastAPI service — public API surface
│   ├── ai-orchestrator/     # FastAPI service — 22-agent committee, consensus, recommendations
│   ├── sports-intel-layer/  # FastAPI service — sports data ingestion & normalization
│   ├── workers/             # FastAPI service — scheduled jobs, market monitoring
│   └── frontend/            # Next.js app — dashboard, chat interface
├── docs/
│   ├── blueprint/           # Authoritative specification — see docs/blueprint/README.md
│   └── ops/                 # Operational runbooks (e.g. secrets management)
├── .github/workflows/       # CI/CD pipeline definitions
├── CHANGELOG.md             # Blueprint version history
├── CLAUDE.md                # Project instructions and working agreement
└── PROGRESS.md              # Live build status
```

Each service under `apps/` is an independently deployable Railway service with its own Dockerfile.

---

## Quick Start

Each service is self-contained. To run one locally:

```bash
# Python services (api-gateway, ai-orchestrator, sports-intel-layer, workers)
cd apps/<service>
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q          # run tests
uvicorn app.main:app --reload --port 8000

# Frontend
cd apps/frontend
npm install
npm run dev
```

There is no local orchestration (e.g. `docker-compose`) yet — that is not in scope until a later phase. See `docs/blueprint/engineering-roadmap-build-order.md` for when it lands.

---

## Technology Stack

- **Backend:** Python / FastAPI (4 services: `api-gateway`, `ai-orchestrator`, `sports-intel-layer`, `workers`)
- **Frontend:** Next.js / React / TypeScript
- **Database:** Supabase (PostgreSQL), with Row-Level Security on every user-data table
- **Cache / queue:** Redis (introduced per the environment data-source policy in Volume 2 §5)
- **Deployment:** Railway, one service per app, Dockerfile-based builds, three environments (dev / staging / production)
- **CI/CD:** GitHub Actions

Full rationale for each stack decision lives in `docs/blueprint/volume-2-system-architecture.md`.

---

## High-Level Architecture

```
                 ┌────────────┐
   Users ──────► │  frontend  │  (Next.js — chat-first dashboard)
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
│ (22-agent      │ │   layer     │ │(scheduled │
│  committee,    │ │(data ingest,│ │ jobs,     │
│  consensus,    │ │ normalize)  │ │ market    │
│  Kelly sizing) │ │             │ │ monitor)  │
└────────────────┘ └─────────────┘ └───────────┘
        │              │               │
        └──────────────┼───────────────┘
                        │
                 ┌──────▼──────┐
                 │  Supabase   │
                 │ (Postgres)  │
                 └─────────────┘
```

This is a summary for orientation only. The authoritative architecture — including the Recommendation Worker's proactive/on-demand dual entry points, the normalized multi-sport data core, and the full request lifecycle — lives in `docs/blueprint/volume-2-system-architecture.md` and `docs/blueprint/volume-4-ai-intelligence.md`.

---

## Documentation

The full specification lives in **`docs/blueprint/`**. Start with **`docs/blueprint/README.md`** — it explains what the Blueprint is, the reading order, how the documents depend on each other, and the current version of each document (read directly from each file's own header, not tracked separately).

This README stays intentionally high-level and does not duplicate that content.

---

## Development Workflow

1. Work happens on a feature branch, never directly on `dev` or `main`.
2. Open a pull request into `dev`. CI (`test-python-services`, `test-frontend`) must pass before merge.
3. On merge to `dev`, GitHub Actions deploys all 5 services to the **dev** Railway environment.
4. Promotion to **staging** happens via merge to `main`.
5. Promotion to **production** happens only via a `v*` tag push — production never deploys from a branch push, by design.

See `.github/workflows/ci-cd.yml` for the exact gating logic.

## Branch Strategy

- `dev` — integration branch, deploys to the dev environment on every push
- `main` — staging branch, deploys to the staging environment on every push
- `v*` tags — production releases, deploy to the production environment and only the production environment
- Feature branches — short-lived, merged into `dev` via pull request

## Environment Strategy

| Environment | Trigger | Data source | Audience |
|---|---|---|---|
| **dev** | Push to `dev` | Per Volume 2 §5's environment data-source policy | Internal development |
| **staging** | Push to `main` | Per Volume 2 §5's environment data-source policy | Internal pre-release validation |
| **production** | `v*` tag push only | Live data | End users |

Full detail, including exactly which data sources are permitted in which environment, is in `docs/blueprint/volume-2-system-architecture.md` §5.

## CI/CD Overview

GitHub Actions (`.github/workflows/ci-cd.yml`) runs on every push and pull request to `dev`/`main`:

- **`test-python-services`** — matrix job, runs `pytest` for each of the 4 Python services
- **`test-frontend`** — installs and builds the Next.js app as its test gate at this phase
- **`deploy-dev`** — on push to `dev`, after tests pass, deploys all 5 services to Railway's dev environment
- **`deploy-staging`** — on push to `main`, after tests pass, deploys all 5 services to Railway's staging environment
- **`deploy-production`** — on a `v*` tag push, after tests pass, deploys all 5 services to Railway's production environment

Deploys use the Railway CLI (`railway up`), authenticated via a `RAILWAY_TOKEN` scoped per GitHub Environment.

---

## Contributing

This is currently a single-developer build following the phase-gated roadmap in `docs/blueprint/engineering-roadmap-build-order.md`. If that changes, contribution guidelines will be added here.

## License

_Placeholder — no license has been selected yet._

## Contact / Ownership

_Placeholder — repository ownership contact to be added._
