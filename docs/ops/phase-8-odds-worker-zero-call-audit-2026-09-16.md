# Odds Worker — Zero-Call Audit (2026-09-16)

**Directive:** MANSA HQ — "The next autonomy step is the Odds Worker proof. Do not spend
Odds API credits yet. First perform a ZERO-CALL audit… ZERO provider calls. Do not alter
cron configuration. Do not run recommendations. STOP AND REPORT."

**Compliance:** zero provider calls were made by this session. Every finding below comes
from reading code, reading live Railway config/logs, and read-only SQL against dev.
No cron configuration was altered. No recommendations were run. No rows were written.

**Audit window:** 2026-09-16 14:11–14:20 UTC.

---

## Headline: two findings, one of them urgent

1. **Autonomous odds ingestion is already PROVEN.** It does not need a new live proof.
   At 13:00:26 UTC today — 13 minutes after the schedule refresh created the Week 2 games,
   with no manual game input of any kind — the cron picked them up and wrote 162 real odds
   snapshots. Question 7 is answered empirically, not by inference.

2. **The Odds API is bleeding credits right now, and has been since 13:00 UTC.**
   Ten of the sixteen Week 2 games can never record a snapshot, because The Odds API's own
   team names for them have no `team_provider_ids` mapping. A game with no snapshot reads as
   *never polled*, so it is **due on every single tick, forever**. Every tick therefore spends
   a real paid call and persists nothing. Measured burn: **3 credits per tick × 96 ticks/day
   = 288 credits/day, for zero data.** Six ticks have already gone this way (13:16 → 14:16),
   spending 18 credits and persisting 0 rows.

The second finding is the reason the real proof should be cheap and immediate: fixing it is a
zero-call database change, and the fix *is* the remaining proof.

---

## 1. Which Week 2 games are currently considered due for odds collection

All 16 Week 2 games are **candidates** (`_CANDIDATE_WINDOW_DAYS = 7`; the query window
`[today, today+7)` covers every Sep 18–22 kickoff). All 16 classify **FAR** (33.9 h to 129.9 h
to kickoff).

Of those, **10 are due on the current tick** and 6 are throttled. This is confirmed from the
live cron result, not computed: `games_considered: 16, games_due: 10, games_skipped_not_due: 6`
on each of the 13:16, 13:31, 13:45, 14:01 and 14:16 ticks.

| Kickoff (UTC) | Game | Hours out | Odds API event id | Snapshots | Due now? |
|---|---|---|---|---|---|
| 2026-09-18 00:15 | DET @ BUF | 33.9 | `56e88976…` | 27 | no — throttled |
| 2026-09-20 17:00 | CAR @ ATL | 98.7 | **none** | **0** | **YES** |
| 2026-09-20 17:00 | NO @ BAL | 98.7 | **none** | **0** | **YES** |
| 2026-09-20 17:00 | MIN @ CHI | 98.7 | `0283a29e…` | 27 | no — throttled |
| 2026-09-20 17:00 | CIN @ HOU | 98.7 | **none** | **0** | **YES** |
| 2026-09-20 17:00 | PIT @ NE | 98.7 | **none** | **0** | **YES** |
| 2026-09-20 17:00 | GB @ NYJ | 98.7 | **none** | **0** | **YES** |
| 2026-09-20 17:00 | CLE @ TB | 98.7 | **none** | **0** | **YES** |
| 2026-09-20 17:00 | PHI @ TEN | 98.7 | **none** | **0** | **YES** |
| 2026-09-20 20:05 | JAX @ DEN | 101.8 | **none** | **0** | **YES** |
| 2026-09-20 20:05 | LV @ LAC | 101.8 | `71b3b837…` | 27 | no — throttled |
| 2026-09-20 20:25 | SEA @ ARI | 102.1 | `4dd80201…` | 27 | no — throttled |
| 2026-09-20 20:25 | WAS @ DAL | 102.1 | `85ef8509…` | 27 | no — throttled |
| 2026-09-20 20:25 | MIA @ SF | 102.1 | `68bc5590…` | 27 | no — throttled |
| 2026-09-21 00:20 | IND @ KC | 106.0 | **none** | **0** | **YES** |
| 2026-09-22 00:15 | NYG @ LAR | 129.9 | **none** | **0** | **YES** |

