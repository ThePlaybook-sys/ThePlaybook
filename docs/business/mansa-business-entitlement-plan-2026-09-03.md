# MANSA Business + Entitlement Planning Package (2026-09-03)

**Status: PLANNING ONLY. Nothing in this document has been implemented.**
No billing code, Stripe integration, entitlement enforcement, usage
metering, or database migration exists as a result of this document. No
Railway/Supabase/provider subscription was changed to produce it. This
is the four-step sequence HQ requested after Public Web M3 and the NFL
provider diagnostics: (1) lock a provider-cost hypothesis, (2) run an
economic stress test, (3) draft tier entitlements, (4) design (not
build) a billing/metering architecture.

**Sources used:** `docs/ops/nfl-provider-bakeoff-2026-09-03.md`,
`docs/ops/nfl-provider-gap-test-mysportsfeeds-2026-09-03.md`,
`docs/ops/nfl-provider-decision-record.md`, `PROGRESS.md`'s 2026-08-10
procurement-checkpoint entries (The Odds API, SportsDataIO, Weather,
News), `docs/blueprint/volume-1` (business model, pricing copy),
`volume-2` (Railway/Supabase/Redis/Twilio architecture, §8/§9),
`volume-4` (agent committee — real implemented count and execution
model), the `apps/frontend` pricing page (`Core $19.99` / `Pro $34.99` /
`Elite $69.99`, from Public Web M3), and current published vendor
pricing pages (WebSearch, since direct vendor-site fetches are blocked
by this workspace's own egress policy — same constraint documented in
both provider diagnostic reports).

**No missing price was invented anywhere in this document.** Every
dollar figure below is labeled CONFIRMED, ASSUMPTION, or UNKNOWN — see
the ledger at the end of Step 1. Where a real number doesn't exist yet,
the line says so and is excluded from confirmed totals, never papered
over with a guess.

---

## STEP 1 — Provider-Cost Hypothesis

### NFL data-provider stack

