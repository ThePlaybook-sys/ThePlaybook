# MANSA News Provider Decision Record

**Living document — updated as each News provider diagnostic pass
closes.** GNews is now MANSA's **development** news provider (HQ
decision, 2026-09-04, below). NewsAPI Business remains the current,
unswapped **production** default and an alternative benchmark — **not
an authorized purchase to replace with GNews.** No GNews upgrade,
migration, or production selection has been made or authorized as of
the most recent entry below.

**CORRECTION (2026-09-04, HQ clarification): the 2026-09-03 GNews
validation actually ran against GNews's FREE plan, not Essential.**
Every place below (and in the source validation report) that treated
the observed 12-hour delay or the `expand=content` no-op as an
*Essential provisioning problem* was wrong — both are expected,
documented Free-plan behavior. This is corrected throughout this
record and in `docs/ops/news-provider-validation-gnews-2026-09-03.md`
directly. It does not change the underlying fact that real-time
freshness, paid full-content access, and sustained rate/quota behavior
on a commercially-usable GNews tier remain **untested** — it changes
only *why* they're untested (wrong tier exercised, not a discovered
defect in the right one).

Source reports, in order:
1. `docs/business/mansa-business-entitlement-plan-2026-09-03.md` (STEP
   1/2 + News Provider Validation Gate) — the economic case for
   comparing NewsAPI Business against GNews.
2. `docs/ops/news-provider-validation-gnews-2026-09-03.md` — the
   controlled GNews diagnostic against HQ's 11 named evaluation
   criteria — **actually run on the Free plan, corrected 2026-09-04.**
3. `docs/ops/news-cadence-architecture-audit-2026-09-04.md` — a
   redesigned, centralized/adaptive News Worker cadence and a
   recalculation of GNews Essential's published request-volume fit
   against it.

---

## UPDATE (2026-09-04): the volume blocker is resolved; the freshness
question was never actually tested on the right tier

The 2026-09-03 validation's second blocker — GNews Essential's 1,000
req/day quota being ~3x short of MANSA's actual cadence — was correctly
derived from the *current* News Worker design (32 independent team
queries every 15 minutes, no stop-at-kickoff), which HQ has since
confirmed is not an accepted production requirement, only the design
this project happened to build first. Under a redesigned, centralized/
adaptive cadence (broad category queries instead of 32 team queries,
entity/team classification after ingestion, adaptive/game-aware
cadence reusing the existing `app.workers.windows` discipline, targeted
team refresh only when justified — full detail in the linked audit),
recalculated volume lands one to two orders of magnitude under
Essential's published quota even under deliberately generous
assumptions.

**Separately (same day, later correction): the real-time-entitlement
"blocker" was never real in the first place — the validation that
surfaced it ran on GNews's Free plan, not Essential**, so the 12-hour
delay it observed was expected Free-plan behavior, not evidence
Essential is broken or under-provisioned. Real-time freshness on a
paid tier remains **untested**, not **found insufficient** — a
meaningfully different status, now reflected in the "Current status"
section below rather than left as an open "blocker."

---

## Current status (2026-09-04): GNews is MANSA's DEVELOPMENT news provider; PRODUCTION decision deferred to a 6-item gate

**HQ decision, 2026-09-04: GNews remains MANSA's development news
provider. Do not upgrade or migrate providers now.** The redesigned
centralized/adaptive News architecture (`docs/ops/news-cadence-architecture-audit-2026-09-04.md`)
remains the intended direction — the previous ~3,072 calls/day design
is confirmed not an accepted production requirement, independent of
which provider ends up serving production.

This is a real, current decision for **development use** — it is not
the same thing as a **production** provider selection, which remains
open and gated below. The 2026-09-03 validation's two originally-framed
"blockers" are now understood differently, not both cleared:
- **Request volume**: genuinely resolved — not a blocker under the
  redesigned architecture, at any tier.
