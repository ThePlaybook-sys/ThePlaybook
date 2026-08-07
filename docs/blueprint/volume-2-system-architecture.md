# The Playbook — Volume 2
## System Architecture, Backend Design, Railway Deployment, API Strategy, AI Orchestration, DevOps

**Version:** v4.0
**Last updated:** 2026-08-06
**Depends on:** Volume 1 (v3.0) — subscription tiers, personas, and core product principles are treated as fixed constraints here
**v4.0 note:** Core Architecture Principles added (§1.1) as the explicit lens for future decisions. Recommendation Worker added (§4.4) — proactive recommendation generation coexisting with on-demand. Environment data-source policy formalized (§5). See `CHANGELOG.md` v4.0 entry for full reasoning.
**Read next:** Volume 3 (Database Architecture) — this volume defines the services that read/write the schema Volume 3 will specify

---

## 1. Guiding Principles (Carried Forward From the Master Spec)

Before any framework or hosting decision, three constraints from the master spec shape everything in this volume:

1. **No web scraping, ever.** All external sports/odds data flows through one internal Sports Intelligence Layer. Nothing else in the system talks to a provider directly.
2. **Nothing is a black box.** Every recommendation must be reconstructible months later (Time Machine requirement). This is an architecture requirement, not just a data requirement — it means snapshotting, not just logging.
3. **The AI Orchestrator must be able to swap models without a redesign.** OpenAI and Claude are both in play today; whatever routes between them can't hardcode either one as "the" model.

Everything below is built to satisfy these three constraints first, convenience second.

### 1.1 Core Architecture Principles (v4.0)

Ten principles, added as the explicit lens for future architectural decisions rather than leaving that judgment implicit across five volumes. Several are restatements of decisions already made elsewhere — collected here so a future decision can be checked against a short list instead of re-deriving the reasoning from scratch each time:

