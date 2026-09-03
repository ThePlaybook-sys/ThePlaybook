# MANSA News Provider Validation — GNews Essential (2026-09-03)

**Diagnostic only. No provider migration, no subscription change, no
News Worker/adapter rewrite. DEV only.** GNews Essential (€49.99/mo) is
already active and `GNEWS_API_KEY` was already configured on
`sports-intel-layer`/dev when this task started. This report evaluates
whether it can credibly replace NewsAPI Business ($449/mo) as MANSA's
production NFL news provider — it does not decide that question.

**Answer up front: not yet, and not on price alone.** GNews Essential
is genuinely strong on query precision for structured categories
(injuries, roster/depth-chart news) and offers richer structured
metadata than MANSA's current NewsAPI adapter uses. But two real
problems surfaced — an apparent freshness/delay gap despite being on a
paid, real-time-eligible plan, and a stricter-than-documented burst rate
limit — that need a direct answer from GNews before a production
decision is defensible. See Recommendation at the end.

---

## Method

Same "temporary probe, dev-only startup hook + `logger.warning`
retrieval, then full revert" discipline as both prior NFL provider
bake-offs (`docs/ops/nfl-provider-bakeoff-2026-09-03.md`,
`docs/ops/nfl-provider-gap-test-mysportsfeeds-2026-09-03.md`) — this
workspace's own egress policy blocks direct HTTPS to `gnews.io`/
`docs.gnews.io` and to this service's own public Railway domain, so
results were retrieved via Railway's own deploy logs from a temporary,
dev-only, `RUN_GNEWS_VALIDATION=1`-gated startup hook
(`app.diagnostics.gnews_validation`, since reverted).

Endpoint shape (base URL, `q`/`lang`/`country`/`max`/`sortby`/`page`/
`expand` params, `apikey` auth, the `articles: [{id, title, description,
content, url, image, publishedAt, lang, source: {id, name, url,
country}}]` response shape) was confirmed from the official
`gnews-io/gnews-io-js` TypeScript client's README plus multiple
independent WebSearch-indexed sources for the Essential plan's real
limits (1,000 req/day, 10 req/sec, 25 articles/request max, `expand=
content` as a documented paid-only full-content parameter) — not from
the unrelated `gnews` PyPI package (a Google-News RSS scraper by a
different, unaffiliated author, deliberately not used as a schema
source despite the name collision).

**Two runs, 18 total calls (9 attempted per run).** Run 1 (1.5s spacing
between calls) hit 4 of 9 calls rate-limited (`429`, "too many requests
... in a short period of time") despite being comfortably inside the
documented 10 req/sec Essential limit — a real finding about actual vs.
documented burst behavior, not a probe bug. Run 2 (5s spacing) got a
clean 9/9 `200` sample. All figures below are drawn from Run 2's clean
data; Run 1's rate-limit behavior is itself reported as a finding.

Queries, mirroring `NewsAPINewsAdapter.fetch_news`'s own query
construction (`f"{team} NFL"`) for direct comparability, plus one query
per named evaluation category:

| Category | Query |
|---|---|
| Team-scoped (comparability) | `"Kansas City Chiefs NFL"`, `"Philadelphia Eagles NFL"` |
| Breaking injury news | `"NFL injury report"` |
| Trades | `"NFL trade"` |
| Suspensions | `"NFL suspension"` |
| Roster/lineup/depth-chart news | `"NFL depth chart"` |
| Coaching news | `"NFL head coach"` |
| Full-content test | `"Kansas City Chiefs NFL"` with `expand=content` |
| Pagination behavior | `"NFL"` with `page=2` |

---

## Findings by objective

### 1. Breaking injury news — GREEN (content quality), YELLOW (freshness)

The `"NFL injury report"` sample returned six real, specific injury
reports: Vikings QB JJ McCarthy (ankle, multi-week), Chargers C Tyler
Biadasz (ACL, indefinite), Vikings LB Jamal Adams (season-ending knee),
plus Tyreek Hill's ongoing recovery, a Jaguars O-line injury-driven
trade, and a rookie-focused fantasy injury roundup — each names a real
player, a real injury, and a real status. This is a genuinely better
per-article signal than MySportsFeeds' own injury data (2 of 3 sampled
descriptions were literally the string `"unknown"`, per the 2026-09-03
NFL gap test) or SportsDataIO's trial data (that adapter's own
docstring documents injury descriptions as "100% Scrambled").