- **Real-time freshness / `expand=content` / commercial terms**: **never
  actually tested** — the validation that was supposed to test them ran
  on the Free plan by mistake, so there is no finding to stand on either
  way. These are exactly the kind of thing that must be tested for real
  before a production decision, not treated as either passed or failed
  based on a Free-plan result.

**Content quality remains a genuine point in GNews's favor** (four of
six named categories tested GREEN, richer structured metadata than
NewsAPI's current adapter shape) — this record does not walk that back,
only the freshness/full-content/rate-limit claims that were
mischaracterized.

---

## Production/Beta Gate — six items, in order, before a final GNews production decision

Per HQ's explicit instruction, none of these six items is done yet, and
none is authorized to start by this record alone:

1. **Upgrade to the appropriate commercially-usable GNews tier** — the
   real comparison point against NewsAPI Business's $449/mo, whatever
   that tier turns out to require (Essential, or higher, depending on
   what items 2-3 below actually need).
2. **Validate real-time NFL freshness** on that tier — the question the
   2026-09-03 pass never actually answered, corrected above.
3. **Validate paid full-content (`expand=content`) behavior**, if
   full-content access is actually needed for anything MANSA plans to
   build against it.
4. **Validate actual quota/rate behavior under MANSA's redesigned
   cadence** (`docs/ops/news-cadence-architecture-audit-2026-09-04.md`)
   — not the old 32-team design, and not assumed from a published spec
   sheet alone.
5. **Reconfirm commercial-use terms** directly for the tier actually
   provisioned — not inferred from a public pricing page, per the
   same correction above.
6. **Only after 1-5**, make the final GNews production-provider
   decision.

**NewsAPI Business remains an alternative benchmark, not an authorized
purchase** — nothing above authorizes cancelling, downgrading, or
replacing it.

## Do NOT, at any point before this gate closes:
- Cancel, downgrade, or change the NewsAPI Business subscription.
- Upgrade or migrate the GNews subscription/tier without a separate,
  explicit HQ authorization (item 1 above is a gate item, not a
  standing authorization to act on it unilaterally).
- Migrate `app/workers/news_worker.py` or
  `app/adapters/providers/newsapi.py` to GNews.
- Change the News Worker's cadence/ramp design to accommodate GNews's
  quota without a separate, explicit product decision.
- Leave a diagnostic probe in the codebase — revert it, per the
  established discipline, once a report is written.
- Touch staging or production, or any Phase 7 gate, in service of any
  of the above.

## Closing this gate

Once all six production/beta gate items above are validated for real
(a real upgraded-tier test, not another Free-plan run), update this
record's "Current status" section with the real result, add a dated
entry to `PROGRESS.md` following the same convention as the entries
already there for this News provider work, and produce a dated
follow-up report for whichever tier was actually tested. Only then does
this record move from "GNews is the dev provider, production
undecided" to a real production recommendation Mac can act on.

---

## Provider-role summary as of 2026-09-04

| Role | Current provider | Confidence |
|---|---|---|
| Production news (all categories) | NewsAPI Business ($449/mo) | Current, unswapped, real-time entitlement not independently re-verified this pass |
| Development news provider | GNews | **Confirmed HQ decision, 2026-09-04.** Content quality GREEN on 4/6 categories (plan-independent finding); request-volume headroom RESOLVED under a redesigned cadence; real-time freshness/`expand=content`/commercial terms UNTESTED (2026-09-03 pass ran on Free plan by mistake, corrected 2026-09-04) — not "found insufficient," genuinely untested |
| Production candidate | GNews (tier TBD) | UNDECIDED — gated on the 6-item Production/Beta Gate above; no upgrade/migration authorized |
| News Worker cadence | 32 teams/15-min flat (current, live) | Confirmed not an accepted production requirement (2026-09-04); redesign direction proposed, NOT implemented — `docs/ops/news-cadence-architecture-audit-2026-09-04.md` |
