# Odds Team Identity Repair + Autonomous Proof (2026-09-16)

**Directive:** MANSA HQ — "ODDS TEAM IDENTITY REPAIR + AUTONOMOUS PROOF." The 15 missing
`the_odds_api` team mappings authorized as provider evidence. No manual provider call. Observe
the next natural tick only, then one more.

**Result: both predicted outcomes occurred, and the credit leak is CLOSED — confirmed across
two consecutive zero-call ticks, not one.**

---

## Timeline

| Time (UTC) | Event |
|---|---|
| 16:03:59 | Baseline frozen after the mapping write, before any tick |
| 16:16:21 | **Tick 1** — natural `*/15` cron tick |
| 16:30:41 | **Tick 2** — natural tick, the bleed-closed proof |
| 16:45:55 | **Tick 3** — unrequested bonus confirmation, identical to tick 2 |
| 16:58:08 | Final verification read |

No manual invocation. No cadence change. No cron configuration touched.

---

## 1. Mappings inserted

**15 rows**, exactly the 15 authorized, via migration
`supabase/migrations/20260916160500_the_odds_api_team_identity_repair.sql`.

Atlanta Falcons · Carolina Panthers · Cincinnati Bengals · Cleveland Browns · Denver Broncos ·
Houston Texans · Indianapolis Colts · Jacksonville Jaguars · Los Angeles Rams ·
New Orleans Saints · New York Giants · New York Jets · Pittsburgh Steelers ·
Tampa Bay Buccaneers · Tennessee Titans

### Provenance, recorded as required

The provider identifiers were transcribed from a real production response, not recalled:

> **Railway deploy log** — service `cron-odds-worker`
> (`04b53e11-e8bf-40ad-9e07-15f465ced2ee`), environment **dev**
> (`5c1e630f-f4b7-4d99-933a-231bf1aaca91`), deployment
> `a1a606e3-8526-45c9-b8a2-f58935474c57`, **cron tick of 2026-09-16 13:00:26 UTC**, repeated
> identically on every subsequent tick through 16:01:37 UTC.

The worker's own `unresolved_events` payload named each one, in the form:

```
aee7eae1849ebb103b9bf233e9741392: unknown team(s), no team_provider_ids mapping:
  ['Atlanta Falcons', 'Carolina Panthers']
```

Those bracketed strings **are** The Odds API's own `home_team` / `away_team` field values,
carried through `app/persistence/odds_game_linking.py` untransformed. The full provenance
statement lives in the migration header, so it travels with the rows rather than only with
this report.

### Why the join is exact identity, not fuzzy matching

For this provider `provider_team_id` **is** the full team name — the vendor's own identifier
scheme, not a display label being parsed. All 17 pre-existing rows follow the identical pattern
(`"Baltimore Ravens"` → Baltimore Ravens). The insert joins on `t.name = mapping.provider_team_id`:
plain string equality, **no normalization, no casefolding, no whitespace handling, no
abbreviation inference, no nearest-match**. A string that failed to match exactly would have
inserted nothing rather than resolve to something close.

Constraint `unique(provider_name, provider_team_id)` — the collision guard preserved by the
2026-09-11 multi-identifier widening — was relied on, not bypassed: the insert carries
`on conflict (provider_name, provider_team_id) do nothing` plus a `not exists` guard preventing
any team that already holds a `the_odds_api` identity from gaining a second one.

---

## 2. Team identity coverage: 32/32

Verified after the write:

| Check | Result |
|---|---|
| `the_odds_api` mappings | **32** |
| Canonical teams | **32** |
| Teams still unmapped | **0** |
| Duplicate `provider_team_id` values | **0** |
| Teams carrying more than one `the_odds_api` identity | **0** |
| Rows where `provider_team_id` ≠ canonical `teams.name` | **0** |

17 existing + 15 new = 32/32. The arithmetic closes exactly.

---

## 3. Conflicts and ambiguities: none

Checked **before** writing, per row, all 15. Every row had to clear three tests:

| Test | Result across all 15 |
|---|---|
| Exactly 1 canonical team matches the string exactly (never 0, never >1) | **15/15 = 1** |
| `provider_team_id` not already taken by another team | **15/15 = 0 taken** |
| Canonical team holds no conflicting `the_odds_api` identity | **15/15 = 0 conflicts** |

