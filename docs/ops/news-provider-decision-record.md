# MANSA News Provider Decision Record

**Living document — updated as each News provider diagnostic pass
closes. Not a build spec: no provider migration or subscription change
has been made or authorized as of the most recent entry below. NewsAPI
Business remains the current, unswapped production default throughout
everything on this page.**

Source reports, in order:
1. `docs/business/mansa-business-entitlement-plan-2026-09-03.md` (STEP
   1/2 + News Provider Validation Gate) — the economic case for
   comparing NewsAPI Business against GNews Essential.
2. `docs/ops/news-provider-validation-gnews-2026-09-03.md` — the
   controlled GNews Essential diagnostic against HQ's 11 named
   evaluation criteria.
3. `docs/ops/news-cadence-architecture-audit-2026-09-04.md` — a
   redesigned, centralized/adaptive News Worker cadence and a
   recalculation of GNews Essential's request-volume fit against it.

---

## UPDATE (2026-09-04): the volume blocker is resolved; the freshness
blocker is NOT

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
Essential's quota even under deliberately generous assumptions.

**This does not change the "NOT DECIDED" status below.** The real-time-
entitlement and `expand=content` blockers are completely independent of
request volume and remain exactly as open as they were on 2026-09-03 —
resolving the volume question removed one reason to hesitate on GNews,
it did not supply a reason to select it. No News Worker code has
changed; this redesign remains a documented direction, not an
implementation.

---

## Current status (2026-09-03, volume blocker superseded 2026-09-04): NOT DECIDED, two concrete blockers

**GNews Essential is not recommended for production adoption yet — not
because it's unproven on content quality (four of six named categories
tested GREEN), but because two specific, answerable questions remain
open and materially affect whether it can do the job at all:**

1. **Real-time entitlement is unconfirmed.** Every diagnostic call
   against the paid, already-active Essential subscription carried a
   response notice implying free-tier-level delay ("Free plan has a
   12-hour delay... upgrade your plan"), and the empirically freshest
   article available for high-volume queries was 17-34 hours old.
   Whether this is a real Essential-tier limitation (real-time requires
   a higher tier) or a provisioning lag needs a direct answer from
   GNews support — not assumed either way.
2. ~~Request-volume headroom is short.~~ **SUPERSEDED 2026-09-04 — no
   longer a blocker.** This was correctly derived from the *current*
   News Worker design (32 independent team queries/15-min flat cadence,
   ~3,072 calls/day at typical in-season volume, ~3x Essential's 1,000
   req/day quota) — but HQ has since confirmed that design is not an
   accepted production requirement. `docs/ops/news-cadence-architecture-audit-2026-09-04.md`
   recalculates volume under a redesigned, centralized/adaptive cadence
   (broad category queries + post-ingestion classification + adaptive
   windows + justified-only targeted refresh) at one to two orders of
   magnitude under quota. **The remaining live blocker is #1 above
   only** — real-time entitlement/freshness, completely independent of
   volume.

**Reasoning for holding the decision open, not defaulting to either
provider:**
- GNews's content quality, when it worked, was genuinely strong —
  better than the "unknown"-riddled injury data seen from both
  MySportsFeeds and SportsDataIO in the NFL provider bake-offs — so
  rejecting it purely on price-skepticism grounds would be wrong.
- Committing to GNews without resolving items 1-2 above risks
  discovering, only after cancelling or downgrading NewsAPI, that
  GNews cannot actually deliver the freshness or volume MANSA's product
  needs — the exact "don't select on price alone" failure mode HQ's own
  instruction was written to prevent.
- NewsAPI Business's own real-time entitlement and true daily quota
  were **not independently re-verified this pass either** — the
  comparison table in the validation report is honest about that gap.
  This record does not claim NewsAPI is confirmed superior, only that
  GNews is not yet confirmed sufficient.

---

## What's needed before this decision can close

1. **A direct question to GNews support**: does the Essential tier
   include real-time article delivery, or does real-time require a
   higher tier? If a higher tier is required, get its price and req/day
   quota — that tier, not Essential, becomes the real comparison point
   against NewsAPI Business's $449/mo.
2. **Confirmation of Essential's real, sustained rate limit** — Run 1 of
   the 2026-09-03 validation saw a 44% failure rate at 1.5s spacing
   despite a documented 10 req/sec ceiling; Run 2 was clean only at 5s
   spacing. A short sustained-load check (not a full 10-day trial)
   would confirm whether 5s-per-call is the real practical ceiling.
3. ~~A capacity decision, independent of price.~~ **RESOLVED 2026-09-04
   — not a blocker under a properly designed architecture** (see the
   UPDATE section at the top of this record). Still requires HQ to
   actually authorize the News Worker redesign itself before any of
   this is real — the recalculation is a planning result, not a built
   capability.
4. **Once 1-2 (freshness/rate-limit) are answered**, run the News
   Provider Validation Gate's original recommendation: a GNews 10-day
   trial (at whichever tier answers them satisfactorily) focused on the
   criteria this pass could not fully resolve — sustained freshness
   during a real live-game window, and request-volume behavior under
   closer-to-production load, now informed by the redesigned cadence
   rather than the original 32-team design.

## Do NOT, at any point before this record is updated to CLEARED:
- Cancel, downgrade, or change the NewsAPI Business subscription.
- Migrate `app/workers/news_worker.py` or
  `app/adapters/providers/newsapi.py` to GNews.
- Change the News Worker's cadence/ramp design to accommodate GNews's
  quota without a separate, explicit product decision.
- Leave a diagnostic probe in the codebase — revert it, per the
  established discipline, once a report is written.

## Closing this record

Once GNews support answers the real-time/rate-limit questions (or a
10-day trial resolves them empirically), update this record's "Current
status" section with the real result (GNews confirmed sufficient /
GNews confirmed insufficient / a different GNews tier is the real
comparison point), add a dated entry to `PROGRESS.md` following the
same convention as the two entries already there for this News provider
work, and produce a dated follow-up report if a trial is actually run.
Only then does this record move from **NOT DECIDED** to a real
recommendation Mac can act on.

---

## Provider-role summary as of 2026-09-04

| Role | Current provider | Confidence |
|---|---|---|
| Production news (all categories) | NewsAPI Business ($449/mo) | Current, unswapped, real-time entitlement not independently re-verified this pass |
| Candidate replacement | GNews Essential (≈$54/mo) | Content quality GREEN on 4/6 categories; request-volume headroom RESOLVED (not a blocker under a redesigned cadence, 2026-09-04); real-time entitlement/freshness UNRESOLVED — see blockers above |
| News Worker cadence | 32 teams/15-min flat (current, live) | Confirmed not an accepted production requirement (2026-09-04); redesign direction proposed, NOT implemented — `docs/ops/news-cadence-architecture-audit-2026-09-04.md` |
