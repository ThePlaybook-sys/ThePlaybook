# MANSA Business + Entitlement Planning Package (2026-09-03, corrected)

**CORRECTION PASS (2026-09-03, same day):** HQ's original checkout for
MySportsFeeds ("NFL, Commercial, Live w/10-minute delay, CORE+STATS+
DETAILS") actually completed at **$246 CAD/month after trial** — the
first version of this document incorrectly treated that cost as
unknown/unquoted. This revision replaces every MySportsFeeds cost line
with the real figure, splits break-even into a CASH measure (excludes
founder labor) and an ECONOMIC measure (includes it, never blended with
cash), and adds an explicit News Provider Validation Gate rather than
picking between NewsAPI and GNews unilaterally. **Knowing the price does
NOT close the MySportsFeeds live-game data-quality gate** — play-by-play
and box-score completeness are still unvalidated pending the first
completed 2026 NFL regular-season game, per
`docs/ops/nfl-provider-decision-record.md`, which this document does not
alter. Step 3 (entitlements) and Step 4 (billing/metering architecture)
are carried forward unchanged — the corrected economics did not surface
a reason to revise either.

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
News), Mac's own authenticated MySportsFeeds checkout (real, confirmed
$246 CAD/month figure — see the corrected Step 1 table below),
`docs/blueprint/volume-1` (business model, pricing copy), `volume-2`
(Railway/Supabase/Redis/Twilio architecture, §8/§9), `volume-4` (agent
committee — real implemented count and execution model), the
`apps/frontend` pricing page (`Core $19.99` / `Pro $34.99` / `Elite
$69.99`, from Public Web M3), current published vendor pricing pages
(WebSearch, since direct vendor-site fetches are blocked by this
workspace's own egress policy — same constraint documented in both
provider diagnostic reports), and a WebSearch-sourced USD/CAD spot rate
(tradingeconomics.com, 2026-09-03: 1 USD ≈ 1.3831 CAD, i.e. 1 CAD ≈
0.7230 USD) used only to fold the confirmed CAD figure into consolidated
USD totals — the CAD figure itself is the real number, never the
conversion.

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
| **MySportsFeeds** | Team stats (current season) + lineups, per the 2026-09-03 gap test findings | **$246 CAD/month** (NFL, Commercial, Live w/10-minute delay, CORE+STATS+DETAILS — the working cost-direction hypothesis from `nfl-provider-decision-record.md`) ≈ **$178 USD/month** at the labeled approximate FX rate above | **CONFIRMED — Mac's actual authenticated checkout**, no longer an unknown. For contrast (not modeled, not chosen): Near-Realtime CORE+STATS+DETAILS on the same checkout was **$674 CAD/month** (≈$487 USD) — **2.7x the 10-minute-delay tier**, which is exactly the freshness premium the still-open live-game validation gate exists to justify or reject. **Pricing being known does not validate data quality**: play-by-play and box-score completeness/granularity remain UNKNOWN pending the first completed 2026 NFL regular-season game (gate status unchanged by this document — see `docs/ops/nfl-provider-decision-record.md`). Included in every fixed-cost total below at the $246 CAD/≈$178 USD figure. |
| **The Odds API** | Betting markets (moneyline/spread/totals) | **$59/mo** (100K-credit tier) production, **$30/mo** (20K-credit tier) staging | **CONFIRMED tier pricing** (published, current), against a **Mac-approved usage projection** (~40,944 credits/month production under the adaptive/game-aware cadence, PROGRESS.md 2026-08-10) — not a measured live bill, since Gate B (live odds capture) remains blocked on the missing credential per the Phase 7.0B decision record. Usage-variable in principle (credits scale with regions×markets×calls), but the approved cadence keeps it within one flat tier at current design. |
| **Weather** (WeatherAPI + OpenWeatherMap) | Existing/planned weather provider | **$0/mo** | **CONFIRMED.** PROGRESS.md's 2026-08-10 procurement review found Weather Worker cost "not driven by cadence at current volume" — free-tier capacity (WeatherAPI: 1M calls/mo) is sufficient. Real finding, not an assumption: reducing polling frequency would not save money here. |
| **News** (NewsAPI vs. GNews) | Existing/planned news provider | **UNRESOLVED — two confirmed published prices, no decision made, NOT auto-selected in this pass either.** NewsAPI Business: **$449/mo** (confirmed, required since NewsAPI's free tier is non-commercial by ToS). GNews Essential: **€49.99/mo** (≈$54 USD at a rough conversion — confirmed published price, FX approximate) for 1,000 req/day. | Mac explicitly held back the GNews swap pending a coverage/latency/reliability/licensing comparison (PROGRESS.md 2026-08-10). Per HQ's explicit instruction this pass, **neither provider is picked here** — both are modeled side-by-side in Step 2 as named scenarios, and a dedicated **News Provider Validation Gate** (new section below Step 2) proposes how to actually decide. NewsAPI remains the current-default assumption only because it's the one already live, not because it was chosen as better. |
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

## STEP 2 — Economic Stress Test (rerun with MySportsFeeds included)

**Prices (given):** Core $19.99, Pro $34.99, Elite $69.99.
**Base tier mix (given):** 50% Core / 40% Pro / 10% Elite → blended
**ARPU = $30.99/mo**.

**Model structure** (full detail in the scratch model computed for this
report — inputs are all labeled above; this is a spreadsheet-shaped
estimate, not a measurement):

- **Fixed costs** now include MySportsFeeds at $246 CAD/mo (≈$178 USD).
  With **NewsAPI** ($449/mo): The Odds API $59 + Weather $0 +
  MySportsFeeds ≈$178 + BALLDONTLIE $39.99 + Railway $150 + Supabase $50
  + Redis $15 + AI shared-committee $15 + NewsAPI $449 = **≈$956/month**.
  With **GNews** (≈$54/mo) instead: **≈$561/month** — a **$395/month
  delta**, unchanged from the first pass, since only the News line
  moves.
- **Variable costs** scale with subscriber count: AI personalization, a
  small sports-data usage-variable buffer, Railway/Supabase
  usage-variable growth, Stripe processing (2.9% + $0.30/user), and a
  nominal transactional-email cost. Unchanged from the first pass.
- **Founder labor**: hours × $75/hr shadow rate — **now reported
  separately as its own line, never folded into a single "OpEx"
  number**, per HQ's explicit instruction not to mix cash and economic
  concepts.
- **Contingency**: 10% of (fixed + variable) in every scenario except
  the combined worst case (15%).
- **Cash OpEx** = fixed + variable + contingency. **Economic OpEx** =
  Cash OpEx + founder labor. Every table below reports **both margins
  side by side** — they answer two different questions and are never
  blended into one figure.

### Base scenario — NewsAPI (current default)

| Users | MRR | Fixed | Variable | Conting. | **Cash OpEx** | **Cash Margin** | Founder Labor | **Economic OpEx** | **Economic Margin** |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | $3,099 | $956 | $177 | $113 | **$1,246** | **59.8%** | $5,250 | **$6,496** | **-109.6%** |
| 250 | $7,748 | $956 | $442 | $140 | **$1,538** | **80.2%** | $5,250 | **$6,788** | **12.4%** |
| 500 | $15,495 | $956 | $884 | $184 | **$2,024** | **86.9%** | $5,250 | **$7,274** | **53.1%** |
| 1,000 | $30,990 | $956 | $1,769 | $272 | **$2,997** | **90.3%** | $5,250 | **$8,247** | **73.4%** |
| 5,000 | $154,950 | $956 | $8,844 | $980 | **$10,779** | **93.0%** | $5,250 | **$16,029** | **89.7%** |

### Base scenario — GNews (challenger, not selected)

| Users | MRR | Fixed | Variable | Conting. | **Cash OpEx** | **Cash Margin** | Founder Labor | **Economic OpEx** | **Economic Margin** |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | $3,099 | $561 | $177 | $74 | **$812** | **73.8%** | $5,250 | **$6,062** | **-95.6%** |
| 250 | $7,748 | $561 | $442 | $100 | **$1,104** | **85.8%** | $5,250 | **$6,354** | **18.0%** |
| 500 | $15,495 | $561 | $884 | $145 | **$1,590** | **89.7%** | $5,250 | **$6,840** | **55.9%** |
| 1,000 | $30,990 | $561 | $1,769 | $233 | **$2,563** | **91.7%** | $5,250 | **$7,813** | **74.8%** |
| 5,000 | $154,950 | $561 | $8,844 | $940 | **$10,345** | **93.3%** | $5,250 | **$15,595** | **89.9%** |

(70 hrs/month founder labor for both tables above; see the two
dedicated founder-labor rows below for the 60hr/80hr range. All
remaining stress scenarios below use NewsAPI as the pessimistic/current
default, except where a scenario is explicitly about the News choice
itself.)

### Stress scenarios (all 5 user counts; NewsAPI, founder labor 70
hrs/month except the two dedicated labor rows; MySportsFeeds included in
every fixed-cost figure)