The six throttled games all captured at exactly `2026-09-16 13:00:26.369003+00` and are FAR
(86400 s interval), so they are not due again until **2026-09-17 13:00:26**. Correct behaviour.

The ten due games are due for the wrong reason. They are not due because a day has elapsed —
they are due because they have **no history at all**, and they can never acquire any until the
linking gap in §9 is closed. They are permanently due.

Zero Week 2 games are STOPPED; none has kicked off.

---

## 2. The exact kickoff-proximity rules / cadence

One shared policy module, `app/workers/windows.py` — the Odds Worker computes no cadence
numbers of its own, and Player Props Worker uses the identical policy rather than a copy.

**Window boundaries** (`_BOUNDARIES`, evaluated nearest-first on time-to-kickoff):

| Time to kickoff | Window | Poll interval |
|---|---|---|
| ≤ 0 (kicked off) | `STOPPED` | `None` — never polled |
| ≤ 5 min | `RAMP_5M` | 120 s |
| ≤ 15 min | `RAMP_15M` | 300 s |
| ≤ 60 min | `RAMP_60M` | 900 s |
| ≤ 2 h | `RAMP_2H` | 3600 s |
| > 2 h | `FAR` | 86400 s |

**Provenance, stated honestly.** The four boundaries (2 h / 60 m / 15 m / 5 m) are CONFIRMED
from Volume 2 §8's Odds Worker cadence row. The **interval values are ASSUMED** — the module
adopts a boundary-as-interval convention (a window's interval equals the span of the next tier
up) and says so in its own docstring. Volume 2 specifies the ramp shape, not the numbers.
This is recorded here as an outstanding assumption, not presented as blueprint-specified.

**The due rule** (`should_poll`): a game is due when its window has an interval (i.e. is not
`STOPPED`) **and** either `last_polled_at is None` **or** `now - last_polled_at >= interval`.

**Where `last_polled_at` comes from** — this is the crux of the cost finding.
`app/persistence/odds_snapshots.read_last_polled_at()` derives it from the append-only
`odds_snapshots.captured_at` history, keyed by internal `game_id`. There is no separate
poll-state table for odds. A game with zero snapshots is absent from the dict, `.get()` returns
`None`, and `None` means *never polled*, which means **always due**. That is correct and safe
for a game that will eventually persist a snapshot. It is an unbounded paid loop for a game
that structurally cannot.

**This exact failure mode was already known and already defended against — but the defence
does not apply here.** `MANUAL_SEED_MAX_ATTEMPTS = 3` in `odds_worker.py` exists because of a
real 2026-09-07 incident with the same shape: three manually-seeded games that never linked
triggered a paid call on every tick indefinitely. The cap excludes such a game after 3 attempts —
but **only when `games.manual_seed = true`**. The comment is explicit that it is "never applied
to a normal Schedule/Master-Refresh-sourced game… those correctly keep retrying a real,
temporarily-unresolved team mapping forever." Our ten games are Schedule-sourced, so they are
deliberately outside the cap. The judgment behind that was that a Schedule-sourced game's
unresolved mapping is *temporary*. Here it is not temporary — it is a permanent missing row —
so the "forever" in that comment is running literally.

**Post-kickoff:** `STOPPED` means this worker generation never polls after kickoff. In-game
odds are out of scope by design.

---

## 3. How many Odds API requests the next natural worker cycle would make

**Exactly one.**

The worker makes **one bulk discovery call per cycle**, never one per game:
`fetch_odds([])` against The Odds API's bulk `/odds` endpoint, which returns the full slate
regardless of filter. Markets `h2h`/`spreads`/`totals`, regions `us`.

The sequence is: read candidates → classify → if nothing is due, **skip the provider call
entirely** → otherwise one call covers every due game at once.

So request count per cycle is binary: **0 if nothing is due, 1 if anything is due.** Ten games
due and one game due cost the same. Confirmed live — every tick logs a single
`POST /v1/internal/odds-worker/run`, and the credit ledger moves by exactly one call's worth.

