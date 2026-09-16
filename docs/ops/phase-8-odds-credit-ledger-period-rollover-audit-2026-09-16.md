# Odds Credit Ledger Period Rollover — Audit (2026-09-16)

**Directive:** MANSA HQ — "ODDS CREDIT LEDGER PERIOD ROLLOVER HARDENING." Audit first. *"Do not
invent the provider billing/reset period if it is not already known. If the actual renewal/reset
cadence cannot be established from persisted configuration or existing provider/account evidence:
STOP AND REPORT what owner input is needed before implementing date arithmetic."*

**Outcome: STOPPED at that gate.** The allowance *size* is confirmed (500 credits/month). The
allowance *boundary* — when a period begins and ends — is **not established anywhere**, and every
candidate rule gives a materially different answer. No date arithmetic was implemented, no schema
changed, no code changed.

**Compliance:** zero provider calls, zero LLM calls, no cron cadence changed,
`MASTER_REFRESH_ENABLED` untouched (`false`). Read-only throughout.

---

## 1. Root cause

Three separate facts, each verified directly:

**(a) `record_call` never writes `period_start`.** Its upsert payload contains exactly three keys:

```python
json={
    "provider_name": provider_name,
    "credits_used_this_period": new_total,
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
```

On insert, `period_start` takes the column default `now()`. On every subsequent upsert
(`resolution=merge-duplicates`) the column is simply absent from the payload, so PostgREST leaves
it untouched. It has therefore held one value since the row was born and can never change on its
own.

**(b) `period_start` is never read by any logic.** A repo-wide grep finds exactly one reference in
the odds path — inside the `select=` list of `read_credit_ledger`. It is fetched and then never
compared to anything. `_check_credit_guard` uses only `credits_used_this_period`:

```python
remaining = budget - used
return remaining > floor, used
```

So the column is **decorative today**. The guard has no concept of a period at all; it compares a
monotonically increasing lifetime counter against a monthly-sized budget.

**(c) This is a documented, deliberate scope limit — not an oversight.** The migration that
created the table says so in its own header:

> *"No automatic monthly period rollover is built here — a real 'is it a new calendar month' reset
> is a disclosed, deliberate scope limit for this pass (HQ can reset the counter manually, or a
> future milestone can add real rollover); the guard's job today is 'never silently exceed the
> free-tier budget,' not 'automatically track billing periods.'"*

This directive is that future milestone. The prior pass correctly identified the consequence: at
some point `credits_used_this_period` crosses 450, the guard trips, and — because nothing ever
resets it — **it stays tripped permanently**, silently stopping odds collection while the real
vendor allowance is full.

---

## 2. Authoritative meanings, as they exist today

| Field | Authoritative meaning **today** | Is it what the name implies? |
|---|---|---|
| `period_start` | The moment the ledger row was first created — i.e. the timestamp of the **first ever real odds call**, `2026-09-07 02:30:23.554545+00`. | **No.** It is a row-creation timestamp, not a billing anchor. |
| `credits_used_this_period` | Our own count of **real provider round-trips × 3**, accumulated since that row was created. Never incremented on a cache hit, a failed call, or a guard-skipped call. | Partly — it is accurate usage, but "this period" is a misnomer: it is **lifetime** usage. |
| Configured allowance | `THE_ODDS_API_MONTHLY_CREDIT_BUDGET` = **500** | Yes — confirmed, see below. |
| Reserve / floor | `THE_ODDS_API_MIN_REMAINING_CREDITS` = **50**. Guard fails **closed** when `budget − used <= floor`, i.e. **trips at 450 used**. Fails **open** (disclosed no-op) if either variable is unset. | Yes. |
| Reset date semantics | **NONE EXIST.** No reset logic, no anchor, no cadence, anywhere in code, schema, or config. | — |

### The allowance size IS confirmed — 500 credits/month

Five independent records, established in the previous pass and re-verified: the literal
`THE_ODDS_API_MONTHLY_CREDIT_BUDGET=500` recorded the day it was set; the plan it came from ("The
Odds API's free Starter plan is 500 credits/month", from the 2026-08-10 procurement checkpoint
corrected against Mac-supplied official vendor data); ledger readings `174/500`, `180/500`,
`234/500`; and the derived "450-credit safety trip point" recorded twice, which is exactly
`500 − 50`.

### The allowance BOUNDARY is not confirmed, and that is the blocker

Everything this project holds about the vendor's own quota accounting is explicitly flagged
unverified:

- `x-requests-remaining` / `x-requests-used` — *"ASSUMED header names, not live-verified; logged
  only, never parsed/raised on"*, and separately *"presence/exact names unconfirmed"*.
- No account signup date, no billing anchor, no renewal cadence, and no vendor documentation of
  reset semantics exists anywhere in the repo, `PROGRESS.md`, `docs/`, or any migration.