**AI cost 3x:**

| Users | MRR | Cash OpEx | Cash Margin | Economic OpEx | Economic Margin |
|---:|---:|---:|---:|---:|---:|
| 100 | $3,099 | $1,286 | 58.5% | $6,536 | -110.9% |
| 250 | $7,748 | $1,637 | 78.9% | $6,887 | 11.1% |
| 500 | $15,495 | $2,222 | 85.7% | $7,472 | 51.8% |
| 1,000 | $30,990 | $3,393 | 89.1% | $8,643 | 72.1% |
| 5,000 | $154,950 | $12,759 | 91.8% | $18,009 | 88.4% |

**Sports-data cost 2x** (Odds API + BALLDONTLIE + MySportsFeeds flat
tiers all doubled, plus the usage-variable buffer):

| Users | MRR | Cash OpEx | Cash Margin | Economic OpEx | Economic Margin |
|---:|---:|---:|---:|---:|---:|
| 100 | $3,099 | $1,526 | 50.8% | $6,776 | -118.7% |
| 250 | $7,748 | $1,823 | 76.5% | $7,073 | 8.7% |
| 500 | $15,495 | $2,318 | 85.0% | $7,568 | 51.2% |
| 1,000 | $30,990 | $3,307 | 89.3% | $8,557 | 72.4% |
| 5,000 | $154,950 | $11,221 | 92.8% | $16,471 | 89.4% |