The next natural cycle is at **14:31 UTC**, and it will make **1 request**.

---

## 4. Expected credit cost of that cycle

**3 credits.** `CREDITS_PER_CALL = 3` in `app/persistence/odds_api_credit_ledger.py` — three
markets × one region, counted deterministically by the ledger on a genuine round-trip, never
parsed from a vendor header.

**Verified empirically during this audit, not assumed:** the ledger read
`credits_used_this_period = 249` at 14:01:21 and `252` at 14:16:29 — exactly +3 across exactly
one tick.

Ledger state at audit time:

```
provider_name            the_odds_api
credits_used_this_period 252
period_start             2026-09-07 02:30:23 UTC   (9.49 days ago)
updated_at               2026-09-16 14:16:29 UTC
```

**Credits are recorded only for a real round-trip** (`if not response.from_cache`). A ledger
write failure is collected, never raised — it must not block persisting odds a succeeded fetch
already returned.

**The run rate is the problem, not the per-cycle cost.** The `CachingAdapter` is real, but
`run_odds_worker` does `cache_backend = cache_backend or InMemoryCacheBackend()` — constructed
fresh per invocation — and each cron tick is a **new container** (`Starting Container` appears
in the logs on every tick). So the cache can never serve a hit across ticks; it only
de-duplicates within a single run, where there is only one call anyway. Every tick with
anything due is a real paid call.

Projected: **12 credits/hour, 288 credits/day**, for as long as the ten games stay unlinked.
Since 13:16 UTC: 6 ticks, 18 credits, **0 rows persisted**.

---

## 5. Current credit guard / trip threshold behaviour

`_check_credit_guard()` in `app/workers/odds_worker.py`:

- Reads `THE_ODDS_API_MONTHLY_CREDIT_BUDGET` and `THE_ODDS_API_MIN_REMAINING_CREDITS`.
- **Fails OPEN if either is unset.** Neither is ever defaulted to an invented number — an
  unset budget means "guard not configured," and the worker makes that an explicit, disclosed
  no-op rather than a silent one.
- Once both are set, **fails CLOSED** the moment `budget - credits_used <= floor`.
- Computed from this project's own deterministic call-counting ledger, **never** from a parsed
  vendor header.
- Checked **after** due-selection and **before** the provider call — so a guard-skip is a
  distinct, named outcome (`status="skipped_credit_guard"`) rather than being confused with
  "nothing was due."

**Live state: the guard IS armed.** Both `THE_ODDS_API_MONTHLY_CREDIT_BUDGET` and
`THE_ODDS_API_MIN_REMAINING_CREDITS` are present on `sports-intel-layer` in dev. The Railway
MCP connection returns variable **names only** for this session (`valuesRedacted: true`), so
**I cannot read the numeric budget or floor, and I am not going to guess them.**

**This is a live risk worth naming.** Used is 252 and rising at 288/day. Whatever the budget is,
the bleed is consuming it roughly 96× faster than the useful workload would, and if it trips
the guard before Sunday the worker will return `skipped_credit_guard` and **stop collecting odds
for the Week 2 slate entirely** — the guard doing exactly its job, on a bill it should never have
had to absorb. If HQ can supply or confirm the budget/floor values, the time-to-trip is a one-line
calculation; without them I can state the rate but not the deadline.

---

## 6. Is the existing `cron-odds-worker` on dev and healthy?

**Yes on both counts, with one structural caveat that turns out not to matter.**

| Property | Value |
|---|---|
| Service id | `04b53e11-e8bf-40ad-9e07-15f465ced2ee` |
| Environment | **dev** (`5c1e630f-…`) |
| Source | `ThePlaybook-sys/ThePlaybook`, branch **`dev`**, root `apps/workers` |
| Start command | `python -m app.cron_dispatch` |
| Cron schedule | `*/15 * * * *` |
| Restart policy | `NEVER` (correct for a finite job) |
| Public domain | none |
| Variables | `CRON_DISPATCH_BASE_URL`, `CRON_DISPATCH_TARGET`, `INTERNAL_SERVICE_TOKEN` |
| Active deployment | `a1a606e3`, **SUCCESS**, updated 14:16:33 UTC today |