**I must correct my own previous report here.** In the cron/Sentry pass I wrote that *"the vendor's
month rolls over around 2026-10-07."* That was wrong, and it is exactly the kind of error that
would have produced incorrect date arithmetic had I implemented on it. It was inferred from
`period_start`, which — per §1(a) — is merely the timestamp of our first call. It carries no vendor
billing meaning whatsoever. **There is no evidence the vendor's period is anchored to 2026-09-07.**

---

## 3. What owner input is needed

**One question, and it decides everything:**

> **On what schedule does The Odds API reset the 500-credit Starter allowance?**

The two realistic candidates are not close together, which is why guessing is unacceptable:

| Candidate rule | Next boundary from today | Consequence if we implement the wrong one |
|---|---|---|
| **Calendar month, UTC** — resets 1st of each month at 00:00 | **2026-10-01 00:00 UTC** | If the truth is anniversary-based, we reset ~6 days early and can overspend a real allowance without the guard objecting. |
| **Signup/subscription anniversary** — resets on the account's own monthly date | unknown — depends on the signup date, which is **not recorded anywhere** | If the truth is calendar-based, we hold a stale period ~6 days too long and the guard may block while credits are actually available. |

A third possibility — a rolling 30-day window — cannot be excluded either, and would behave
differently again.

### How to get the answer at zero provider-API cost

**Preferred — the vendor dashboard (no API call at all).** Sign in to the-odds-api.com account
page. It shows usage against the quota and, typically, the period or reset date. That single
screenshot or figure settles the rule. This is a web page the owner reads; it spends no credits.

Two specific things worth capturing while there, because they also validate our own ledger:

1. **The reset date or period** — the actual answer.
2. **The vendor's own "used" figure for the current period.** If it reads far below our 276, a
   vendor-side reset has already occurred and our counter has been over-reporting since — which
   would be a second, independent confirmation that rollover is real and overdue.

**Alternative, if the dashboard does not state it:** the answer can be observed for free from
response headers we already receive on every call. The adapter logs `x-requests-remaining` /
`x-requests-used` today but discards them. Persisting those two values alongside each call would
let a reset be *detected empirically* — a sharp drop in the vendor's own used-count is a rollover,
with no extra provider call and no date arithmetic.

**Two caveats on that alternative, stated plainly.** The header names remain ASSUMED and
unverified, so this cannot be the sole mechanism. And it cannot satisfy the directive's own
requirement 4 — *"the first worker tick in a new period must not require a provider call just to
discover that rollover occurred"* — because a header only arrives *on* a call. It is a strong
corroborating signal and a good belt-and-braces addition; it is not a substitute for knowing the
rule.

---

## 4. Interim safety, and how much time there actually is

**The risk is real but not imminent, and the arithmetic is worth having.**

- Current: **276 / 500** used, trip at **450**.
- Headroom: **174 credits = 58 calls**.
- Measured burn: ~2 calls (6 credits) on a quiet day; ~19 calls (57 credits) on a 13-game Sunday.
- Newly armed daily ceiling: **20 calls/day max**.

So the earliest conceivable trip is ~3 days of maximum spend; the realistic trajectory
(quiet weekdays plus one Sunday per week) puts it roughly **2–3 weeks out**. It will happen, and
when it does it is permanent under current code — but nothing breaks tomorrow.

**A zero-arithmetic interim mitigation already exists and is explicitly contemplated by the
migration:** *"HQ can reset the counter manually."* A one-line update to
`credits_used_this_period` (and, if desired, `period_start`) removes the permanent-block risk at
any time without implementing any rule. **Not done this pass** — it is a judgment call about real
spend against a real allowance, and it is the owner's to make, not mine.

---

## 5. Design ready to implement, once the rule is known

Recorded now so that the implementation pass is mechanical rather than exploratory. **Nothing
below was built.**

The shape that satisfies all seven of the directive's requirements without any of the traps:

**Make the period part of the row's identity, exactly as the daily budget already does.** The
2026-09-16 daily-call budget table solved the identical problem by being **day-keyed**, so a new
day simply has no row yet and reads as zero — *"no rollover logic at all"*. `news_provider_daily_quota`
uses the same trick. A `period_key` (e.g. `2026-10`) column with
`unique (provider_name, period_key)` makes rollover a **lookup, not a mutation**:

- **Requirement 1 & 6** — a new period has no row, so it reads zero and cannot be blocked by the
  old one. A stale row is inert by construction rather than by a reset succeeding.
- **Requirement 2 & 5** — the old row is never touched, so history is preserved automatically.
  This is strictly safer than mutating `period_start` in place, which destroys the audit trail the
  directive requires be kept.