**Infrastructure 2x** (Railway/Supabase/Redis flat tiers and
usage-variable rate both doubled):

| Users | MRR | Cash OpEx | Cash Margin | Economic OpEx | Economic Margin |
|---:|---:|---:|---:|---:|---:|
| 100 | $3,099 | $1,499 | 51.6% | $6,749 | -117.8% |
| 250 | $7,748 | $1,849 | 76.1% | $7,099 | 8.4% |
| 500 | $15,495 | $2,432 | 84.3% | $7,682 | 50.4% |
| 1,000 | $30,990 | $3,597 | 88.4% | $8,847 | 71.5% |
| 5,000 | $154,950 | $12,919 | 91.7% | $18,169 | 88.3% |

**10% power users at 10x personalized compute:**

| Users | MRR | Cash OpEx | Cash Margin | Economic OpEx | Economic Margin |
|---:|---:|---:|---:|---:|---:|
| 100 | $3,099 | $1,275 | 58.9% | $6,525 | -110.5% |
| 250 | $7,748 | $1,609 | 79.2% | $6,859 | 11.5% |
| 500 | $15,495 | $2,167 | 86.0% | $7,417 | 52.1% |
| 1,000 | $30,990 | $3,283 | 89.4% | $8,533 | 72.5% |
| 5,000 | $154,950 | $12,209 | 92.1% | $17,459 | 88.7% |

**Bad tier mix (70% Core / 25% Pro / 5% Elite — ARPU drops to $26.24):**

| Users | MRR | Cash OpEx | Cash Margin | Economic OpEx | Economic Margin |
|---:|---:|---:|---:|---:|---:|
| 100 | $2,624 | $1,222 | 53.4% | $6,472 | -146.7% |
| 250 | $6,560 | $1,479 | 77.5% | $6,729 | -2.6% |
| 500 | $13,120 | $1,906 | 85.5% | $7,156 | 45.5% |
| 1,000 | $26,240 | $2,761 | 89.5% | $8,011 | 69.5% |
| 5,000 | $131,200 | $9,598 | 92.7% | $14,848 | 88.7% |