Health is not inferred from config — it is observed. Every quarter-hour tick in the audit
window started a container, resolved the target, got `HTTP/1.1 200 OK`, logged
`cron_dispatch succeeded`, and exited cleanly. Six consecutive healthy ticks: 12:30, 12:45,
13:00, 13:16, 13:31, 13:45, 14:01, 14:16.

Target and base URL resolve correctly:
`target=odds-worker base_url=https://sports-intel-layer-dev.up.railway.app` →
`POST /v1/internal/odds-worker/run`.

**The `INFO` lines are logged at Railway severity `error`.** That is stderr routing, not a
failure — the payloads read `cron_dispatch succeeded`. Worth knowing before anyone builds an
alert on log severity for this service.

The consumer is healthy too: `sports-intel-layer` dev deployment `e5f5f2b9` is **SUCCESS** on
commit `84c6892` — the current head of `dev`, including today's venue alias fix.

---

## 7. Will it automatically begin polling Week 2 with no manual game input?

**Yes — and it already did. This is observed fact, not a prediction.**

The timeline from the live cron logs:

| Tick | Result |
|---|---|
| 12:30:54 | `games_considered: 0` — Week 2 games did not exist yet |
| 12:45:45 | `games_considered: 0` — the schedule refresh ran at 12:45:52, seconds *after* this tick |
| **13:00:14** | **`games_considered: 16, games_due: 16, lines_persisted: 162, newly_linked: 12`** |
| 13:16 onward | `games_considered: 16, games_due: 10, games_skipped_not_due: 6, lines_persisted: 0` |

Nobody seeded a game, named a matchup, or touched the odds worker. The schedule refresh created
canonical Week 2 rows at 12:47, and **the very next odds tick found them, fetched the slate,
linked 12 events and wrote 162 snapshots**. That is the autonomy claim, satisfied end to end,
at a cost of 3 credits.

The mechanism is that the worker only ever *reads* `games` via `list_games_in_window` — the same
read-only helper Master Refresh uses. It never creates or updates a game. Decision 1's ownership
boundary holds: Master Refresh makes zero Odds calls, and the Odds Worker makes zero schedule
writes. The handoff between them is the database, and it worked untouched.

The 13:16 drop from 16 due to 10 due is also the cadence proving itself: the six games that
successfully captured at 13:00 became correctly throttled for 24 hours.

---

## 8. Could any stale branch / config issue prevent that?

**No — but the reason is worth recording, because the service genuinely looks stale.**

Two things about `cron-odds-worker` look like staleness and are not:

**(a) `watchPatterns: ["__gate_b_frozen__/do-not-match-anything/**"]`** — a deliberate freeze
pattern that matches nothing. Every dev push to this service shows `SKIPPED`.

**(b) The active deployment is from 2026-09-07**, nine days old, on commit `6bca087f`, while
`dev` head is `84c6892`. `apps/workers` has genuinely moved since: `cron_dispatch.py` has
+68 lines across five commits, including the `canonical-finalization` and `schedule-refresh`
targets added this week.

Neither blocks odds ingestion, for a structural reason: **`cron-odds-worker` is a dispatcher,
not the worker.** It runs `python -m app.cron_dispatch`, whose entire job is to POST
`/v1/internal/odds-worker/run` on `sports-intel-layer`. All odds logic — cadence, credit guard,
linking, persistence — lives in `sports-intel-layer`, which **is** current (deployment
`e5f5f2b9`, commit `84c6892`, SUCCESS). The dispatcher's `odds-worker` target has existed since
before `6bca087f` and has not changed. A frozen dispatcher pointing at a live consumer is not
stale in any way that affects behaviour, and the 200 OKs prove the deployed dispatcher resolves
the target correctly.