- **Requirement 3 (idempotent, concurrency-safe)** — an atomic upsert keyed on
  `(provider_name, period_key)`, mirroring the existing `increment_odds_api_daily_calls` RPC. Two
  concurrent rollovers converge on one row; neither can create a conflicting active period.
  Deliberately stronger than the current ledger's accepted read-then-write race, since this is a
  hard spending guard.
- **Requirement 4** — the period key is computed from the clock, so the first tick of a new period
  discovers rollover with **no provider call**.
- **Requirement 7** — a restart changes nothing, because usage lives in the database keyed by
  period, not in process memory.

The **only** missing input is the function that maps "now" to a `period_key` — and that is
precisely the rule §3 is asking for.

The existing row would be backfilled with the period key its `period_start` falls in, preserving
the 276 figure as genuine history rather than discarding it.

---

## 6. Tests — not written, and why

The directive's ten proofs (A–J) are all mechanical against the design in §5, and every one of
them depends on the boundary function. Writing tests A, B, F and G now would mean asserting a
boundary I would have had to invent, which would bake the guess into the test suite where it looks
authoritative. **Deliberately not done.**

No regressions were introduced this pass: no code, schema, config or Railway change was made.
Last full run stands at `apps/workers` **67**, `sports-intel-layer` **1021 passed / 5 failed**
(the known wall-clock rot), `ai-orchestrator` **987**.

---

## 7. Answers to the numbered report items

**1. Root cause** — §1. `record_call` omits `period_start` from its payload, so it is frozen at
row-creation time; and no code reads it anyway, so the guard has no notion of a period. Documented
as a deliberate scope limit in the original migration.

**2. Authoritative allowance-period rule** — **NOT ESTABLISHED.** Allowance *size* is confirmed at
500/month; the *boundary* is not, and I did not invent it. See §2–§3.

**3. Schema / code changes** — **NONE.** Stopped at the audit gate as instructed.

**4. Rollover behaviour** — not implemented. Design recorded in §5.

**5. Historical preservation** — not implemented. The §5 design preserves history by construction
(new row per period) rather than by mutating the existing row.

**6. Concurrency / idempotency proof** — not applicable yet; the intended mechanism (atomic upsert
on a period-keyed unique index, mirroring `increment_odds_api_daily_calls`) is recorded in §5.

**7. Tests / regressions** — none added (§6); none broken (nothing changed).

**8. Current active ledger period** — `period_start = 2026-09-07 02:30:23.554545+00`,
`credits_used_this_period = 276`, `updated_at = 2026-09-16 16:16:22`. **With the caveat that this
is not really a "period"** — it is 9.68 days of lifetime usage since the row was created.

**9. Next expected rollover date** — **CANNOT BE DETERMINED.** This is the finding, not a gap in
the investigation. Candidates are 2026-10-01 (calendar) or an unknown anniversary date. **My
earlier "~2026-10-07" was incorrect and is retracted** (§2).

**10. `cron-news-worker` natural tick** — **NOT AVAILABLE.** Its schedule is `0 */4 * * *`; the
next tick is **20:00 UTC** and the current time is 18:54 UTC. It did not occur during this pass and
was not triggered. Still an observation item.

**11. Are odds economics safe across billing periods?** — **NO, not yet.** Within a single period
they are now well bounded (backoff, 20-call/60-credit daily ceiling, monthly guard at 450, clean
exit-0 pauses). **Across** a period boundary they are not: the guard will trip and stay tripped.
Not urgent — ~2–3 weeks of headroom (§4) — but unresolved, and it needs one answer from the owner.

**12. Ready to set `MASTER_REFRESH_ENABLED=true` permanently?** — **Technically yes; per your own
stated ordering, not yet.** The precise position:

- The two systems are **independent providers**. Master Refresh spends **SportsDataIO** (1
  call/day), which has no credit ledger and is not touched by this defect. Nothing about the odds
  ledger can break the schedule refresh.
- But there is a **real coupling**: the schedule refresh continuously creates new canonical games,
  each of which becomes an odds-polling candidate. Enabling it increases odds spend and therefore
  **moves the trip date closer**.
- Your directive opened with *"Fix the Odds API credit-ledger period rollover before enabling
  additional permanent automation."* That ordering is sound and I would keep it.

**Recommendation: answer the one question in §3, implement §5, then enable.** If you would rather
enable now, it is defensible — but do the manual counter reset (§4) at the same time so the
permanent-block risk is not sitting behind newly increased spend.

---

## What was NOT done

- **Zero provider calls. Zero LLM calls.**
- **No date arithmetic implemented, and no reset cadence invented** — the explicit stop condition.
- **No schema, code, config or Railway change.** `MASTER_REFRESH_ENABLED` still `false`; no cron
  cadence touched.
- **No manual ledger reset performed** — available and recommended as an interim measure, but it is
  a decision about real spend against a real allowance, and it is the owner's to make.
- **`cron-news-worker` not triggered** — its 20:00 UTC tick remains to be observed.
- No unrelated repairs.