**Founder labor 60 hrs/month:**

| Users | MRR | Cash OpEx | Cash Margin | Economic OpEx | Economic Margin |
|---:|---:|---:|---:|---:|---:|
| 100 | $3,099 | $1,246 | 59.8% | $5,746 | -85.4% |
| 250 | $7,748 | $1,538 | 80.2% | $6,038 | 22.1% |
| 500 | $15,495 | $2,024 | 86.9% | $6,524 | 57.9% |
| 1,000 | $30,990 | $2,997 | 90.3% | $7,497 | 75.8% |
| 5,000 | $154,950 | $10,779 | 93.0% | $15,279 | 90.1% |

**Founder labor 80 hrs/month:**

| Users | MRR | Cash OpEx | Cash Margin | Economic OpEx | Economic Margin |
|---:|---:|---:|---:|---:|---:|
| 100 | $3,099 | $1,246 | 59.8% | $7,246 | -133.8% |
| 250 | $7,748 | $1,538 | 80.2% | $7,538 | 2.7% |
| 500 | $15,495 | $2,024 | 86.9% | $8,024 | 48.2% |
| 1,000 | $30,990 | $2,997 | 90.3% | $8,997 | 71.0% |
| 5,000 | $154,950 | $10,779 | 93.0% | $16,779 | 89.2% |

**Combined worst case** (bad tier mix + AI 3x + sports-data 2x + infra
2x + 10% power users at 10x + founder labor 80hr + 15% contingency,
NewsAPI — everything going wrong at once):

| Users | MRR | Cash OpEx | Cash Margin | Economic OpEx | Economic Margin |
|---:|---:|---:|---:|---:|---:|
| 100 | $2,624 | $1,927 | 26.6% | **$7,927** | **-202.1%** |
| 250 | $6,560 | $2,431 | 62.9% | **$8,431** | **-28.5%** |
| 500 | $13,120 | $3,270 | 75.1% | $9,270 | 29.3% |
| 1,000 | $26,240 | $4,949 | 81.1% | $10,949 | 58.3% |
| 5,000 | $131,200 | $18,381 | 86.0% | $24,381 | 81.4% |

### Break-even subscriber count — reported as TWO separate measures