**It becomes stale the moment anything the odds path needs is added to `apps/workers`.** It will
not pick up a new dispatch target, a retry policy change, or a timeout change until it is rebuilt.
The rebuild mechanism is itself a known trap, recorded on this exact service: the commit message
on `6bca087f` says a comment-only touch was needed because *"Railway's own path-based skip logic,
not the watchPatterns freeze, was the actual reason recent pushes produced a SKIPPED (no-build)
deployment."* Both mechanisms are in play. Not changed here — the directive forbids altering cron
configuration, and nothing in the odds path currently needs it.

**One real config-adjacent issue, out of scope but noted:** `cron-master-refresh` remains on stale
branch `claude/new-session-fqsad5` with an invalid sentinel target and CRASHes daily. Untouched
per standing directive. It does not touch the odds path.

---

## 9. Is the existing provider mapping sufficient for all Week 2 games?

**No. This is the root cause, and it is precise.**

`team_provider_ids` holds **17** `the_odds_api` rows against **32** canonical teams. All 32
canonical `teams` rows exist — the gap is purely in the provider mapping layer.

**The 15 missing teams are exactly the 15 named in the live unresolved log**, with no
discrepancy in either direction:

> Atlanta Falcons · Carolina Panthers · Cincinnati Bengals · Cleveland Browns · Denver Broncos ·
> Houston Texans · Indianapolis Colts · Jacksonville Jaguars · Los Angeles Rams ·
> New Orleans Saints · New York Giants · New York Jets · Pittsburgh Steelers ·
> Tampa Bay Buccaneers · Tennessee Titans

17 + 15 = 32. The arithmetic closes exactly, the same way the 271/272 audit did.

**Why this blocks ingestion.** `odds_game_linking` resolves an event through
*The Odds API team string → `team_provider_ids` → canonical `teams.id` → SportsDataIO abbreviation →
candidate game → kickoff validation → `games.id`*, with **no fuzzy matching, ever**. The first hop
fails, so the event is classified `unknown team` and reported unresolved — never guessed, never
paired with a nearest candidate, never allowed to create a game. That is the correct and desirable
behaviour; the data is what is missing, not the logic.

The 20 unresolved events logged on every tick are the away/home halves of the ten affected games
plus their Week 3 counterparts in the same bulk response.

**Why the gap exists, and why it is not a bug.** Migration `20260814050000` is explicit: the
`the_odds_api` mapping set was seeded **only** from teams confirmed by real fixture evidence
(BAL, BUF, DAL, KC, PHI, SF at the time), because of the standing instruction not to fabricate
provider identifiers. It records that "26 teams have zero The Odds API fixture evidence — reported
to Mac as unverified rather than filled in from general knowledge." Nine more were added as
evidence arrived. The discipline was followed correctly; the consequence is that Week 2 arrived
before the evidence did.

**What has changed is that the evidence now exists.** Today's 13:00 production response emitted
all 15 missing strings verbatim, and every one is an exact match for an existing canonical
`teams.name`. The 17 rows already present follow the identical pattern — `the_odds_api`'s
`provider_team_id` *is* the full team name (`"Baltimore Ravens" → Baltimore Ravens`), not an
opaque vendor id. So the 15 rows can be created from observed provider output rather than from
general knowledge. That distinction is the whole point of the no-fabrication rule, and it is
satisfied — but the source is a Railway log line rather than a persisted fixture, so **HQ should
decide whether that clears the bar** before the rows are written. I am not writing them on my
own authority.

---

## 10. The smallest bounded live proof of autonomous odds ingestion

**First, the honest framing: the headline proof is already banked.** Question 7 shows the cron
autonomously discovering brand-new canonical games and persisting 162 real odds snapshots with no
manual input. Spending credits to re-demonstrate that would be buying something already owned.

What is *not* yet proven is that **all sixteen** Week 2 games ingest — and that the credit bleed
stops. Those are the same event, which makes the proof cheap.

### Proposed proof — 1 request, 3 credits, no config change

**Step 1 — zero-call fix (needs authorization; this is a DB write).**
Insert the 15 missing `team_provider_ids` rows for `the_odds_api`, each
`provider_team_id` taken verbatim from today's production response and joined to the canonical
`teams.name` it matches exactly. No provider call. No schema change. Reversible by deleting 15
rows. Per §9, HQ should confirm that log-observed provider output clears the no-fabrication bar.