**But freshness is a real concern.** The most recent article in this
category was ~34 hours old at capture time even sorted by
`publishedAt` descending — not "breaking" in the sub-hour sense HQ's
own criterion implies. See the cross-cutting freshness finding below;
this isn't unique to injuries, but injury news is the category where a
day-plus lag matters most for MANSA's product.

### 2. Trades — GREEN

`"NFL trade"` returned genuinely on-topic content: a Joey Porter Jr.
contract/trade-request storyline (two independent, corroborating
articles from different outlets), a Patriots roster-churn piece
detailing specific trade acquisitions (players, positions, the
acquiring mechanism), and several trade-prediction/analysis pieces.
Real trade substance, not noise.

### 3. Suspensions — GREEN

`"NFL suspension"` returned specific, real suspension content: a
confirmed Tracy Walker III suspension (three games, named), the Justin
Tucker/Jets tryout storyline tied explicitly to his prior suspension,
and the ongoing Puka Nacua/Josh Jacobs disciplinary situations with
named sourcing (team, allegation type, process stage). Genuinely
substantive, not vague.

### 4. Roster changes — GREEN

Covered well by the trade and coaching samples above (final 53-man
roster construction, waiver claims, position battles) — real,
timely-to-late-August roster-cut coverage.

### 5. Lineup/depth-chart news — GREEN, a genuine strength

`"NFL depth chart"` was the strongest category in the whole sample:
Jets QB depth chart questions, an explicit "Updated Chicago Bears Depth
Chart After Roster Cuts" piece (traded/cut/kept players named by
position), Giants WR depth chart post-Beckham-signing, Cowboys RB2
competition, and a Steelers OL depth battle with specific player names
and snap-count-level detail. This is genuinely depth-chart-level
content, arguably a closer match to HQ's own named criterion than
NewsAPI's broader `"{team} NFL"` query would surface on its own.

### 6. Coaching news — GREEN, with a precision caveat

`"NFL head coach"` returned real NFL coaching content (Mike Vrabel/
Patriots, Mike Macdonald/Seahawks, Ben Johnson/Bears) but also pulled
in two **college football** coaching stories (Lane Kiffin/LSU, Deion
Sanders/Colorado) that only match because they mention "NFL" in passing
(a former player, a coach's NFL playing history). A real, modest query-
precision gap — not a broken feature, but worth knowing before assuming
every result is NFL-scoped just because the query included "NFL."

### 7. Source diversity and quality — MIXED

Category-level queries (trade, suspension, coaching, depth chart) drew
from 6-8 distinct, credible outlets each (Newsweek, Bleacher Report,
Sports Illustrated, Heavy., theScore, TSN, Yardbarker, Boston Herald,
Spokesman-Review, AL.com, Pittsburgh Tribune-Review). **But the
team-scoped `"Kansas City Chiefs NFL"` query was dominated by a single
low-relevance source**: 5 of 6 results were Times of India (`country:
"in"`) tabloid-style Travis Kelce content — a business-lawsuit story, a
"health scare" story, an NFL-fine story, Gracie Hunt's personal
wellness investment, and an emotional-interview piece. Only 1 of 6 was
genuine football analysis. This is a real, concrete "one aggregator can
dominate a broad team query" risk NewsAPI's own `"{team} NFL"`
construction is equally exposed to in principle, but which this sample
actually demonstrated for GNews specifically.

**Actionable finding**: GNews's `source.country` field (present on
every article, `"us"`/`"in"`/`"ca"` observed) gives MANSA a real,
already-available lever to filter out this exact problem — restricting
ingestion to `source.country == "us"` (or a small allowlist) would have
removed all 5 of the low-relevance Chiefs articles in this sample while
keeping the genuine one. NewsAPI's adapter has no equivalent field
today (`NewsArticle.source` is a bare name string).

### 8. Duplicate/noisy results — LOW duplication, some category noise