**A. CASH break-even** (fixed + variable + contingency only, founder
labor excluded — "how many subscribers before MANSA's actual cash
outlays are covered"):

- **Base, NewsAPI: 37 paying subscribers** (MRR $1,147 vs. Cash OpEx
  $1,123).
- **Base, GNews: 22 paying subscribers** (MRR $682 vs. Cash OpEx $660).
- **Combined worst case: 70 paying subscribers** (MRR $1,837 vs. Cash
  OpEx $1,826).

**B. ECONOMIC break-even** (fixed + variable + contingency + founder
labor at the $75/hr shadow rate — "how many subscribers before MANSA
covers its cash costs AND the economic value of Mac's own time"):

- **Base, NewsAPI: 217 paying subscribers** (MRR $6,725 vs. Economic
  OpEx $6,724).
- **Base, GNews: 203 paying subscribers** (MRR $6,291 vs. Economic OpEx
  $6,262).
- **Combined worst case: 332 paying subscribers** (MRR $8,712 vs.
  Economic OpEx $8,706).

**These are not interchangeable and should never be quoted without
saying which one is meant.** Cash break-even (22-70 subscribers) is the
real survival floor — the point below which MANSA is literally losing
cash, not just "not paying Mac." Economic break-even (203-332
subscribers) is the point at which the business would be sound even if
Mac's time carried a real market cost. The gap between them — roughly
180-260 subscribers — **is the size of the founder-labor subsidy this
business currently runs on.**

### Which costs actually matter most (rerun with MySportsFeeds included)

In order of real leverage over the outcome:

1. **Founder labor is still the largest single line at low subscriber
   counts**, and now the single clearest way to see this is the cash-
   vs-economic break-even gap itself: cash break-even is ~22-70
   subscribers; economic break-even is ~203-332. That ~180-260-
   subscriber gap **is** the founder-labor effect, made concrete instead
   of implied by a blended margin number the way the first pass showed
   it.
2. **MySportsFeeds is now a confirmed, material fixed cost — ≈$178
   USD/month — not the open-ended unknown the first pass flagged.**
   Resolving it didn't blow up the model (it moves cash break-even by
   roughly 6-9 subscribers relative to a hypothetical $0 line), but it
   is now the second-largest single confirmed fixed-cost line after
   News, and it is **denominated in CAD** — a real, ongoing FX exposure
   this plan did not previously carry. **This is a new, genuine risk
   this pass surfaces**: if CAD strengthens against USD, this line gets
   more expensive in USD terms with no product change to show for it.
3. **The News provider decision is now the single largest remaining
   discretionary lever in the whole model — $395/month, larger than
   MySportsFeeds itself.** GNews cuts cash break-even from 37 to 22
   subscribers (a >40% reduction) and economic break-even from 217 to
   203. See the new News Provider Validation Gate below — this is cheap
   to resolve and meaningfully changes both break-even numbers.
4. **Tier mix still matters more than any individual provider cost
   multiplier.** The bad-mix scenario alone turns the 250-user cash
   margin from 80.2% to 77.5% and the economic margin from +12.4% to
   -2.6% — a bigger swing at that user count than AI/sports-data/infra
   2-3x individually produce.
5. **Provider/infra cost multipliers (AI 3x, sports-data 2x, infra 2x)
   individually still move margin by only a few percentage points** at
   every user count — unchanged finding from the first pass; the
   shared-execution AI architecture and already-confirmed cheap/free
   Weather tier keep these from being the dominant risk even
   tripled/doubled.

### Major economic risks (do not present as certainties)

- **Founder-labor dependency**: unchanged from the first pass — the
  cash/economic split above makes this concrete rather than
  hypothetical. If that labor is ever priced at a real market rate
  (likely well above the $75/hr shadow rate), the true economic
  break-even could be materially higher than 203-332.
- **MySportsFeeds is now a confirmed cost, but carries a new FX risk**
  the first pass didn't have — a CAD-denominated recurring line whose
  USD cost moves with the exchange rate, not with anything MANSA
  controls.
- **MySportsFeeds' data-quality gate is still open** — this document
  only resolves *price*; play-by-play/box-score completeness remain
  unvalidated pending the first completed 2026 game
  (`nfl-provider-decision-record.md`, unchanged by this pass). A poor
  validation result could mean the $246 CAD/mo spend doesn't actually
  close the gaps it was budgeted for, independent of cost.
- **News provider choice remains unresolved** and is now the largest
  discretionary lever in the model (larger than MySportsFeeds) — see
  the new validation gate below.
- **Railway/Supabase actual current bills were not verified** from this
  session — both are ASSUMPTIONS. If real current spend is meaningfully
  higher, every fixed-cost line shifts.
- **The Odds API's approved projection is a *cadence design* number,
  not a measured bill** — Gate B (live capture) is still blocked on a
  missing credential per the Phase 7.0B decision record, so real
  production credit consumption has never actually been observed.
- **Payment processor is unchosen.** Stripe's standard rate was used as
  a placeholder; a real negotiated rate, a different processor, or
  MANSA's actual transaction pattern (annual billing, refunds, failed
  payments) could shift this materially.
- **Conversational MANSA/Telegram usage cost is entirely unmodeled**
  because it isn't built yet — launching it without first estimating
  its incremental AI/infra cost would be flying blind on exactly the
  kind of "personalized compute" this whole planning sequence exists to
  control.

---

## News Provider Validation Gate (RUN 2026-09-03 — see result below)

**UPDATE (2026-09-03, same day): this gate has been run.** Full report:
`docs/ops/news-provider-validation-gnews-2026-09-03.md`, decision
tracked going forward in `docs/ops/news-provider-decision-record.md`
(same living-document pattern as the NFL provider decision record).
GNews Essential was already active with `GNEWS_API_KEY` configured when
this ran — a controlled, 18-call (2 runs) DEV-only diagnostic against
the 11 criteria below.