**Zero conflicts. Zero ambiguities. Nothing was skipped, because nothing needed to be.** Had any
row failed any test it would have been left out and reported rather than guessed.

---

## 4. First natural tick — 16:16:21 UTC

```
status: 'success'          (was 'partial' on every tick since 13:00)
games_considered: 16
games_due: 10
games_skipped_not_due: 6
lines_persisted: 266
newly_linked: 20
unresolved_events: []
failures: []
error: None
```

**Every prediction held.** Side by side:

| Metric | Predicted | Actual | |
|---|---|---|---|
| `games_considered` | 16 | **16** | ✅ |
| `games_due` | 10 | **10** | ✅ |
| Odds API requests | 1 | **1** | ✅ |
| Credits | 3 | **3** | ✅ |
| `newly_linked` | ~10 | **20** | ✅ over-delivered |
| `unresolved_events` | `[]` | **`[]`** | ✅ |
| Week 2 snapshot coverage | 16/16 | **16/16** | ✅ |

**`newly_linked` came in at 20, not 10 — and the extra 10 are explained, not anomalous.** The
linking step operates on every event in the bulk response, while persistence is restricted to
the due set. So:

| Week | Games newly mapped at 16:16 | Lines persisted |
|---|---|---|
| 2 | 10 | **266** |
| 3 | 10 | **0** |

Week 3 kickoffs (Sep 25 00:15 → Sep 28 00:20) sit outside the 7-day candidate window
`[Sep 16, Sep 23)`, so those games were never due and correctly persisted nothing — but they are
now **identity-resolved in advance**, before they enter the polling window on Sep 19. No future
tick will spend a cycle rediscovering them.

The ten event ids linked are exactly the ten that appeared in `unresolved_events` on every prior
tick — `aee7eae1…` (CAR@ATL), `2143ade9…` (NO@BAL), `36ad2fa7…` (CIN@HOU), `9d14f876…` (PIT@NE),
`4aeee070…` (GB@NYJ), `0636ebff…` (CLE@TB), `fafc649c…` (PHI@TEN), `1fd6628c…` (JAX@DEN),
`50bc2470…` (IND@KC), `32367f88…` (NYG@LAR). The events that could not resolve are precisely the
events that now do.

---

## 5. Actual Odds API request count

**Tick 1: exactly 1. Tick 2: exactly 0. Tick 3: exactly 0.**

One bulk `fetch_odds([])` covering all ten due games at once — the worker never issues one
request per game.

Ticks 2 and 3 made **no request at all**: with `games_due: 0`, `run_odds_worker` returns before
the credit guard and before the provider call is ever constructed. Zero is structural here, not
incidental.

---

## 6. Actual credit cost

**Tick 1: 3 credits. Tick 2: 0. Tick 3: 0.**

| Reading | Credits | Ledger `updated_at` |
|---|---|---|
| Baseline, 16:03:59 | 273 | 16:01:37 |
| After tick 1, 16:18:22 | **276** (+3) | **16:16:22** |
| After ticks 2 and 3, 16:58:08 | **276** (+0) | **16:16:22** — unmoved |

**Total cost of this entire proof: 3 credits.**

---

## 7. Snapshots persisted

**266 rows on tick 1. Zero since.**

`odds_snapshots` went 1420 → **1686**. The arithmetic closes exactly against the per-game counts:
8 games × 27 + IND@KC 26 + NYG@LAR 24 = **266**. (The two short counts reflect fewer books quoting
those games, not a partial write.)

Rows captured after 16:17:00 UTC: **0** — ticks 2 and 3 wrote nothing, as intended.

---

## 8. Unresolved events

**`[]` — empty on tick 1, tick 2 and tick 3.**

Down from 20 unresolved events on every tick between 13:00 and 16:01. `status` moved from
`partial` to `success` as a direct consequence.

---

## 9. Week 2 snapshot coverage: 16/16

All sixteen games are now both mapped and captured.