1. **Download once, reuse everywhere.** Never repeatedly call an external API for the same information — store it in Supabase, read from there. (Already the entire reason the Sports Intelligence Layer and Redis cache exist, §8.)
2. **Background workers gather data; the AI does not collect raw data during a user request.** Every agent reasons over already-assembled intelligence (`daily_game_intelligence`, Volume 3 §4.1), never over a live external API call mid-request.
3. **AI reasons, workers gather.** A clean separation of responsibility — an agent's job is judgment, not fetching.
4. **Store intelligence, not just raw data.** The derived score tables and `daily_game_intelligence` (Volume 3 §4.1–§4.2) exist because precomputed judgment is more valuable than a pile of numbers an agent has to re-derive every time.
5. **Every recommendation must be explainable.** (Volume 4 §8 — already load-bearing.)
6. **Everything must be observable.** (§9's per-component latency tracking, error tracking, health checks.)
7. **Every recommendation must be reproducible.** (Volume 3's Time Machine principle — the project's oldest and most-repeated constraint.)
8. **Optimize for scalability** — but not prematurely. This principle and #10 below are in tension on purpose; #10 wins at MLP stage.
9. **Optimize for user trust** over engagement, win rate, or any other metric that could conflict with honesty (Volume 1 §1's core tension).
10. **Keep Phase 0 intentionally focused.** Scalability work for sports that aren't NFL, features without a proven MLP-stage consumer, and infrastructure without a proven need all get deferred — not because they're bad ideas, but because building them now is the more expensive time to build them wrong. This is the same reasoning that's driven every deferral logged in this changelog so far (Knowledge Graph, Public Transparency Portal, the bulk of the ~150-table proposal, sportsbook promotions, social sentiment).

---

## 2. Backend Framework: FastAPI vs. Node.js

**Recommendation: FastAPI (Python).**

The master spec asked for this decision to be justified, not assumed, so here's the actual tradeoff analysis rather than a default.

| Factor | FastAPI (Python) | Node.js | Winner |
|---|---|---|---|
| AI/ML ecosystem | Native — OpenAI SDK, Anthropic SDK, numpy/pandas/scikit-learn all first-class, needed later for the Continuous Learning Engine's calibration work (Volume 4) | Workable via SDKs, but numerical/ML work means shelling out to Python anyway eventually | **FastAPI** |
| Async I/O performance | Excellent (async/await native, ASGI) — comparable to Node for concurrent API calls to multiple providers/agents | Excellent, this is Node's home turf | Tie |
| Data validation | Pydantic gives you schema validation and type safety for free on every request/response — directly useful for the Explainability Engine's structured outputs | Requires a separate library (Zod, etc.) bolted on | **FastAPI** |
| Team familiarity / hiring | Slightly smaller talent pool than Node, but growing fast in AI-adjacent hiring | Larger overall pool | Node (minor) |
| Supabase/Twilio SDK support | Good, well-maintained Python clients | Slightly more mature JS clients (Supabase's JS SDK is the primary one) | Node (minor) |

**Why FastAPI wins overall:** This platform's hardest engineering problems — orchestrating multiple AI agents, calibrating confidence scores, running the adaptive weighting system, eventually training/fine-tuning components of the Continuous Learning Engine — are all Python-native problems. Node would work for the CRUD/API surface, but you'd end up standing up a second Python service for the ML-heavy parts anyway (agent evaluation, calibration, weighting), which means two languages, two deploy pipelines, and a network hop between them for no real gain. Better to commit to one stack that's strong everywhere the hard problems live, and accept a marginally smaller frontend-adjacent talent pool as the tradeoff.

**What this decision does NOT mean:** the frontend stays Next.js/React regardless (Volume 5) — this is a backend-only decision. FastAPI serves a clean REST/JSON API; the frontend doesn't know or care what language generated it.

---

## 3. High-Level System Architecture

```
                              ┌─────────────────────┐
                              │   Next.js Frontend    │
                              │   (Volume 5)          │
                              └──────────┬───────────┘
                                         │ REST / JSON
                              ┌──────────▼───────────┐
                              │   FastAPI Gateway     │
                              │  (Auth, Rate Limit,   │
                              │   Request Routing)    │
                              └──────────┬───────────┘
                 ┌────────────────────────┼────────────────────────┐
                 │                        │                        │
        ┌────────▼────────┐    ┌─────────▼─────────┐    ┌─────────▼─────────┐
        │  AI Orchestrator │    │  Sports Intel      │    │  User/Sub/Auth    │
        │  + Agent Committee│    │  Layer (adapters)  │    │  Engines          │
        └────────┬────────┘    └─────────┬─────────┘    └─────────┬─────────┘
                 │                        │                        │
        ┌────────▼────────────────────────▼────────────────────────▼─────────┐
        │                        Supabase (PostgreSQL)                        │
        │           Auth · Realtime · Storage · Edge Functions                │
        └───────────────────────────────┬───────────────────────────────────┘
                                         │
                              ┌──────────▼───────────┐
                              │  Background Workers   │
                              │  (Market Monitor,     │
                              │   Postgame Review,    │
                              │   Weight Recalc)       │
                              └───────────────────────┘
```

Four service types, all deployed on Railway (Section 5):

1. **API Gateway** — the only thing the frontend ever talks to. Handles auth, rate limiting, request routing to internal engines.
2. **AI Orchestrator service** — stateless compute that fans out to the agent committee, runs the consensus engine, and returns a recommendation package. Detailed in Section 7.
3. **Sports Intelligence Layer** — the adapter layer to external providers (Section 8). Nothing outside this service ever calls a provider directly.
4. **Background workers** — long-running or scheduled processes: market monitoring, postgame review generation, agent weight recalculation, notification dispatch.

---

## 4. Service Breakdown

### 4.1 API Gateway (FastAPI)
Owns: authentication, request validation, rate limiting, routing to internal engines, response shaping. This is deliberately kept thin — it should not contain business logic. Its job is traffic control, not decision-making.

### 4.2 AI Orchestrator Service
Owns: model routing decisions, agent fan-out, consensus resolution, confidence gating, explainability packaging. This is the most complex service in the system and gets its own full treatment in Volume 4 — this volume only defines its *deployment shape* (stateless, horizontally scalable, no persistent state between requests beyond what's written to Postgres).

### 4.3 Sports Intelligence Layer
Owns: provider adapters (odds, stats, weather, injuries, rosters, schedules), normalization into one internal data model, caching to avoid redundant provider calls. Detailed in Section 8.

### 4.4 Background Workers
Owns: anything that runs on a schedule or reacts to an external event rather than a user request — market monitoring (continuous), postgame review generation (triggered by game completion), agent weight recalculation (scheduled, e.g. weekly), notification dispatch (event-triggered).

**Recommendation Worker (v4.0).** Previously, a recommendation only existed once a user asked for one — the flow was strictly on-demand: user request → Orchestrator → response. This adds a proactive path: `Master Refresh (Volume 3 §4.1) → Recommendation Worker → AI Committee (Volume 4 §2) → store recommendations`, running shortly after each Master Refresh so that a recommendation already exists by the time a user opens the app, rather than being computed live in front of them. **This coexists with, not replaces, on-demand generation** — the NL Engine (Volume 4 §7) can still trigger a fresh Orchestrator run for a specific request (e.g., "build me something around Mahomes") that the proactive worker wouldn't have anticipated. Documented here and in Volume 4 §3.1, since both the trigger (this volume) and the reasoning it triggers (Volume 4) need to agree on the flow.

**Why separate workers from the API Gateway:** Market monitoring in particular needs to run continuously regardless of whether any user has an active request in flight. Bundling that into the request/response API service would mean either blocking user requests or building ad-hoc background threading inside a service that's supposed to be stateless and horizontally scalable. Keeping workers separate lets each piece scale independently — you might need ten API Gateway instances during Sunday NFL traffic but only one market-monitoring worker running continuously.

### 4.5 Scoped Internal Event System (v2.0)

Added per the external architecture review, deliberately scoped down from the review's original proposal of a full event-driven architecture connecting every service. **At MLP stage, this uses Postgres LISTEN/NOTIFY** — no new infrastructure, since Supabase already provides it — rather than a dedicated message broker.

**Events implemented at MLP stage:**
- `RecommendationCreated`
- `RecommendationUpdated`
- `RecommendationWithdrawn`
- `GameFinished`
- `AgentWeightsUpdated`

**Events deferred to post-MLP** (real value, but no independent consumer exists yet at MLP scope): `GameStarted`, `InjuryUpdated`, `WeatherChanged` (the Market Monitoring worker's own internal logic can stay synchronous until multiple independent consumers need to react to these), `UserSubscribed`, `OCRCompleted` (both tied to features that are themselves post-MLP or early-MLP-adjacent per the Engineering Roadmap).

**Why scoped instead of full event-driven architecture:** a message broker and event schema versioning system is real operational weight this project's small-team, MLP-first strategy (Volume 1 §9) argues against front-loading. The scoped version delivers concrete value immediately — `RecommendationCreated`/`Updated`/`Withdrawn` directly power the Recommendation Timeline component (Volume 5 §4.2) — without the footprint of infrastructure that doesn't have proven consumers yet. If volume ever justifies it, migrating from LISTEN/NOTIFY to a dedicated broker (Redis pub/sub, or a proper queue) is a contained upgrade, not a rearchitecture, since the event *contracts* (names and payloads) don't change, only the transport.

**Where it plugs into the architecture diagram above:** the Background Workers box both publishes events (Market Monitor → `RecommendationWithdrawn`, `GameFinished`) and the API Gateway/frontend subscribes to a subset (`RecommendationUpdated`, `RecommendationWithdrawn`) via Supabase Realtime, which is what Volume 5 §2 already established as the mechanism for live dashboard updates — this section is the source of those events, not a separate system from what Volume 5 assumed.

---

## 5. Railway Deployment Strategy

**Environments:** `dev`, `staging`, `production` — three separate Railway environments, not just branches within one. This matters specifically because of the Time Machine requirement (Volume 1, principle 2): staging needs to be able to test against real provider data without any risk of a staging recommendation snapshot polluting the production reproducibility record.

**Official environment data-source policy (v4.0)** — this was previously only an informal note in the Engineering Roadmap's Phase 1 testing section; formalized here as the volume that actually owns environment strategy:

| Environment | Data Source | Users |
|---|---|---|
| **Development** | Sandbox APIs where the provider offers them, fake/seeded data otherwise | None — internal only |
| **Staging** | Real APIs, real odds, real schedules — mirrors production behavior | Internal testers only |
| **Production** | Real APIs, live traffic | Real customers |

Staging exists specifically to catch problems with real data before customers see them — using fake data in staging would defeat that purpose, and using real data in dev would burn API quota and provider rate limits on rapid, throwaway iteration. Each environment's data policy should be enforced at the adapter configuration level (§8), not left as a convention a developer has to remember when switching environments.

**Services per environment (Railway project structure):**
- `api-gateway`
- `ai-orchestrator`
- `sports-intel-layer`
- `worker-market-monitor` (always-on)
- `worker-recommendation` (v4.0 — proactive generation, §4.4)
- `worker-scheduled` (cron-triggered: postgame review, weight recalc)
- Supabase is *not* hosted on Railway — it's a separate managed service (Section 6, Volume 3 owns schema)

**Scaling approach:** Start with Railway's autoscaling on `api-gateway` and `ai-orchestrator` (these see traffic spikes tied to game schedules — Sunday NFL windows will dwarf a random Tuesday). `sports-intel-layer` and workers can run on fixed, smaller instances at launch since their load is more predictable (polling intervals, not user-driven spikes).

**Why Railway over raw AWS/GCP at this stage:** Railway's git-push deploys and built-in environment management dramatically reduce DevOps overhead for a small team, which matters when the same person or a very small team is wearing the product, business, and engineering hats simultaneously. This is the right tradeoff for launch and the first 6–12 months. Flag now, for a future major-version decision: if the platform reaches a scale where Railway's pricing or infrastructure control becomes limiting (hundreds of thousands of users, per the master spec's scalability target), migrating the containerized services to AWS ECS/Fargate is a straightforward move *because* everything is already containerized — this is a reason to keep Dockerfiles clean and provider-agnostic from day one rather than leaning on Railway-specific magic.

---

## 6. API Strategy

**Versioning:** All routes under `/v1/`. No exceptions, even for internal-only endpoints — this habit prevents painful breaking changes later once the frontend and any future mobile apps depend on a stable contract.

**Authentication:** Supabase Auth issues JWTs; API Gateway validates on every request. Service-to-service calls (Orchestrator → Sports Intel Layer, workers → Orchestrator) use a separate internal service token, never the user's JWT, to keep the blast radius of a leaked internal token limited to internal services.

**Rate limiting:** Tiered by subscription level (Volume 1, Section 2) — Free tier gets the tightest limits, Elite the loosest, enforced at the Gateway before a request ever reaches the Orchestrator. This double-serves as cost control on AI API spend, since Free-tier users are the least monetized but could otherwise generate the same compute cost as Elite users.

**Key endpoint groups:**
- `/v1/recommendations` — current recommendations, filtered by sport/user
- `/v1/recommendations/{id}/explain` — full explainability payload for one recommendation
- `/v1/recommendations/{id}/snapshot` — Time Machine reconstruction endpoint
- `/v1/chat` — natural language interface entry point (routes to NL Engine, Volume 4)
- `/v1/betslip` — optional OCR upload
- `/v1/user/profile`, `/v1/user/betting-dna`
- `/v1/webhooks/twilio` — inbound SMS
- `/v1/webhooks/provider/*` — inbound provider push notifications where supported (injury alerts, line movement), reducing reliance on polling

**Webhooks over polling where possible:** For providers that support push (injury news, breaking line movement), prefer webhooks into the Market Monitoring worker over constant polling — cheaper, faster, and reduces the chance of hitting provider rate limits during high-traffic windows like Sunday mornings.

---

## 7. AI Orchestration Architecture

This is a deployment-shape overview; full agent-level detail belongs in Volume 4. What belongs here is *how the orchestrator is deployed and structured as a service.*

**Model routing:** The Orchestrator holds a routing table (stored in Postgres, not hardcoded) mapping task type → preferred model → fallback model. This satisfies the master spec's "swap models without redesign" requirement — updating the routing table is a data change, not a deploy.

**Execution pattern:** Agent fan-out is async and parallel — all ~20 committee agents (Volume 4 defines the full list) execute concurrently against the same game snapshot rather than sequentially, since they're independent analyses. This is a hard requirement for latency: sequential execution of 20 agents, each making an LLM call, would make the natural-language chat interface feel unusably slow.

**Consensus + confidence gating:** After fan-out completes, the Consensus Engine runs as a synchronous step against all agent outputs. If aggregate confidence falls below threshold, the Orchestrator returns "No Bet Today" rather than publishing a low-confidence recommendation — this is where Volume 1's core principle #1 becomes actual code, not just philosophy.

**Cost/latency/quality balancing:** The routing table should weight this explicitly per subscription tier (tying back to Volume 1's Elite "priority agent compute" feature) — Elite tier requests can afford a slower, higher-quality model pass or a second reasoning pass on disagreement; Free/Pro tier requests use faster/cheaper routing by default. This needs a concrete metric to avoid becoming vague marketing language: recommend defining "priority compute" as Elite requests get a mandatory second-pass reconciliation step whenever agents disagree beyond a defined variance threshold, while Pro/Free accept the first-pass consensus. Volume 4 should finalize the exact threshold.

---

## 8. Sports Intelligence Layer & Provider Adapter Pattern

**Adapter pattern, strictly enforced:** Each external provider (odds, stats, weather, injuries, rosters, schedules) gets its own adapter implementing a shared internal interface. No other service — not the Orchestrator, not any agent, not any worker — ever imports a provider SDK directly. They only ever talk to the Sports Intelligence Layer's normalized internal models.

**Why this matters practically, not just architecturally:** Odds and sports data providers get acquired, change pricing, throttle limits, or degrade in quality more often than most external APIs. If provider-specific code is scattered across the Orchestrator and agents, replacing a provider becomes a system-wide hunt-and-replace. With the adapter pattern, replacing a provider means writing one new adapter that implements the existing interface — nothing upstream changes.

**Multi-provider strategy (per master spec):** Separate providers per data category rather than one all-in-one provider, specifically so a problem with one (e.g., an odds provider outage) doesn't take down injury or weather data. Recommend maintaining at least one documented fallback provider per category before launch, even if not actively integrated — this shortens the response time if a primary provider has an outage during a live NFL Sunday.

**Named vendor candidates for Phase 3 (v3.0):** the adapter pattern above means these are swappable by design, but a real default has to be picked to start building against:

| Adapter Category | Default Vendor | Fallback |
|---|---|---|
| Odds | The Odds API | (document a second before launch, per the paragraph above) |
| Player/team stats, injuries, rosters, schedules | SportsDataIO | — |
| Weather | WeatherAPI | OpenWeatherMap |
| News/sentiment | NewsAPI | GNews |

**Caching — Redis (v3.0):** the Sports Intelligence Layer caches normalized responses in Redis, sitting in front of every adapter, with category-appropriate TTLs — odds data needs near-real-time freshness (seconds), injury/roster data can tolerate minutes, weather can tolerate longer. Cached responses are shared across all users, not per-user — this is both a cost control (fewer provider calls) and a load control (protects against provider rate limits during traffic spikes), and matters most during concentrated windows like Sunday NFL slates where hundreds of users are effectively asking for the same data at once.

**Concrete refresh cadences (v3.0) — replaces the previously vague "category-appropriate" language with real numbers:**

| Worker | Cadence | Purpose |
|---|---|---|
| Master Refresh | Daily, 6:00 AM | Full pull: games, odds, props, injuries, weather, news, rosters, schedule updates — this feeds `daily_game_intelligence` (Volume 3 §5.1) |
| Odds Worker | Every 5 minutes | Refresh `odds_snapshots` |
| Player Props Worker | Every 5 minutes | Refresh prop markets specifically — highest volatility, highest user interest |
| Injury Worker | Every 10 minutes | Refresh injury reports |
| Weather Worker | Every 15 minutes | Refresh weather snapshots |
| News Worker | Every 15 minutes | Refresh news/sentiment feed |
| Pregame Worker | Triggered, T-minus kickoff | Final refresh of all critical data immediately before a game starts — catches last-minute inactive lists and line moves the scheduled cadences might miss by a few minutes |

**Why exact cadences matter enough to specify (not just "make it fast"):** the AI Transparency Meter's `data_quality` dimension (Volume 5 §5, v2.0) needs a real, calculable number — "how stale is this data right now" only means something if there's a known cadence to measure staleness against. Vague TTLs made that dimension a placeholder; concrete cadences make it real.

---

## 9. DevOps & CI/CD

**Pipeline:** GitHub Actions → Railway, triggered on merge to environment-mapped branches (`dev` branch → dev environment, `main` → staging, tagged release → production). Every deploy runs the test suite before it's allowed to promote — no manual "just push it" deploys to production, even under time pressure, since a bad Orchestrator deploy during a live NFL Sunday is the worst-case failure mode for this specific product.

**Secrets management:** Railway's environment variable management per-environment, never committed to the repo. Provider API keys, model API keys, and the internal service token (Section 6) are the highest-sensitivity secrets — recommend rotating model API keys on a defined schedule (quarterly) rather than only on suspected compromise.

**Observability stack:**
- **Structured logging** across all services, correlated by a request ID that follows a single recommendation from user request through agent fan-out to final response — this correlation ID is what makes the Time Machine reconstruction practical from a systems standpoint, not just a database standpoint.
- **Error tracking** (e.g., Sentry) on all services, with the Orchestrator and Sports Intelligence Layer getting the tightest alerting — these are the two services where a silent failure is most costly (a silent Sports Intel failure could feed stale odds into a live recommendation without anyone noticing).
- **Uptime/health checks** on all services, feeding the System Health Dashboard defined in Volume 1's dashboard list.
- **Per-component latency tracking (v2.0):** attached to the same correlation ID above — recommendation end-to-end, individual agent, provider call, consensus computation, database query, and API response latency each tracked separately. This is a natural extension of tracing infrastructure that already needed to exist for Time Machine purposes, not a new system; it answers "which layer is slow" instead of just "the request was slow."

**Rollback strategy:** Railway's deployment history supports one-click rollback; the team's operating rule should be that any production incident during a live game window triggers immediate rollback to last-known-good rather than attempting a hotfix live — diagnose and fix in staging, redeploy properly afterward.

**Disaster recovery targets (v2.0):**
- **RPO (Recovery Point Objective):** no worse than the interval between automated Supabase backups — if backups run every 24 hours, that's the maximum acceptable data loss window. Verify the actual backup interval against Supabase's plan tier and tighten if the default doesn't meet this.
- **RTO (Recovery Time Objective):** scoped against the "immediate rollback during a live game window" incident protocol already established above — a code-level rollback should complete in minutes; a full data-restore scenario is the harder case and needs its own explicit target, recommended at under 4 hours for MLP stage.
- **Restore testing:** the backup restore procedure must be tested at least once before Phase 10 (Beta) in the Engineering Roadmap, not assumed to work because it's configured — an untested backup is not a real backup.

---

## 10. Security Touchpoints (Cross-Reference to Later Detail)

Full security architecture (RLS policies, encryption, threat modeling) belongs in Volume 3 (database-level) and gets a dedicated pass, but three decisions belong here because they're deployment-level, not schema-level:

- **Internal service token** (Section 6) is a system-architecture decision — it exists specifically so a compromised frontend-facing JWT can't be used to call internal-only endpoints directly.
- **Environment isolation** (Section 5) exists specifically so a staging/dev compromise can't touch production data or pollute the Time Machine reproducibility record.
- **AI abuse protection (v2.0):** three specific defenses, added per the external architecture review — (1) prompt injection filtering on all Natural Language Engine inputs (Volume 4 §7) before they reach any model call, since the NL Engine is the one place user-supplied free text flows directly into a model prompt; (2) rate limiting tuned specifically against SMS flooding (Twilio inbound, Volume 5 §7), distinct from and in addition to the standard tier-based API rate limits in Section 6, since SMS abuse has a different cost profile (per-message carrier cost) than API abuse; (3) circuit breakers on the Orchestrator to stop a single runaway request (e.g., a malformed retry loop) from cascading into a token-exhaustion cost or availability incident — the breaker should trip on either an elapsed-time or a call-count threshold per request, whichever is hit first.

---

## 11. Open Decisions Carried to Later Volumes

- **Routing table schema** (Section 7) needs a concrete table definition in Volume 3 — model, task type, fallback, per-tier compute rules.
- **Agent list and individual agent specs** (referenced in Section 7) are fully owned by Volume 4.
- **Confidence variance threshold** for Elite-tier second-pass reconciliation (Section 7) needs a specific number, to be set in Volume 4 and reflected back here if it changes the deployment/latency assumptions in this volume.
- **Dashboard data contracts** for the System Health Dashboard (Section 9) need to be defined jointly with Volume 5.

---

## Changelog Entry for This Version

See `CHANGELOG.md` — v1.0, 2026-08-05, Volume 2 added. Updated to v2.0, 2026-08-05, per external architecture review — scoped internal event system (§4.5), AI abuse protection and disaster recovery targets (§9–§10), and per-component observability (§9) integrated into the sections above, not just noted in the version header. Updated to v3.0, 2026-08-05 — Redis, named vendor candidates, and concrete worker cadences integrated into §8. Updated to v4.0, 2026-08-06 — Core Architecture Principles (§1.1), Recommendation Worker (§4.4), and environment data-source policy (§5) integrated directly, per the internal markdown-consistency review.