**Result: NOT selected, and not rejected — two concrete blockers
identified, neither of which is "it's cheaper so it must be worse."**
Content quality was genuinely strong on 4 of 6 named categories
(injuries, trades, suspensions, roster/depth-chart news all tested
GREEN, with depth-chart content arguably better than what NewsAPI's own
current query pattern would surface). But: **(1)** every single response
carried a real-time-delay notice ("Free plan has a 12-hour delay...
upgrade") despite the subscription being paid, and the empirically
freshest article for high-volume queries was 17-34 hours old — real-
time entitlement on Essential specifically is unconfirmed; **(2)** GNews
Essential's 1,000 req/day quota is roughly 3x short of MANSA's own News
Worker's actual ~3,072 calls/day typical in-season volume (flat
15-minute cadence, no ramp, up to 32 teams) — a hard capacity ceiling
independent of price. **Recommendation: ask GNews support directly
whether Essential includes real-time delivery before spending a 10-day
trial on it** — if it doesn't, a higher (likely costlier) tier is the
real comparison point against NewsAPI, not Essential's ≈$54/mo. The
$395/month delta this plan's economics are built around may not be the
real delta once that's answered. See the decision record for the full
"what's needed before this closes" list. **News provider selection
remains UNRESOLVED in this business plan** — NewsAPI Business stays the
modeled default for the same reason it already was: it's the one that's
live, not because it's been confirmed better.

### Original gate design (run as specified below)

**Do not select NewsAPI or GNews from this document.** $395/month is a
real, material swing in both break-even measures above, but price alone
is not a sufficient basis to choose — the first bake-off's own lesson
(a cheaper/better-looking provider can be gated, restricted, or
qualitatively worse in ways a price comparison never surfaces) applies
here too.

**Proposed gate, mirroring the same diagnostic discipline as the NFL
provider bake-offs above** — small, controlled, DEV-only, no
subscription committed until the comparison is in hand:

Compare GNews vs. NewsAPI specifically for **NFL-relevant** content
(not general news volume) across:

1. **Breaking injury news** — speed and specificity (a real designation
   change vs. vague "questionable" boilerplate).
2. **Trades** — coverage completeness and how fast a trade appears
   after being reported.
3. **Suspensions** — same two dimensions.
4. **Roster/lineup news** — depth-chart-relevant coverage, not just
   headline-level roster moves.
5. **Coaching news** — hires/fires/scheme changes that can matter to
   game-level analysis.
6. **Latency** — real wall-clock time from event to article availability
   via each API.
7. **Source coverage** — which outlets each provider actually indexes
   for NFL content (beat reporters vs. wire-only).
8. **Duplicates/noise** — how much of each provider's NFL feed is
   redundant re-reporting of the same story vs. genuinely new
   information.
9. **Reliability** — uptime/error-rate behavior observed during the
   test window.
10. **Commercial rights** — confirm GNews Essential's license actually
    covers MANSA's intended commercial use the same way NewsAPI
    Business's does (NewsAPI's free tier's non-commercial restriction
    was already the reason Business is the current default — GNews's
    equivalent terms haven't been read closely yet).
11. **API ergonomics** — request shape, rate limits, pagination,
    response schema quality, ease of adapter integration.

**Recommendation: yes, run the GNews 10-day trial** before making a
production choice. It is the only way to get real signal on items 1-9
and 11 above — none of them are resolvable from a pricing page — and a
10-day trial is cheap and time-boxed relative to a $395/month decision
that will recur for the life of the product. NewsAPI Business should be
left running unchanged during the trial (no reason to interrupt a live
default while evaluating a challenger). This gate should follow the
same "temporary probe, then report, no code left behind" discipline as
the NFL provider bake-offs, adapted for a REST news API rather than a
sports-data API — not run as part of this planning pass, since HQ's
explicit scope for today was planning only.

---

## STEP 3 — Tier Entitlements (proposed, not implemented)

**Carried forward unchanged from the first pass.** The corrected
economics (MySportsFeeds now a confirmed, moderate fixed cost rather
than an open-ended unknown; the News decision now the largest
discretionary lever) did not surface a reason to revise the matrix
below — MySportsFeeds funds the same **Market Intelligence** row's
"still-open provider question" rationale already noted there, now with
a real price attached rather than an unknown one, which strengthens
that row's existing reasoning rather than changing it.

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