| Kickoff (UTC) | Game | Snapshots | Last capture |
|---|---|---|---|
| Sep 18 00:15 | DET @ BUF | 27 | 13:00:26 |
| Sep 20 17:00 | CAR @ ATL | 27 | **16:16:32** |
| Sep 20 17:00 | NO @ BAL | 27 | **16:16:32** |
| Sep 20 17:00 | MIN @ CHI | 27 | 13:00:26 |
| Sep 20 17:00 | CIN @ HOU | 27 | **16:16:32** |
| Sep 20 17:00 | PIT @ NE | 27 | **16:16:32** |
| Sep 20 17:00 | GB @ NYJ | 27 | **16:16:32** |
| Sep 20 17:00 | CLE @ TB | 27 | **16:16:32** |
| Sep 20 17:00 | PHI @ TEN | 27 | **16:16:32** |
| Sep 20 20:05 | JAX @ DEN | 27 | **16:16:32** |
| Sep 20 20:05 | LV @ LAC | 27 | 13:00:26 |
| Sep 20 20:25 | SEA @ ARI | 27 | 13:00:26 |
| Sep 20 20:25 | WAS @ DAL | 27 | 13:00:26 |
| Sep 20 20:25 | MIA @ SF | 27 | 13:00:26 |
| Sep 21 00:20 | IND @ KC | 26 | **16:16:32** |
| Sep 22 00:15 | NYG @ LAR | 24 | **16:16:32** |

**16/16 mapped. 16/16 with snapshots. Zero games with a null event id.**
`the_odds_api` game mappings went 24 → **44**.

---

## 10. Second natural tick — 16:30:41 UTC

```
status: 'success'
games_considered: 16
games_due: 0
games_skipped_not_due: 16
lines_persisted: 0
newly_linked: 0
unresolved_events: []
failures: []
```

**Exactly as predicted.** And a third tick at 16:45:55 returned byte-identical numbers — an
unrequested second confirmation that the zero-due state is stable, not a one-off.

All sixteen games now hold a capture and all classify FAR (86400 s), so none is due again until
**2026-09-17 13:00:26** (the six from the earlier tick) and **2026-09-17 16:16:32** (the ten from
tick 1).

---

## 11. Did the credit ledger stay unchanged on tick 2?

**Yes — and on tick 3 as well.**

`credits_used_this_period` has read **276** continuously since 16:16:22, and the ledger's own
`updated_at` is still **16:16:22** — it has not been written since tick 1. That is stronger than
the value merely being equal: the row was not touched at all.

`odds_snapshots` likewise frozen at 1686, with zero rows captured after 16:17:00.

---

## 12. Is the active credit leak CLOSED?

**Yes. Closed, and verified twice.**

**Before** — every tick from 13:16 to 16:01 spent 3 credits and persisted nothing:

| | |
|---|---|
| Wasted ticks (13:16 → 16:01) | **12** |
| Credits burned | **36** |
| Rows persisted | **0** |
| `odds_snapshots` throughout | 1420, unmoved |

The ledger corroborates the tick count exactly: 249 at 14:01 → 252 at 14:16 → 273 at 16:01, which
is 7 ticks × 3 credits between 14:16 and 16:01 with no data to show for it.

**After** — ticks 2 and 3 made no call and moved nothing.

**Projected run rate: 288 credits/day → roughly 6 credits/day while the slate stays FAR** (two
daily due-boundaries, one per capture cohort), rising legitimately as kickoff approaches. That is
a ~98% reduction, and what remains is real work rather than waste.

**One qualification, stated plainly:** this proves the leak is closed *for the current cause* — an
unmapped team identity. It does not prove the *class* of leak is impossible. See the architecture
debt below.

---

## 13. Next autonomy step

Two candidates. Recommendation and ordering:

### Recommended first: make canonical schedule maintenance autonomous

Set **`MASTER_REFRESH_ENABLED=true`** permanently so the existing `cron-schedule-refresh`
(`0 9 * * *`) becomes real autonomy instead of an inert daily no-op.

Why this is the right next step rather than more odds work:
- **Odds autonomy is now proven end to end** — new games appear, get linked, get polled, throttle
  correctly, all with no human input. The layer *below* it, canonical schedule maintenance, is
  still manual.
