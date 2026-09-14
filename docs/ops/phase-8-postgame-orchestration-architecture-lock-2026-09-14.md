# Postgame Orchestration Architecture Lock (2026-09-14)

MANSA HQ directive: "POSTGAME ORCHESTRATION ARCHITECTURE LOCK." Locks the
operational lessons from today's MSF dispatcher 502 incident and its
hardening into the permanent Blueprint, audits `cron-master-refresh`'s
disabled state, defines (not builds) an observability contract, records
existing debt, and checks status on tonight's DEN@KC forward-looking
proof. **No provider calls made in this pass. No code built** (the
disabled-cron design and observability contract are both documented,
smallest-next-step proposals, per HQ's explicit "do not build a large
system yet" instruction).

## 1. Architecture lock created

**Volume 2 → v5.5 (MINOR)**, `docs/blueprint/volume-2-system-architecture.md`:

- **§1.1, new Principle #11**: "Any synchronous cron-triggered HTTP
  endpoint must have a bounded workload that fits comfortably inside the
  shortest transport/proxy timeout in its execution path. Private
  networking is not permission to allow unbounded synchronous work."
- **§8, new note**: the MSF Postgame Dispatcher instance this principle
  generalizes from — the real 502 incident, the real fix
  (`MAX_GAMES_PER_DISPATCH_TICK` 4→2 plus the private-networking switch,
  both already applied and verified live in the prior pass today), and
  an explicit statement that per-game durable state, idempotent atomic
  claims, the `validated`-state resume checkpoint, and terminal-game
  exclusion were all preserved unchanged.
- **§8, new note**: the `cron-master-refresh` disabled-cron audit
  (Section 2 below) and recommended design (Section 3 below).
- **§9, new note**: the five-case cron/dispatcher outcome contract
  (Section 4 below).

Full four-field CHANGELOG entry recorded (`CHANGELOG.md`, "v5.5 (Volume
2) — 2026-09-14"). No other volume touched — this is scoped entirely to
system-architecture/DevOps principle and precedent, not product, schema,
or AI-committee decisions.

## 2. `cron-master-refresh` audit

**Currently disabled, deliberately, and the reason still holds.**

- **What it would call**: `POST /v1/internal/master-refresh/run`
  (`sports-intel-layer`) — Master Refresh's own schedule-refresh/game-
  identity/`daily_game_intelligence`-assembly cycle, which requires a
  real SportsDataIO Schedule API call (Volume 2 §8's Master Refresh row).
- **Why disabled**: the Pre-Phase-6 Operational Readiness Gate
  (2026-08-27) deliberately reserved SportsDataIO's Free Trial's last
  call (**11 of 12 spent**) rather than let an unattended daily cron
  spend it — confirmed still true today, live: `credits_used`/budget
  language across every subsequent PROGRESS.md entry through
  2026-09-13 states "11/12 used, final call still reserved and
  untouched," and no entry anywhere authorizes spending it.
- **Expected provider cost of re-enabling**: exactly the one remaining
  reserved SportsDataIO Free Trial call, spent on the very next `0 6 * *
  *` UTC tick after re-enabling (the endpoint has no additional guard
  once its own cron fires and its `CRON_DISPATCH_TARGET` is valid).
- **Does the reason still apply?** Yes — no new SportsDataIO
  authorization, purchase decision, or subscription change has occurred
  since 2026-08-27. **Not re-enabled in this pass, exactly as
  instructed.**
- **Real mechanism, found via live logs, not assumed**: `CRON_DISPATCH_
  TARGET` on this service is literally set to
  `"master-refresh-DISABLED-pending-authorization"` — an intentionally
  invalid sentinel value. `cron_dispatch.py`'s own target-validation
  raises `CronDispatchError: unknown CRON_DISPATCH_TARGET=...` for it,
  **before any network call** — confirmed via this morning's real deploy
  log (2026-09-14 06:03:50 UTC, the service's own daily scheduled tick):
  ```
  cron_dispatch starting target=master-refresh-DISABLED-pending-authorization ...
  ERROR cron_dispatch failed target=master-refresh-DISABLED-pending-authorization
    error=unknown CRON_DISPATCH_TARGET='master-refresh-DISABLED-pending-authorization';
    expected one of ['adaptive-weighting', 'master-refresh', 'postgame-grading', 'recommendation-worker']
  ```
  This is real defense-in-depth, not a guess: the genuine Railway
  `cronSchedule` (`0 6 * * *`) is intentionally left in place (an earlier
  2026-08-27 attempt at `cronSchedule: null` was found, the same day, to
  do the *opposite* of disabling — Railway's own documentation states
  this makes a service "run continuously" — corrected same-day to this
  two-layer design). The application-level target guard, not the Railway
  schedule, is what actually prevents the call.

## 3. Recommended disabled-cron design (documented, not built)

**The real cost of today's mechanism**: it works correctly (zero real
provider calls have leaked since 2026-08-27, confirmed), but Railway has
no visibility into *why* the tick exited non-zero — every single day, at
06:03 UTC, `cron-master-refresh` reports **CRASHED**, indistinguishable
from the platform's own health view alone from a genuine failure. This is
the same underlying gap as the 502 incident, from the opposite direction:
one case misreports a real success as a failure; this case misreports a
deliberate no-op as a failure.

**Recommended fix** (a `cron_dispatch.py` change, not built this pass):
add a dedicated sentinel target name — e.g. `"disabled"` — distinct from
an *unknown/misconfigured* target, that `_run()` recognizes and exits `0`
for, logging a clear "intentionally disabled, no-op" message instead of
raising through the existing unknown-target `CronDispatchError` path. The
mechanism stays identical (one env var on one service); only the
reporting semantics change — a deliberate no-op should report success,
not borrow the accidental-misconfiguration error path as an intentional
kill switch. `master-refresh-DISABLED-pending-authorization` would become
literally `disabled` (or similar), keeping the same "clearly not a real
target name" self-documentation the current value already provides.

## 4. Observability contract (documented, not built)

Five outcomes a cron tick can have, in order of urgency:

1. **Origin processing failure** — the endpoint's own handler genuinely
   errored. Needs investigation.
2. **Transport/proxy timeout** — the client saw a non-2xx/connection
   failure, but the origin's own durable state shows real completion
   (today's 502 pattern). Needs the §1.1 principle #11 workload-sizing
   fix, not investigation.
3. **Intentional disabled state** — fires on schedule by design, does
   nothing by design (`cron-master-refresh`). Should never alert as a
   failure.
4. **Successful empty tick** — ran correctly, genuinely nothing to do
   (`considered: 0`, `"no_candidates"`, `"no_eligible_run"` — all already
   real, existing response shapes). Already distinguishable from failure
   in the endpoint's own response body.
5. **Successful processing tick** — ran correctly, did real work.

**What already exists**: every `/v1/internal/*/run` endpoint already
returns a typed body distinguishing (3)/(4)/(5) — no change needed there.
**What's missing**: (1) vs (2) at the dispatcher layer, where both
currently look identical to `cron_dispatch.py` (a non-2xx or transport
exception). **Smallest future implementation identified**: classify at
the existing `dispatch()` call site — a transport-level exception or a
non-2xx with no parseable body is case 2 evidence (the endpoint never got
to return its own outcome); a non-2xx *with* a parseable typed error body
is case 1. No new service, table, or dashboard. **Not built this pass**,
per HQ's explicit instruction — deferred until a second real incident
confirms this is worth building ahead of, not spec'd speculatively.

## 5. Existing debt (recorded, not fixed)

- **5 pre-existing, unrelated `test_odds_cadence_persistence.py`
  failures** — found during today's dispatcher-hardening pass, confirmed
  via stash-and-retest to predate that change entirely (identical
  failures with the dispatcher edit reverted). Not investigated further
  or fixed — out of every pass's scope so far.
- **Stale PROGRESS.md statements, already known and previously flagged**:
  the file's own top "Current Phase"/Phase 7 checklist headers (lines 3,
  80) still read "7.1+ NOT AUTHORIZED"/"GATE B BLOCKED ON CREDENTIAL,"
  stale against the same file's own later entries (Milestone 7.1
  authorized-and-built; `THE_ODDS_API_KEY` confirmed live). First flagged
  in the 2026-09-13 Phase 7 Real History Observation Window report, still
  unfixed — recorded again here so it isn't lost between passes. **No
  fresh full-document staleness audit was performed this pass** (out of
  scope, "no unrelated cleanup").
- **Canonical final-score/status reconciliation debt**: `games.status`/
  `.final_score`/`.finalized_at` remain permanently stale for every MSF-
  ingested game (e.g. SF@LAR still reads `status='live'`,
  `final_score=null` despite `game_postgame_ingestion_state.state
  ='confirmed_complete'`) — by design, not a bug: the MSF pipeline never
  writes those columns, which belong to SportsDataIO's separate
  `postgame_worker.py` pipeline (Volume 2 §8's own Postgame Ingestion
  Worker row). First disclosed in the SF@LAR Live Proof report
  (2026-09-13); real, unresolved architectural debt — two independent
  provider pipelines each own a different half of "is this game over,"
  with no reconciliation step joining them. Not addressed this pass.
- **New debt found this pass, not previously recorded: no automatic
  new-game discovery for MSF postgame ingestion.** `select_due_msf_
  postgame_games` (the dispatcher's own selection query) only ever reads
  *existing* `game_postgame_ingestion_state` rows — nothing in the
  current system automatically creates that first `scheduled` row for a
  newly-relevant game. Every row that exists today (the 13 Sunday games,
  SF@LAR) was created by a one-time, manually-authorized SQL
  initialization in an earlier pass, not a self-sustaining mechanism.
  Directly relevant to Section 6 below.

## 6. DEN@KC — status, and a real blocker found before the game even starts

DEN@KC is real and confirmed: canonical game `32764b10-a983-45b4-b36c-
7f3962ce01ca`, kickoff **2026-09-15 00:15 UTC (Monday Night Football,
8:15 PM ET tonight)**, MSF game id `163556` already mapped.

**Live-checked now, before waiting for the game**: `game_postgame_
ingestion_state` has **no row at all** for this game
(`ingestion_state: null`). Per Section 5's newly-found debt item, nothing
in the current automatic pipeline will ever create one — the dispatcher's
own selection query cannot select a game it has no row for, no matter how
long the schedule keeps firing. **As built today, "observe whether the
normal cron discovers it automatically" will resolve to "no" by
construction, not because of a bug in tonight's specific run** — this is
true right now, independent of whether DEN@KC ever kicks off or finishes.

This was not fixed or worked around in this pass (creating the row myself
would be exactly the kind of manual intervention the directive's "do not
manually invoke ingestion" instruction rules out, and building an actual
auto-discovery mechanism is a real code change outside this pass's
documentation-lock scope). **Flagged for an explicit decision** rather
than silently defaulting to either "do nothing, DEN@KC goes untracked" or
"quietly initialize the row" — both are legitimate choices, but this pass
makes neither without HQ's steer, since either one changes what "the
normal cron discovers it automatically" actually gets to prove tonight.

## 7. Is there enough evidence for the MSF subscription decision?

**Yes — Sunday's real 13-game recovery is already strong, sufficient
evidence on its own**, independent of whether DEN@KC additionally
succeeds:

- **Real scale**: 13 real games in one slate, not one synthetic/single-
  game proof.
- **Real identity resolution at scale**: 1,213 real players, numeric-
  first team resolution, 0 quarantines, 0 misresolutions.
- **Real failure-mode coverage**: the pipeline was directly proven safe
  under a genuine transport-layer failure (the 502 incident) — data
  integrity held with zero duplicates/corruption even before the fix
  existed, and the fix itself was verified live afterward.
- **Real cost/call discipline proven**: exactly 13 real MSF calls for 13
  real games (1:1, no waste, no retries beyond policy), the durable
  per-game hard cap (4) and cache/rate-limit-aware scheduling all
  unexercised-but-intact (no game needed them this slate, but none were
  bypassed either).
- **Real operational proof**: the permanent dispatcher mechanism itself
  (not a diagnostic, not a manual trigger) is what did all of this —
  confirmed still scheduled and firing on its own as of the most recent
  natural tick.

DEN@KC, if it could run, would add one more data point (a different
night, a single game, exercised only through the already-hardened path)
— genuinely useful confirmation, but not load-bearing for the decision
the way the 13-game Sunday result already is. **Recommendation: the
Sunday evidence alone is sufficient to make the MSF subscription
decision now; DEN@KC's outcome (once Section 6 is resolved one way or
the other) is confirmatory, not a precondition.**

## Out of scope, exactly as instructed

No Context Intelligence. No recommendation work. No unrelated cleanup
(the 5 odds-cadence failures and the stale PROGRESS.md header were
recorded, not fixed; no full staleness re-audit performed). No provider
calls outside normal, already-authorized automation. `cron-master-
refresh` not re-enabled. No code built for the disabled-cron sentinel or
the observability contract — both documented as the smallest identified
next step only.