| Provider | Role | Cost | Status |
|---|---|---|---|
| **BALLDONTLIE** | Primary NFL provider — current-season schedules, rosters, injuries, player/advanced stats | **$39.99/mo** (GOAT tier, 600 req/min, unlocks advanced stats/player props/rosters per the vendor's own published pricing page) | **ASSUMPTION.** The free tier (5 req/min, teams/players/games only) is confirmed to exist and was what the bake-off's own 429s characterized; the live bake-off calls to `player_stats`/`season_stats`/`advanced_stats/passing` never hit a paywall error on the key Mac configured, so it's unconfirmed whether that key is actually on GOAT or whether those specific endpoints are free-tier-inclusive after all. Budgeting the published GOAT price is the conservative planning assumption. |
| **MySportsFeeds** | Team stats (current season) + lineups, per the 2026-09-03 gap test findings | **UNKNOWN — NEEDS A DIRECT QUOTE.** | MySportsFeeds' own pricing page confirms commercial/real-time tiers are **not publicly published** ("contact sales for exact commercial pricing" — confirmed via their own site, WebSearch 2026-09-03). The 14-day trial's real cost after conversion is unknown. **This is the single largest unresolved cost in this entire plan** — excluded from every "confirmed" total below, covered only by the general contingency reserve, which is not a substitute for a real quote. |
| **The Odds API** | Betting markets (moneyline/spread/totals) | **$59/mo** (100K-credit tier) production, **$30/mo** (20K-credit tier) staging | **CONFIRMED tier pricing** (published, current), against a **Mac-approved usage projection** (~40,944 credits/month production under the adaptive/game-aware cadence, PROGRESS.md 2026-08-10) — not a measured live bill, since Gate B (live odds capture) remains blocked on the missing credential per the Phase 7.0B decision record. Usage-variable in principle (credits scale with regions×markets×calls), but the approved cadence keeps it within one flat tier at current design. |
| **Weather** (WeatherAPI + OpenWeatherMap) | Existing/planned weather provider | **$0/mo** | **CONFIRMED.** PROGRESS.md's 2026-08-10 procurement review found Weather Worker cost "not driven by cadence at current volume" — free-tier capacity (WeatherAPI: 1M calls/mo) is sufficient. Real finding, not an assumption: reducing polling frequency would not save money here. |
| **News** (NewsAPI vs. GNews) | Existing/planned news provider | **UNRESOLVED — two confirmed published prices, no decision made.** NewsAPI Business: **$449/mo** (confirmed, required since NewsAPI's free tier is non-commercial by ToS). GNews Essential: **€49.99/mo** (≈$54 USD at a rough conversion — confirmed published price, FX approximate) for 1,000 req/day. | Mac explicitly held back the GNews swap pending a coverage/latency/reliability/licensing comparison (PROGRESS.md 2026-08-10) — **the currently-approved-if-launched-today default is NewsAPI Business ($449/mo)**, since no swap has been approved. This is modeled as the working default below; a GNews approval would cut this line by ~$395/mo. |
| **SportsDataIO** | Optional premium benchmark, **not a required launch dependency** (per this task's own framing and the provider bake-off/decision record) | **$10,000–$15,000/season** (≈$833–$1,250/month) | **CONFIRMED real quote** (Mac declined this purchase, Volume 4 §1.1's own documented trigger for the multi-source strategy). **Excluded from every base-scenario total below** — modeled only as an optional add-on scenario, since today's task explicitly frames it as optional. |

### Infrastructure

| Item | Cost | Status |
|---|---|---|
| **Railway** (4 environments — dev/staging/production/demo — ~13 services) | **ASSUMPTION: ~$150/mo at seed scale**, usage-variable beyond that (API Gateway/Orchestrator compute scales with traffic) | **UNKNOWN actual current bill** — no billing-dashboard access from this session (Railway MCP exposes deploys/logs/variables, not invoices). $150/mo is a rough placeholder against Railway's own published Pro-plan shape ($20/seat + usage), not a real number — flagged as needing a real billing-page check before this plan is trusted. |
| **Supabase** (4 separate projects — dev/staging/production/demo, per DEMO-1 architecture) | **ASSUMPTION: ~$50/mo** (production + staging on Pro at $25/project/mo each; dev/demo assumed free tier) | **UNKNOWN actual current tier** — published tiers (Free/$0, Pro/$25 per project, Team/$599 org-wide) are confirmed; which tier each of the 4 projects is actually on is not confirmed from this session. Usage-variable beyond bundled MAU/storage/egress as subscriber count grows. |
| **Redis** | **$0/mo today (confirmed: not yet provisioned — Phase 3D explicitly deferred it)**; **UNKNOWN future cost** | No quote obtained for a hosted option (Upstash, Railway's own Redis add-on) — needs one before Redis actually gets provisioned. Modeled as a small ASSUMED placeholder (~$15/mo) once live, clearly speculative. |
| **AI/model usage (Anthropic Claude API)** | See dedicated derivation below | Bottom-up ASSUMPTION, built from confirmed current Claude API pricing and the real (not originally-specified) committee architecture. |
| **Payment processing** | Stripe standard rate: **2.9% + $0.30/transaction** | **CONFIRMED public rate** (industry-standard, not invented) — but **no payment processor has actually been chosen** for MANSA; Stripe is the working assumption because no alternative has been discussed. |
| **Email/Telegram infrastructure** | Telegram Bot API: **$0** (confirmed — no per-message fee). Transactional email: **ASSUMPTION ~$0.01/user/mo** (a low-volume provider tier) | Telegram Companion is **not built yet** (schema-ready only, per Volume 5 §7's own "future-proofing, not built this milestone" note) — its real infra cost is $0 today and stays a planning placeholder until it ships. `Twilio` credentials are reserved in this project's isolation-guard forbidden-names list for **inbound SMS**, a distinct, also-unbuilt capability — not costed here since it's not confirmed as a launch feature. |
| **Founder labor** | 60–80 hrs/month, modeled at an **ASSUMED $75/hr shadow rate** (opportunity cost, not a real cash disbursement — Mac is not paying himself a salary at this stage) | **ASSUMPTION**, both the hours (HQ-specified range) and the rate (not specified anywhere — chosen as a reasonable technical-founder shadow rate for planning purposes only). Gross-margin figures below should be read with this in mind: they are not "cash left after paying Mac," they're "value created after crediting Mac's time at a nominal rate." |

### AI/model cost derivation (the part worth explaining, not just stating)

The original blueprint specified a **22-agent committee**; **only 12 agents
are actually implemented** as of the Phase 5 close (Volume 4 §1 v5.10,
Volume 1 §2.1 v3.1 — confirmed, not assumed). This matters enormously for
cost, and so does *how* the real architecture executes:

- The **shared committee analysis** (the ~12 implemented fan-out agents +
  Meta Agent review) runs **once per game, shared across every
  subscriber** — Volume 4 §3.1 v5.3 is explicit: Probability Modeling →
  EV → Risk Manager → consensus → Meta Agent review "each run exactly
  once per `(recommendation_id, candidate)` pair, shared across every
  user." **EV and Kelly-criterion math are plain deterministic code, not
  LLM calls at all** (Volume 4's own "never delegate to an LLM what
  application code can compute" rule) — narrowing the real token surface
  further than agent count alone would suggest.
- **Bankroll Coach** runs once per user who needs a personalized stake
  number — genuinely per-user, but only for tiers that get personalized
  staking.
- **Elite second-pass reconciliation** runs at most once per candidate
  per cycle, reused across every Elite subscriber — shared within the
  Elite tier, not per-Elite-user, but gated by entitlement to only
  trigger for candidates Elite users actually see.

**Practical consequence: the dominant AI cost is bounded by the NFL's own
schedule (≈16 games/week in season), not by subscriber count.** The
per-user cost is the much smaller personalization layer on top.

Working unit-economics (ASSUMPTION — no live token telemetry exists yet;
built from current confirmed Claude API pricing: Haiku 4.5 $1/$5 per
MTok in/out, Sonnet 5 $2/$10, Opus 5 $5/$25):

- Shared committee analysis: ~12 agent calls/game (9 at a cheap tier,
  ~4,000 in / 700 out tokens; 3 at a mid tier for the Decision/Advisory
  group + Meta Agent, same token shape) × ~16 games/week ≈ **$15/month
  flat**, rounded up with margin.
- Personalized Bankroll Coach compute (Pro + Elite only — Core is
  assumed not to get personalized staking, consistent with the
  entitlement matrix in Step 3): ~$0.26/paying-personalized-user/month.
- Elite second-pass reconciliation overhead: ~$0.50/Elite-user/month.
- **Conversational MANSA / Telegram usage is explicitly NOT modeled in
  the Base scenario** — it isn't live yet. It's a real future cost
  driver once shipped, flagged in "Unresolved decisions" below.

This is the single most important planning finding from Step 1: **AI
compute is not the dominant per-user cost driver it might appear to be
from a "22-agent committee" framing** — the architecture's own
shared-execution design already does most of the cost control work.

---

## STEP 2 — Economic Stress Test

**Prices (given):** Core $19.99, Pro $34.99, Elite $69.99.
**Base tier mix (given):** 50% Core / 40% Pro / 10% Elite → blended
**ARPU = $30.99/mo**.

**Model structure** (full detail in the scratch model computed for this
report — inputs are all labeled above; this is a spreadsheet-shaped
estimate, not a measurement):

- **Fixed costs** (confirmed + assumption lines from Step 1, excluding
  SportsDataIO and the unknown MySportsFeeds line): The Odds API $59 +
  Weather $0 + BALLDONTLIE $39.99 + NewsAPI $449 + Railway $150 +
  Supabase $50 + Redis $15 + AI shared-committee $15 = **$778/month**.
- **Variable costs** scale with subscriber count: AI personalization,
  a small sports-data usage-variable buffer, Railway/Supabase
  usage-variable growth, Stripe processing (2.9% + $0.30/user), and a
  nominal transactional-email cost.
- **Founder labor**: hours × $75/hr shadow rate.
- **Contingency**: 10% of (fixed + variable) in every scenario except
  the combined worst case (15%, given more is going wrong at once).

### Base scenario

| Users | MRR | Fixed | Variable | Founder Labor | Contingency | **Total OpEx** | **Gross Profit** | **Gross Margin** |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | $3,099 | $778 | $177 | $5,250 | $95 | **$6,300** | **-$3,201** | **-103.3%** |
| 250 | $7,748 | $778 | $442 | $5,250 | $122 | **$6,592** | **$1,155** | **14.9%** |
| 500 | $15,495 | $778 | $884 | $5,250 | $166 | **$7,079** | **$8,416** | **54.3%** |
| 1,000 | $30,990 | $778 | $1,769 | $5,250 | $255 | **$8,051** | **$22,939** | **74.0%** |
| 5,000 | $154,950 | $778 | $8,844 | $5,250 | $962 | **$15,834** | **$139,116** | **89.8%** |

(70 hrs/month founder labor assumed for this row; see the two dedicated
founder-labor rows below for the 60hr/80hr range.)

### Stress scenarios (each shown at all 5 user counts; founder labor
held at 70 hrs/month except the two dedicated labor rows)

**AI cost 3x** (personalization unit costs tripled):

| Users | MRR | Total OpEx | Gross Profit | Gross Margin |
|---:|---:|---:|---:|---:|
| 100 | $3,099 | $6,340 | -$3,241 | -104.6% |
| 250 | $7,748 | $6,691 | $1,056 | 13.6% |
| 500 | $15,495 | $7,277 | $8,218 | 53.0% |
| 1,000 | $30,990 | $8,447 | $22,543 | 72.7% |
| 5,000 | $154,950 | $17,814 | $137,136 | 88.5% |

**Sports-data cost 2x** (both the flat BALLDONTLIE/Odds-API tiers and
the usage-variable buffer doubled):

| Users | MRR | Total OpEx | Gross Profit | Gross Margin |
|---:|---:|---:|---:|---:|
| 100 | $3,099 | $6,403 | -$3,304 | -106.6% |
| 250 | $7,748 | $6,699 | $1,048 | 13.5% |
| 500 | $15,495 | $7,194 | $8,301 | 53.6% |
| 1,000 | $30,990 | $8,183 | $22,807 | 73.6% |
| 5,000 | $154,950 | $16,098 | $138,852 | 89.6% |

**Infrastructure 2x** (Railway/Supabase/Redis flat tiers and
usage-variable rate both doubled):

| Users | MRR | Total OpEx | Gross Profit | Gross Margin |
|---:|---:|---:|---:|---:|
| 100 | $3,099 | $6,554 | -$3,455 | -111.5% |
| 250 | $7,748 | $6,903 | $844 | 10.9% |
| 500 | $15,495 | $7,486 | $8,009 | 51.7% |
| 1,000 | $30,990 | $8,651 | $22,339 | 72.1% |
| 5,000 | $154,950 | $17,974 | $136,976 | 88.4% |

**10% power users at 10x personalized compute:**

| Users | MRR | Total OpEx | Gross Profit | Gross Margin |
|---:|---:|---:|---:|---:|
| 100 | $3,099 | $6,329 | -$3,230 | -104.2% |
| 250 | $7,748 | $6,664 | $1,084 | 14.0% |
| 500 | $15,495 | $7,222 | $8,273 | 53.4% |
| 1,000 | $30,990 | $8,337 | $22,653 | 73.1% |
| 5,000 | $154,950 | $17,264 | $137,686 | 88.9% |

**Bad tier mix (70% Core / 25% Pro / 5% Elite — ARPU drops to $26.24):**

| Users | MRR | Total OpEx | Gross Profit | Gross Margin |
|---:|---:|---:|---:|---:|
| 100 | $2,624 | $6,277 | -$3,653 | -139.2% |
| 250 | $6,560 | $6,533 | $27 | 0.4% |
| 500 | $13,120 | $6,960 | $6,160 | 46.9% |
| 1,000 | $26,240 | $7,815 | $18,425 | 70.2% |
| 5,000 | $131,200 | $14,653 | $116,547 | 88.8% |

**Founder labor 60 hrs/month:**

| Users | MRR | Total OpEx | Gross Profit | Gross Margin |
|---:|---:|---:|---:|---:|
| 100 | $3,099 | $5,550 | -$2,451 | -79.1% |
| 250 | $7,748 | $5,842 | $1,905 | 24.6% |
| 500 | $15,495 | $6,329 | $9,166 | 59.2% |
| 1,000 | $30,990 | $7,301 | $23,689 | 76.4% |
| 5,000 | $154,950 | $15,084 | $139,866 | 90.3% |

**Founder labor 80 hrs/month:**

| Users | MRR | Total OpEx | Gross Profit | Gross Margin |
|---:|---:|---:|---:|---:|
| 100 | $3,099 | $7,050 | -$3,951 | -127.5% |
| 250 | $7,748 | $7,342 | $405 | 5.2% |
| 500 | $15,495 | $7,829 | $7,666 | 49.5% |
| 1,000 | $30,990 | $8,801 | $22,189 | 71.6% |
| 5,000 | $154,950 | $16,584 | $138,366 | 89.3% |

**Combined worst case** (bad tier mix + AI 3x + sports-data 2x + infra
2x + 10% power users at 10x + founder labor 80hr + 15% contingency —
everything going wrong at once):

| Users | MRR | Total OpEx | Gross Profit | Gross Margin |
|---:|---:|---:|---:|---:|
| 100 | $2,624 | $7,544 | **-$4,920** | **-187.5%** |
| 250 | $6,560 | $8,048 | **-$1,488** | **-22.7%** |
| 500 | $13,120 | $8,888 | $4,232 | 32.3% |
| 1,000 | $26,240 | $10,567 | $15,673 | 59.7% |
| 5,000 | $131,200 | $23,998 | $107,202 | 81.7% |

### Break-even subscriber count

- **Base scenario: ~211 paying subscribers.**
- **Combined worst case: ~316 paying subscribers.**

Both are modest numbers relative to the 5,000-user ceiling this model
was asked to test — the real risk this model surfaces is not "can MANSA
ever be profitable," it's **"can MANSA survive the first ~200-300
subscribers,"** where every scenario (including Base) shows a loss at
100 users and only a thin margin at 250.

### Which costs actually matter most

In order of real leverage over the outcome:

1. **Founder labor is the largest single line in every early-stage
   scenario** — at 100-250 users, it dwarfs every provider cost
   combined ($5,250-$6,000/month vs. $778/month of confirmed+assumed
   fixed provider costs). This is a real, not-hypothetical finding:
   **the business's early economics are dominated by the value of
   Mac's own time, not by vendor bills.** Every stress scenario that
   moves fixed/variable provider costs (AI 3x, sports-data 2x, infra
   2x) changes gross margin by only a few percentage points; the two
   founder-labor rows (60hr vs. 80hr) move it by 15-50 points at low
   user counts.
2. **Tier mix matters more than any single provider cost.** The bad-mix
   scenario alone turns the 250-user break-even-adjacent row from
   +14.9% margin to +0.4% — a bigger swing than AI/sports-data/infra
   2-3x each produced individually.
3. **MySportsFeeds' unquoted cost is the largest *unknown* risk in this
   entire model.** None of the scenarios above include it. If its real
   commercial price turns out to be materially above the ~10% general
   contingency reserve's headroom (~$78-$1,600/month depending on
   scale), every margin figure above needs to be revised downward.
4. **Provider/infra cost multipliers (AI 3x, sports-data 2x, infra 2x)
   individually move gross margin by only 1-3 percentage points at
   every user count** — the shared-execution AI architecture and the
   already-confirmed cheap/free tiers for Weather and (at current
   volume) sports data mean these lines were never large enough to be
   the dominant risk, even tripled/doubled.
5. **The News provider decision (NewsAPI $449 vs. GNews ~$54) is a
   real, already-identified $395/month lever** sitting unresolved in
   the backlog — closing it is cheap to do and meaningfully improves
   the fixed-cost base at every user count below ~1,000.

### Major economic risks (do not present as certainties)

- **Founder-labor dependency**: the model above treats Mac's time as a
  cost, but if it's read as "cash profit" instead, the business looks
  far healthier than it would be if that labor ever needed to be
  replaced with paid hires at real market rates (likely well above the
  $75/hr shadow rate used here for anything beyond routine ops).
- **MySportsFeeds pricing is a live unknown** with no upper bound
  established — this plan cannot rule out it being large enough to
  materially change the picture at any user count.
- **Railway/Supabase actual current bills were not verified** from this
  session — both are ASSUMPTIONS. If real current spend is
  meaningfully higher, every fixed-cost line shifts.
- **The Odds API's approved projection is a *cadence design* number,
  not a measured bill** — Gate B (live capture) is still blocked on a
  missing credential per the Phase 7.0B decision record, so real
  production credit consumption has never actually been observed.
- **Payment processor is unchosen.** Stripe's standard rate was used
  as a placeholder; a real negotiated rate, a different processor, or
  MANSA's actual transaction pattern (annual billing, refunds, failed
  payments) could shift this materially.
- **Conversational MANSA/Telegram usage cost is entirely unmodeled**
  because it isn't built yet — launching it without first estimating
  its incremental AI/infra cost would be flying blind on exactly the
  kind of "personalized compute" this whole planning sequence exists
  to control.

---

## STEP 3 — Tier Entitlements (proposed, not implemented)

**Principle applied throughout:** cheaper tiers are not made artificially
weak — every tier gets the real product (real markets, real
recommendations, real track record). What differs is *depth, frequency,
personalization, compute intensity, history depth, alert richness, and
access to genuinely more expensive/advanced intelligence* — never a
crippled core experience designed to force an upgrade.

**No numeric limits are invented here** (message counts, refresh
intervals, token counts, parlay counts) — per HQ's explicit instruction,
those come later, informed by real usage data the metering architecture
in Step 4 will actually collect.

| Capability | Core | Pro | Elite | Cost rationale |
|---|---|---|---|---|
| **Command Center** | Included | Included | Included | Free to serve at any tier — it's a read of already-computed, already-cached data (Redis-fronted per Volume 2 §8); gating it would cripple the core product for no cost reason. |
| **Recommendations** | Included | Included | Included | Shared committee output (Step 1's own finding) — computed once per game regardless of subscriber count, so restricting it saves MANSA nothing. |
| **Moneyline / spread / totals** | Included | Included | Included | Same shared-computation reasoning — these are the three real markets the committee already evaluates for every game; there's no per-market marginal cost to gate. |
| **Track Record** | Included | Included | Included | A read of already-graded, already-stored history (Volume 3's grading pipeline) — near-zero marginal cost, and central to the product's own "checkable over believable" positioning (Volume 1). Gating it would undercut the trust pitch itself. |
| **Explainability** | Limited (basic) | Expanded (full) | Expanded (full) | The deterministic Explainability Engine (Volume 4 §8) is cheap to compute for everyone, but the *full* reasoning trace/evidence detail is a depth differentiator, not a cost one — Core gets the real "why," Pro/Elite get the complete one. |
| **Telegram (Conversational Companion)** | Limited | Expanded (full) | Expanded (full) | **Genuine future personalized-compute cost** once built (Step 1's flagged unmodeled cost) — each conversational turn is a real, per-user LLM call, unlike the shared committee analysis. Limiting Core's access directly limits MANSA's real incremental AI spend, not an artificial restriction. |
| **Conversational MANSA** | Limited (standard) | Expanded | Highest | Same reasoning as Telegram — this *is* the personalized-compute layer; depth of access should scale with what MANSA can afford to spend per user at each price point. |
| **Intelligent Parlays** | Limited | Expanded (full) | Expanded (full) | Not live yet (Public Web M2.2's own "Coming at Launch" framing) — once built, parlay correlation analysis is a genuinely heavier, more personalized compute operation than a single-leg recommendation, justifying tiering by depth/frequency once real unit costs are known. |
| **Time Machine** | Limited | Expanded (full) | Expanded (full) | Reconstruction reads from already-persisted snapshot tables (Volume 3) — cheap at any depth, so the limit here is about *how much history* is surfaced, a genuine value differentiator, not a cost-driven restriction. |
| **Market Intelligence** | Unavailable / basic | Limited/Expanded | Highest (full) | Ties to the still-unresolved Phase 7 anomaly-detection work (not built) and to whichever provider ultimately supplies richer market data (the still-open MySportsFeeds/API-SPORTS team-stats question) — genuinely tiered by real data-acquisition depth once that's resolved. |
| **Bet Timing** | Unavailable | Unavailable | Included (Elite-exclusive) | An explicitly future, not-yet-built capability (Volume 2 §4/Volume 4 §9.5) requiring continuous market monitoring — real, ongoing compute cost that only the highest tier's economics can absorb until proven at scale. |
| **Advanced Alerts** | Unavailable | Included | Highest | Alerting requires an active monitoring/push infrastructure cost (not yet built) distinct from a one-time recommendation read — a genuine incremental infra cost, reasonably gated above the entry tier. |
| **Freshness / compute class** | Standard | Enhanced | Highest priority | Directly maps to Step 4's `compute_classes` concept below — Elite users' requests can be routed to lower-latency/higher-priority execution paths (and, later, stronger models for personalized reasoning) without changing what the shared committee itself computes. |

---

## STEP 4 — Billing + Usage-Metering Architecture (design only — nothing
built)

### Core principle

```
SUBSCRIPTION PLAN
   -> ENTITLEMENTS            (what a tier unlocks, qualitatively)
   -> USAGE / COMPUTE BUDGETS (how much / how fast / at what compute class)
   -> MANSA SERVICES          (the actual capability execution)
```

Every service (Command Center API, Telegram bot, Recommendation Worker,
Conversational MANSA, Parlay builder) asks **one** central resolver a
**one** question — *"can this user do X, and at what compute class/
budget?"* — rather than each service independently hardcoding
`if tier == "elite"`. This is the single architectural rule everything
below exists to enforce.

### Entity model (conceptual — no migration written)

- **`subscription_plans`** — `id`, `name` (core/pro/elite), `price_cents`,
  `billing_interval`, `active`. The canonical list of sellable plans.
- **`plan_entitlements`** — `plan_id`, `capability_key` (one row per
  Step 3 capability), `level` (included/limited/expanded/highest/
  unavailable), `config` (jsonb — qualitative descriptors only, e.g.
  `{"depth": "full"}`, never a numeric cap at this stage). This is the
  literal, queryable form of Step 3's table.
- **`compute_classes`** — `id`, `name` (e.g. `shared_standard`,
  `personalized_standard`, `personalized_priority`), `model_tier`
  (maps to the existing `model_routing_rules` concept from Volume 3
  §8, extended with a tier dimension), `priority_weight`. Represents
  *how* a request gets executed, independent of *whether* it's allowed.
- **`model_routing_policies`** — extends the already-existing
  `model_routing_rules`/`prompt_registry` (Volume 3 §8, already live in
  the Orchestrator) with `compute_class_id`, so the same `task_type`
  can route to a cheaper or stronger model depending on which compute
  class the requesting entitlement resolved to — not a second routing
  system, an added dimension on the one that already exists.
- **`usage_limits`** — `plan_id`, `capability_key`, `limit_type`,
  `limit_value`, `period` (day/week/month). **Deliberately left
  unpopulated at this stage** — the schema exists so real numeric caps
  can be added later from actual observed usage (`usage_events` below),
  never invented ahead of time.
- **`usage_periods`** — `user_id`, `period_start`, `period_end`,
  `plan_id_snapshot` (the plan active *during* that period, since a
  mid-cycle upgrade/downgrade must not retroactively change how prior
  usage in the same period is judged) — the billing-cycle bookkeeping
  boundary every usage aggregate rolls up against.
- **`usage_events`** — the append-only ledger. One row per material
  external API/AI operation: `id`, `occurred_at`, `capability_key`,
  `compute_class_id`, `attribution_scope` (`'shared'` | `'personalized'`
  — see below), `user_id` (**nullable** for shared executions — a
  committee run attributable to no single user), `provider`, `model`,
  `estimated_cost`, `actual_cost` (nullable until reconciled, e.g.
  against a provider's own billing export), `execution_id` (correlates
  back to the actual recommendation/chat-turn/parlay-build that
  triggered it, for real Time-Machine-style auditability). This is the
  single place cost attribution ultimately comes from.
- **`personalized_compute_budgets`** — `scope` (`user` or `plan`),
  `scope_id`, `period`, `budget_cap`, `consumed` — the hard ceiling
  layer. A user or an entire tier can have a cap independent of
  `usage_limits` (which governs *feature access*; this governs *total
  dollars*), so a single runaway personalized-compute pattern can't
  silently blow through the economics this whole plan is built on.
- **Rate limits & abuse protection** — extends Volume 2 §9's already-
  specified AI abuse protections (prompt-injection filtering ahead of
  every model call, SMS-flooding-specific rate limits, and Orchestrator
  circuit breakers tripping on elapsed-time-or-call-count) with a
  fourth, cost-specific trigger: a circuit breaker on `usage_events`
  volume/cost rate per user/period, independent of the existing
  request-count-based limiter, since a single expensive personalized
  operation can matter more than many cheap ones.

### Request flow (how a real request actually traverses this)

1. A user (or the shared Recommendation Worker cycle, for
   `attribution_scope='shared'` work) requests a capability.
2. **`EntitlementResolver.resolve(user_id, capability_key)`** — the one
   central call every service uses, never a scattered tier check —
   reads `subscription_plans` + `plan_entitlements` and returns
   `{level, compute_class}`. If `level == 'unavailable'`, stop here with
   a clean, product-appropriate "not on your plan" response — never a
   silent degrade or a fabricated result.
3. If allowed, check `usage_limits` (once populated) against the
   current `usage_periods` aggregate, and `personalized_compute_budgets`
   against `consumed`. Both are advisory-then-hard: approaching a limit
   can degrade gracefully (e.g., route to a cheaper compute class)
   before it becomes a hard stop, per HQ's "graceful entitlement
   enforcement" instruction — never an abrupt mid-experience failure
   where a softer degrade is possible.
4. Execute via `model_routing_policies`, at the resolved `compute_class`.
5. Write one `usage_events` row — cost estimated at minimum, real cost
   backfilled where the provider/model exposes it — and update the
   relevant `usage_periods`/`personalized_compute_budgets` aggregates.
6. Internal reporting (cost-per-user, cost-per-tier, cost-per-capability)
   is a read-side rollup over `usage_events` — never a second,
   independently-maintained accounting system that could drift from the
   ledger itself.

### Shared vs. personalized: the load-bearing distinction

Step 1's own finding — that the committee analysis is computed once per
game and shared, while Bankroll Coach/Telegram/parlay-building are
genuinely per-user — is the architectural fact this whole design exists
to preserve correctly:

- A `'shared'` `usage_events` row has no `user_id`; its cost is real but
  belongs to the *game/candidate*, not any one subscriber. Cost-per-tier
  reporting must **amortize** shared costs across the subscribers who
  actually consumed that output in the period, not attribute the full
  cost to whichever user happened to trigger the cache-miss.
- A `'personalized'` row has a real `user_id` and its cost is
  attributable to exactly that user, directly.
- Getting this distinction wrong in either direction breaks the whole
  point of Step 2's economic model: over-attributing shared cost to
  individual users would make Core look artificially expensive to serve
  (and justify degrading it further than its real cost requires);
  under-attributing personalized cost would hide the real driver of
  per-user variable spend this plan identified as the thing to watch.

### What this deliberately does NOT do

- No `if tier == "elite"` anywhere — every service asks the resolver.
- No numeric usage caps populated yet — `usage_limits` exists as a
  destination for real data, not a place to park invented numbers.
- No Stripe/webhook/checkout code — entitlements and usage tracking are
  designed to be billing-provider-agnostic; `subscription_plans` doesn't
  assume Stripe specifically (a real integration would add a
  `stripe_price_id`-shaped mapping table, not embed Stripe concepts into
  the core entities above).
- No enforcement is live — this is the shape a future, separately-
  authorized implementation milestone would build against.

---

## Unresolved decisions (need Mac's input before implementation)

1. **MySportsFeeds real commercial pricing** — needs a direct quote;
   the single biggest unbounded cost risk in this plan.
2. **News provider**: NewsAPI Business ($449/mo, current default) vs.
   GNews Essential (~$54/mo) — a real, already-identified $395/month
   lever sitting unresolved since 2026-08-10.
3. **Payment processor** — Stripe assumed for planning only; never
   actually chosen.
4. **Real current Railway/Supabase bills** — both modeled as
   assumptions; should be checked against actual billing pages before
   this plan is trusted for real budgeting.
5. **Redis hosting choice and quote** — not yet provisioned; Upstash vs.
   Railway's own add-on vs. another option, no pricing obtained.
6. **Founder-labor shadow rate** — $75/hr was chosen for this exercise
   only; Mac may want a different number, or to model it differently
   entirely (e.g., excluded from gross margin, shown as a separate line).
7. **Conversational MANSA/Telegram real unit economics** — entirely
   unmodeled here because the feature isn't built; needs its own costing
   pass before launch, using real token/interaction assumptions once
   there's a prototype to measure against.
8. **Whether/when to pursue a MySportsFeeds plan (or API-SPORTS upgrade)
   at all**, pending the still-open 2026-09-09+ live-game validation
   gate recorded in the provider decision record.
9. **SportsDataIO's role, if any** — this plan treats it as fully
   optional per today's task framing; if a future gap can *only* be
   closed by SportsDataIO, its $833-$1,250/month confirmed cost would
   need to re-enter the base model, not just the optional scenario.
10. **Numeric usage limits** — deliberately not set anywhere in this
    package; the metering architecture (Step 4) needs to actually run
    and collect real `usage_events` data before any limit is proposed.

## Recommended next implementation milestone

**Do not build billing/metering yet.** The recommended next step is
narrower and cheaper than full implementation:

1. **Close the two cheap, already-identified unresolved decisions first**
   (News provider swap decision; a real MySportsFeeds quote) — both are
   phone calls/support tickets, not engineering work, and both directly
   change the numbers in this plan.
2. **Verify the two "unknown actual bill" assumptions** (Railway,
   Supabase) against real billing pages, so the fixed-cost base in Step
   2 stops resting on placeholders.
3. **Only after 1-2**, if Mac authorizes proceeding: build the
   `usage_events` ledger and `EntitlementResolver` skeleton *first*,
   wired to log real shared-vs-personalized executions from the
   already-running Recommendation Worker cycle, with **zero enforcement
   behavior** (log-only, no `usage_limits` populated, no blocking) — so
   real usage data exists before any numeric limit, compute budget, or
   billing integration is designed against invented assumptions instead
   of measured ones. This is the same "prove it with real data before
   committing" discipline this project has applied to every other
   quantitative threshold so far (the Elite second-pass variance
   threshold, the adaptive-weighting learning rate, the odds-cadence
   credit projection).

---

## Appendix: full scenario computation

The complete Python model used to produce every table above (all input
assumptions inline, labeled, and adjustable) is preserved for
inspection and re-runs as new real data (a MySportsFeeds quote, a
verified Railway bill, real `usage_events` telemetry) becomes available:
`/tmp` scratch location used during this session — not committed to the
repository, since it's a planning tool, not application code. Reproduce
by re-running the same input table against updated confirmed figures
whenever a Step 1 "ASSUMPTION"/"UNKNOWN" line gets a real answer.