Zero duplicate URLs within any single call's result set across all 9
Run 2 calls (`duplicate_url_count: 0` every time) — GNews's own
de-duplication is solid at the single-query level. The noise that does
exist is topical, not duplicative: the bare `"NFL"` pagination-test
query (page 2) surfaced celebrity content (a Travis Kelce/Taylor Swift
real-estate story) and an unrelated tragedy story (a former player's
death) alongside genuine football content — expected behavior for an
unscoped single-word query, and exactly why MANSA's own News Worker
already never issues one (see `app/workers/news_worker.py`'s own
docstring: it always calls `fetch_news(team=<resolved name>)`, never
`fetch_news(team=None)`).

### 9. Publication timestamps and real-time latency — the most important
finding

**Every single successful call (all 9 in Run 2, all 5 successful in Run
1) carried this notice in the response body's `information` field:**

> "Real-time news data is only available on paid plans. Free plan has a
> 12-hour delay. Upgrade your plan here to remove the delay:
> https://gnews.io/change-plan"

This is HQ's confirmed, already-paid Essential subscription — the
notice's own wording ("Free plan has a 12-hour delay... upgrade") reads
as though it should not apply here. Two explanations are possible, and
this report cannot distinguish between them from outside GNews's own
account dashboard: **(a)** real-time delivery is gated to a *higher*
tier than Essential specifically (Essential may be a "paid but still
delayed" tier, distinct from "paid and real-time"), or **(b)** the
subscription hasn't fully propagated on GNews's backend yet. Empirical
evidence leans toward this being a real, current limitation rather than
a stale label: sorted strictly by `publishedAt` descending, the single
freshest article for high-volume queries (`"Kansas City Chiefs NFL"`,
`"NFL trade"`, bare `"NFL"`) was consistently **17–34 hours old** at
capture time — worse than the 12 hours the notice itself claims as the
*free*-tier ceiling.

**This is squarely a live-game-adjacent freshness question, the same
class of unresolved item the MySportsFeeds gate exists for** — pricing
and category coverage being confirmed doesn't mean the timeliness this
plan actually needs is confirmed. **Recommendation: HQ should ask GNews
support directly whether Essential includes real-time delivery or
whether it requires a higher tier**, before this plan is treated as
settled either way.

### 10. API reliability / pagination / schema quality — MIXED

- **Reliability**: Run 1's 44% rate-limit failure rate at 1.5s spacing
  (well inside the documented 10 req/sec ceiling) is a real reliability
  concern for a shared/cached architecture that may need to fire many
  team-scoped calls in a short window (see request-volume finding
  below). Run 2's 5s spacing was clean (9/9 success), but 5s between
  calls is a much tighter practical constraint than "10 req/sec" implies
  on paper.
- **No rate-limit visibility**: every response's headers were checked
  for `ratelimit`/`retry-after`/`quota`-named headers — **none were
  present on any call, success or failure**. GNews gives MANSA no
  proactive quota-remaining signal the way The Odds API's `x-requests-
  remaining` does; a production integration would have to track its own
  budget blind, only discovering a limit via a `429`.
- **Pagination**: `page=2` was accepted with a `200` and returned a
  different-looking result set (not an error, not a silent ignore) —
  Essential does appear to honor `page`, a genuine capability NewsAPI's
  own adapter doesn't currently use either way.
- **Schema quality**: consistently well-formed across all 47 articles
  observed (9 calls × up to 10 articles, minus the 3-article
  `full_content_expand_test` call) — no malformed entries, no missing
  required fields, in this sample.
- **Latency**: 300–360ms per call — fine for a 15-minute-cadence
  background worker, not a bottleneck either way.

### 11. Commercial-use suitability — UNRESOLVED, needs a direct answer

Could not be independently confirmed (docs.gnews.io/gnews.io/legal
pages are blocked by this workspace's own egress policy, same
constraint as every prior vendor). Public/WebSearch-indexed sources
consistently describe GNews's *free* tier as explicitly non-commercial
and paid tiers (including Essential) as commercial-use-eligible — but
given the real-time-delay notice above appearing on a supposedly-paid
key, **this report does not treat any GNews-side claim about this
key's entitlements as settled without direct confirmation from GNews
or Mac's own account dashboard.**

---

## Additional evaluation questions (HQ's "also evaluate" list)

- **Query precision to NFL-relevant content**: good for specific,
  qualified queries (`"NFL depth chart"`, `"NFL trade"`, `"NFL
  suspension"`); weaker for broad team-name queries (`"Kansas City
  Chiefs NFL"` pulled mostly non-football Kelce content) and for
  `"NFL head coach"` (pulled in adjacent college-football content). A
  production integration would likely need query patterns closer to
  the specific-category style than the bare team-name style
  `NewsAPINewsAdapter` currently uses.
- **Structured metadata for MANSA ingestion**: strong — `id` (stable
  per-article), `source.id` (stable per-publication, confirmed reused
  identically across every article from the same outlet in this
  sample), `source.country`, and `lang` are all present on every
  article and are NOT captured by the current `NewsArticle` model
  (`headline`, `url`, `source: str`, `published_at`, `summary`,
  `related_teams` — no id, no country, no lang field exists today). A
  GNews adapter could carry richer identity/provenance than NewsAPI's
  adapter currently does, but only if `NewsArticle` itself were
  extended — a real, undecided model change, not something this report
  makes unilaterally.
- **URL/source identity stability**: article URLs in this sample all
  pointed to real, canonical publisher domains (heavy.com, si.com,
  bleacherreport.com, nypost.com, etc.) — no redirect/shortlink
  patterns observed. `source.id` was stable and reused correctly within
  this sample (e.g., every Heavy. article shared the identical
  `source.id` value).
- **Whether full-content access materially helps downstream AI
  analysis**: **could not be confirmed — `expand=content` did NOT
  change the `content` field's length in this test.** Every article
  across all 9 Run 2 calls, including the dedicated `expand=content`
  call, carried the identical ~266-character truncated content with a
  `"... [N chars]"` suffix naming the true total length. Either
  `expand=content` requires a tier above Essential, or (again) the
  account isn't fully provisioned — the same open question as the
  real-time-delay finding above, and not resolved by this report. Worth
  noting: MANSA's current `NewsAPINewsAdapter` doesn't use NewsAPI's
  `content` field at all today (only `description`), so this
  limitation is parity with current behavior, not a new regression —
  but it does mean "full content" isn't a confirmed upside of switching
  either.
- **Likely request volume under a centralized/cached MANSA
  architecture — a real capacity concern, not just a cost one.**
  `news_worker.py`'s own confirmed design (Volume 2 §8): flat 15-minute
  cadence, **no ramp tiers, no stop-at-kickoff**, one call per due team.
  During an NFL week, most/all 32 teams have a game inside the worker's
  7-day candidate window simultaneously — worst-case (and, in-season,
  close to *typical*-case) volume is **32 teams × 96 cycles/day = up to
  3,072 calls/day**, roughly **3x GNews Essential's confirmed 1,000
  req/day cap**, before even accounting for Run 1's evidence that real
  burst behavior is stricter than the per-second ceiling implies. This
  is independent of the pricing question — even a materially cheaper
  provider is not viable if its quota can't cover MANSA's actual
  per-team cadence. **This should be treated as a hard input to any
  GNews adoption decision, not just a nice-to-know.**

---

## Comparison against the known NewsAPI Business baseline

| Dimension | NewsAPI Business ($449/mo) | GNews Essential (€49.99/mo, ≈$54 USD) |
|---|---|---|
| Injury/trade/suspension/roster content quality | Not independently re-tested this pass (baseline assumed from existing production use) | GREEN across all four in this sample |
| Depth-chart/lineup specificity | `"{team} NFL"` query only, no depth-chart-specific querying done today | GREEN, genuinely strong with a targeted query |
| Structured metadata | `source: {id?, name}` (adapter uses `name` only), no country/lang field | Richer: `id`, `source.id`, `source.country`, `lang` all present and usable |
| Full-content access | Adapter doesn't use NewsAPI's `content` field today | Could not confirm `expand=content` works on this key/tier — unresolved |
| Real-time freshness | Assumed real-time on Business tier (not independently re-verified this pass) | **Every response flagged a real-time-delay notice; empirical freshest article was 17-34 hours old** — a real, unresolved gap |
| Rate-limit reliability | Not tested this pass | 44% failure rate at 1.5s spacing in Run 1; clean only at 5s spacing |
| Request-volume headroom vs. MANSA's actual cadence | Not directly compared (NewsAPI's own daily cap wasn't re-verified this pass) | **~3x under MANSA's own worst-case/typical-case 32-team, 15-minute-flat cadence** — a real, material capacity gap |
| Commercial-use terms | Confirmed (NewsAPI Business is explicitly commercial-use-eligible, the reason it's the current default) | Publicly described as commercial-eligible on paid tiers, but not independently confirmed for this key given the real-time-delay anomaly above |
| Price | $449/mo | ≈$54/mo — the ~$395/mo delta the business plan's News Provider Validation Gate was built around |

---

## Recommendation

**Do not select GNews Essential as MANSA's production news provider
from this report alone.** Content quality for four of six named
categories (injuries, trades, suspensions, depth-chart/lineup) was
genuinely strong — better than the "unknown"-riddled injury data
MySportsFeeds and SportsDataIO both showed in prior bake-offs — and the
richer structured metadata (`source.country`, stable `source.id`) is a
real, usable win over NewsAPI's current adapter shape. **But three
concrete, unresolved problems block a production recommendation on
price alone, exactly as HQ's own instruction anticipated:**

1. **The real-time-delay notice on every call, and freshest-article
   ages of 17-34 hours, are inconsistent with paying for a plan whose
   own marketing implies real-time delivery.** This needs a direct
   answer from GNews (does Essential include real-time, or does it
   require a higher tier?) before HQ can trust GNews for anything
   latency-sensitive (injury alerts, breaking trades).
2. **Essential's 1,000 req/day quota is materially short of MANSA's own
   confirmed News Worker cadence (~3,072 calls/day at typical in-season
   volume)** — this is a hard capacity ceiling, not a soft cost
   optimization; adopting GNews as-is would require either relaxing the
   worker's flat 15-minute cadence (a real product/architecture change,
   not assumed here) or a higher, likely more expensive, GNews tier
   that would erode some or all of the price advantage this gate exists
   to evaluate.
3. **The observed 44%-then-clean rate-limit behavior (Run 1 vs. Run 2)
   means the account's real, sustainable throughput is not yet known
   with confidence** — 5s-per-call spacing worked once; it has not been
   proven to hold under sustained, production-scale request volume.

**None of these three is a reason to reject GNews outright** — they are
exactly the kind of thing a controlled trial period exists to surface
before a $449/month recurring decision is made either way. **Escalate
items 1 and 2 to GNews support directly** (a specific, answerable
question: "does Essential include real-time delivery, and what's the
actual sustained rate limit in practice?") **before spending a 10-day
trial on anything** — if Essential structurally cannot deliver
real-time or cannot clear MANSA's own request volume, no amount of
additional trial time changes that, and a different (likely costlier)
GNews tier would need to be the actual comparison point against NewsAPI
Business, not Essential. Once that's answered, the News Provider
Validation Gate's original 10-day-trial recommendation still stands for
whatever tier turns out to be the real comparison.

---

## What was and wasn't changed

**Full revert, same discipline as every prior probe.**
`app.diagnostics.gnews_validation`, the dev-only startup hook in
`app.main`, and `build_gnews_validation_client()` in
`production_clients.py` were all removed after this report was
produced — none of it exists in the codebase now (diffed directly
against the pre-task commit to confirm an exact match, not just visual
inspection). `RUN_GNEWS_VALIDATION` was set back to `"0"` on Railway.
`GNEWS_API_KEY` was never logged or surfaced outside the one client
that used it.

**Tests**: 636/636 sports-intel-layer passing before, during (with the
diagnostic module present), and after the revert. **Deployment**: DEV
only, `sports-intel-layer` only. `cron-odds-worker` untouched throughout
(a separate service; nothing in this task's pushes touched it or its
frozen state). Staging and production untouched throughout. No database
writes at any point. No subscription purchased, upgraded, or changed —
GNews Essential was already active before this task began, and remains
unchanged.

**Remaining validation, not done here**: a direct GNews support inquiry
on real-time entitlement and sustained rate limits (recommended above);
a request-volume trial run against MANSA's actual News Worker cadence
once the tier/entitlement question is resolved; confirmation of
`expand=content`'s real behavior once account provisioning is
confirmed; a same-day cross-check of GNews vs. NewsAPI on an identical
query, if NewsAPI is ever re-tested for direct comparison (not done
this pass, since GNews was the only new credential HQ configured).