**Step 2 — change nothing else.** Do not touch the cron, the schedule, the cadence, the credit
guard, or `MASTER_REFRESH_ENABLED`. The proof is that the *existing, unmodified* automation
handles it.

**Step 3 — let exactly ONE natural `*/15` tick run.** No manual invocation, no forced deployment.
The next tick fires within 15 minutes on its own.

**Expected result, stated in advance so it can falsify:**

| Metric | Expected |
|---|---|
| Odds API requests | **1** |
| Credits | **3** |
| `games_considered` | 16 |
| `games_due` | 10 |
| `newly_linked` | 10 |
| `unresolved_events` | **`[]`** |
| `lines_persisted` | > 0 (~270 if the ratio from the 6 mapped games holds) |
| Week 2 games with ≥ 1 snapshot afterwards | **16 / 16** |

**Step 4 — the second half of the proof costs nothing at all.** Observe the *following* tick.
With all 16 games holding a capture and all classified FAR (86400 s), the expected result is
`games_due: 0`, **no provider call, and no ledger movement**. That single observation
simultaneously proves the cadence throttle works on the full slate and that the 288/day bleed is
closed — and it is free, because the correct behaviour is to make no call.

**Total bounded cost: 1 request, 3 credits, two ticks, ~30 minutes.** Nothing to revert but 15
database rows.

**What it does not prove, stated plainly:** it exercises only the FAR tier. The RAMP_2H → RAMP_5M
ladder cannot be observed until a game is genuinely within two hours of kickoff — first real
opportunity is **DET @ BUF, Thursday 2026-09-18 22:15 UTC**. That is a separate, later, and
naturally-occurring proof, and it should not be simulated by moving clocks or rescheduling crons.

### If HQ prefers to spend nothing at all

Doing nothing is a coherent option, but it is **not free** — it costs 288 credits/day for zero
data and risks tripping the credit guard before Sunday's slate (§5). If credits are the binding
constraint, the cheaper move is the opposite of waiting: do Step 1, and additionally pause the
cron until Saturday. That stops the bleed immediately at zero credit cost. It would require
altering cron configuration, which this directive forbids, so it is raised for decision rather
than done.

---

## What was NOT done

- **Zero provider calls** of any kind — no Odds API, no SportsDataIO, no MSF, no LLM.
- **No cron configuration altered.** `cron-odds-worker` untouched (`*/15`, dev, target
  `odds-worker`). `cron-schedule-refresh` untouched (`0 9 * * *`). `cron-master-refresh`
  untouched (still stale-branch + sentinel).
- **No recommendations run.**
- **No database writes.** The 15 `team_provider_ids` rows are proposed, not inserted.
- **No code changes.** The `InMemoryCacheBackend`-per-invocation finding and the
  `MANUAL_SEED_MAX_ATTEMPTS` scope finding are reported, not fixed.
- **`MASTER_REFRESH_ENABLED` remains `false`.** GameKey `202610902` (CIN @ ATL, Week 9) is still
  absent; the season is still 271. Per directive, no Schedule refresh was run to recover it.

## Outstanding items for HQ

1. **Authorize the 15 `team_provider_ids` rows** (§9/§10 Step 1) — or rule that log-observed
   provider strings do not clear the no-fabrication bar, in which case the ten games stay unlinked
   and the bleed continues until a fixture-backed source exists.
2. **Supply or confirm `THE_ODDS_API_MONTHLY_CREDIT_BUDGET` / `_MIN_REMAINING_CREDITS`** so
   time-to-trip can be calculated rather than left open (§5).
3. **Decide on the bleed** if Step 1 is declined: leave it running, or authorize a cron pause.
4. **Note for a later pass, not now:** the cadence *interval* values in `windows.py` are an
   assumed boundary-as-interval convention, not blueprint-specified (§2), and
   `MANUAL_SEED_MAX_ATTEMPTS` deliberately does not cover Schedule-sourced games whose mapping
   gap is permanent rather than transient (§2). Both are recorded as known, not fixed.