1. **News provider**: NewsAPI Business ($449/mo, current default) vs.
   GNews Essential (~$54/mo) — still the **largest discretionary cost
   lever in the model** ($395/month, larger than MySportsFeeds), and
   the News Provider Validation Gate has now been run
   (`docs/ops/news-provider-validation-gnews-2026-09-03.md`,
   2026-09-03). Result: GNews's content quality tested well, but two
   concrete blockers (unconfirmed real-time entitlement on the
   Essential tier; a ~3x request-volume shortfall against MANSA's own
   News Worker cadence) mean the $395/mo delta modeled throughout this
   document is not yet a decision Mac can safely act on. Still
   unresolved — see `docs/ops/news-provider-decision-record.md` for
   what needs to happen before it closes.
2. **MySportsFeeds live-game data-quality validation** — **pricing is
   now resolved** ($246 CAD/mo, confirmed), but the gate covering
   play-by-play/box-score completeness, correction semantics, and
   whether Near-Realtime is actually needed remains **🔴 BLOCKED**
   pending the first completed 2026 NFL regular-season game, per
   `docs/ops/nfl-provider-decision-record.md` (unchanged by this
   document). A poor validation result would mean the confirmed $246
   CAD/mo doesn't close the gaps it's budgeted for, independent of cost.
3. **Payment processor** — Stripe assumed for planning only; never
   actually chosen.
4. **Real current Railway/Supabase bills** — both modeled as
   assumptions; should be checked against actual billing pages before
   this plan is trusted for real budgeting.
5. **Redis hosting choice and quote** — not yet provisioned; Upstash vs.
   Railway's own add-on vs. another option, no pricing obtained.
6. **Founder-labor shadow rate** — $75/hr was chosen for this exercise
   only; Mac may want a different number. The cash-vs-economic
   break-even split in Step 2 now makes exactly how much this choice
   matters explicit (it's the entire ~180-260-subscriber gap between
   the two break-even measures) — a different rate would move the
   economic break-even number directly, without touching the cash one.
7. **Conversational MANSA/Telegram real unit economics** — entirely
   unmodeled here because the feature isn't built; needs its own costing
   pass before launch, using real token/interaction assumptions once
   there's a prototype to measure against.
8. **MySportsFeeds CAD/USD FX exposure** — new this pass. The plan now
   carries a real, ongoing currency risk on one recurring line; whether
   to hedge, pay in CAD directly, or simply monitor is Mac's call, not
   resolved here.
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

1. **Ask GNews support directly whether Essential includes real-time
   delivery, and confirm its real sustained rate limit** — the two
   concrete blockers the 2026-09-03 News Provider Validation Gate
   surfaced. This is cheaper and faster than a 10-day trial and
   determines which GNews tier (Essential's ≈$54/mo, or a costlier
   real-time tier) is actually the right comparison point against
   NewsAPI's $449/mo before any trial is spent.
2. **Verify the two "unknown actual bill" assumptions** (Railway,
   Supabase) against real billing pages, so the fixed-cost base in Step
   2 stops resting on placeholders.
3. **Do not act on the MySportsFeeds cost hypothesis** (i.e. don't
   change the subscription tier, even though the 10-minute-delay price
   is now confirmed) **until the live-game data-quality gate clears** —
   this document only removed the pricing unknown, not the quality
   unknown; see `docs/ops/nfl-provider-decision-record.md`.
4. **Only after 1-3**, if Mac authorizes proceeding: build the
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
assumptions inline, labeled, and adjustable — including the CAD-native
MySportsFeeds figure, the labeled FX conversion, the cash/economic
break-even split, and the two named News scenarios) is preserved for
inspection and re-runs as new real data (a News Provider Validation Gate
result, a verified Railway/Supabase bill, real `usage_events`
telemetry, or a MySportsFeeds live-game validation outcome) becomes
available: `/tmp` scratch location used during this session (`model.py`
= first pass, `model_v2.py` = this correction pass) — not committed to
the repository, since it's a planning tool, not application code.
Reproduce by re-running the same input table against updated confirmed
figures whenever a Step 1 "ASSUMPTION"/"UNKNOWN" line gets a real
answer.