- **Cost is 1 SportsDataIO call per day**, already measured on the 12:45 run.
- **It auto-recovers GameKey `202610902`** (CIN @ ATL, Week 9). The venue alias fix shipped in
  `84c6892`, so the row that was refused will now be admitted. The season goes 271 → 272 with no
  dedicated call and no manual step.
- It is the last remaining piece that still needs a human to spend a call.

### Then, naturally occurring, no action required: the kickoff ramp proof

This pass exercised **only the FAR tier**. The RAMP_2H → RAMP_60M → RAMP_15M → RAMP_5M ladder
cannot be observed until a game is genuinely inside two hours. First real opportunity:
**DET @ BUF, Thursday 2026-09-18 22:15 UTC**. Nothing needs to be scheduled — just observed. It
should not be simulated by moving clocks or rescheduling crons.

**A cost note to weigh before that proof, not a fix:** the cron ticks every 15 minutes, so the
120 s / 300 s / 900 s ramp intervals cannot actually be honoured — the achievable floor is 15
minutes. RAMP_5M, RAMP_15M and RAMP_60M are all effectively floored at the cron period today.
Conversely, on a Sunday with 13 games ramping, most of the 96 daily ticks would find something
due, approaching 288 credits for that day — legitimately this time, but worth pricing before
Sunday rather than after. Out of scope for this pass; raised for decision.

---

## Architecture debt recorded (NOT fixed this pass, per directive)

> **A failed or unresolved odds ingestion attempt does not advance `last_polled_at`.**
>
> `last_polled_at` is derived from `odds_snapshots.captured_at`
> (`app/persistence/odds_snapshots.read_last_polled_at`). A game that is polled but whose event
> cannot be resolved persists no snapshot, so it records no evidence of having been attempted, so
> it reads as never-polled and is due again on the very next tick — permanently. Attempt and
> success are the same signal, and only success is recorded.
>
> That is precisely the shape of the leak closed above. Repairing the 15 mappings removed *this*
> instance; it did not remove the mechanism. **Any future identity failure — a new team string, a
> renamed franchise, a provider changing its naming, a rescheduled game whose kickoff moves
> outside tolerance — recreates the same every-tick spend pattern automatically.**
>
> A partial defence already exists and deliberately does not cover this: `MANUAL_SEED_MAX_ATTEMPTS = 3`
> in `app/workers/odds_worker.py`, added after the identical 2026-09-07 incident, applies **only**
> when `games.manual_seed = true` and is explicitly documented as "never applied to a normal
> Schedule/Master-Refresh-sourced game… those correctly keep retrying a real,
> temporarily-unresolved team mapping forever." That judgment assumed such gaps are transient. The
> gap just repaired was permanent, and the "forever" ran literally for 12 ticks.
>
> **Not fixed in this pass by directive.** Recorded so the next occurrence is recognised
> immediately rather than rediscovered.

---

## Hard boundary compliance

- **No manual provider invocation.** Both observed ticks were the cron's own natural `*/15`
  firings. The single Odds API request was made by the scheduled worker, not by this session.
- **No cadence altered.** `windows.py` untouched.
- **No cron configuration changed.** `cron-odds-worker` still `*/15 * * * *`, dev, target
  `odds-worker`, restart NEVER. `cron-schedule-refresh` still `0 9 * * *`.
- **No SportsDataIO, MSF or LLM calls.**
- **No recommendations run.**
- **No unrelated repairs.** The `InMemoryCacheBackend`-per-invocation finding, the
  `MANUAL_SEED_MAX_ATTEMPTS` scope gap, the `last_polled_at` debt, the `*/15`-vs-ramp-interval
  mismatch, and `cron-master-refresh`'s stale branch are all **reported, not fixed**.
- **`MASTER_REFRESH_ENABLED` remains `false`.** GameKey `202610902` still absent; season still 271.

## Files changed

- `supabase/migrations/20260916160500_the_odds_api_team_identity_repair.sql` (new, applied to dev)
- `docs/ops/phase-8-odds-team-identity-repair-and-autonomous-proof-2026-09-16.md` (new)
- `PROGRESS.md`

Zero code changes. One data migration (15 rows). Three credits spent, by the scheduled worker.
