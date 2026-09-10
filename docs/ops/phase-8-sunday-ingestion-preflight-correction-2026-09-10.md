# Sunday Ingestion Preflight Correction (2026-09-10)

MANSA HQ directive: "SUNDAY INGESTION PREFLIGHT CORRECTION." Corrects five
items in the prior design (`docs/ops/phase-8-sunday-completed-game-ingestion-design-2026-09-10.md`)
before build authorization. Design/audit only -- zero code, schema, provider
calls, staging, or production this pass. Railway variable-name listing and
Supabase reads used for verification; no MSF/BALLDONTLIE call made.

---

## 1. MSF credential location -- discrepancy reconciled

**HQ was right, the prior report was wrong.** Live Railway DEV inspection
(`list-variables`, names only, no value read or exposed) confirms
`MYSPORTSFEEDS_API_KEY` **is present today** on `sports-intel-layer` in the
`dev` environment, alongside every other provider key this project uses
(`SPORTSDATAIO_API_KEY`, `THE_ODDS_API_KEY`, `BALLDONTLIE_API_KEY`,
`WEATHERAPI_API_KEY`, `GNEWS_API_KEY`, etc.) and every `RUN_MSF_*`
diagnostic flag from every prior MSF pass.

**What was actually true, stated precisely:** the credential is correctly
provisioned on the correct service. What does not yet exist is a *standing
code path* that uses it -- every MSF call to date (Gate B included) went
through a temporary module + a gated `RUN_..._DIAGNOSTIC` flag + a one-time
`set-variables` deploy, not a permanent, always-invocable worker function.
The prior report's "no standing key exists on an always-on service" was
inaccurate and is corrected here: the key exists; the gap is architectural
(a reusable code path), not a credential-provisioning gap.

**Can the proposed Postgame Ingestion Worker run on `sports-intel-layer`?**
Yes, safely, and it is the natural home for it. `sports-intel-layer` is
this project's provider-adapter-hosting service -- it already holds every
provider credential MANSA uses and already exposes internal HTTP endpoints
that Railway Cron Job services dispatch into (the `cron-master-refresh` ->
`POST /v1/internal/master-refresh/run` pattern from Milestone 4.9/the
Pre-Phase-6 gate is the direct precedent). A new
`POST /v1/internal/postgame-msf-boxscore/run` endpoint on this same service,
dispatched by a new `cron-postgame-msf-boxscore` Railway Cron Job service
(mirroring `cron-master-refresh`/`cron-postgame-grading`/etc. exactly),
requires no new service and no new credential provisioning.

**Is any credential move/copy actually necessary? No.** The key is already
on the one service that needs it. Nothing to move, nothing to copy. The
credential value itself was not read or displayed at any point in this
audit -- only its name's presence in the variable list was confirmed.

---

## 2. Actual Sunday scope -- MANSA's real canonical games, not a generic maximum

Queried `games` directly (dev, no provider call). MANSA's canonical
database holds **12 total games**, of which:

- 4 are pre-existing fixture/seed rows (`external_provider_id` like
  `seed-game-final`/`seed-game-live`/etc., dated August 2026) -- unrelated
  to the real 2026 season, not part of Sunday scope.
- 1 is the already-captured SEA @ NE opener (Gate B's game, kickoff
  2026-09-10, not a Sunday game).
- **4 are the real Sunday, September 13, 2026 slate**, all
  `external_provider_id = balldontlie:...` (real BALLDONTLIE-sourced Week 1
  games, not invented), all `status = 'scheduled'`:

  | Matchup | Kickoff (UTC) | Kickoff (ET) | MSF `game_provider_ids` row exists? |
  |---|---|---|---|
  | Las Vegas @ Miami | 2026-09-13 20:25 | 4:25 PM | **No** |
  | Minnesota @ Green Bay | 2026-09-13 20:25 | 4:25 PM | **No** |
  | Philadelphia @ Washington | 2026-09-13 20:25 | 4:25 PM | **No** |
  | LA Chargers @ Arizona | 2026-09-13 20:25 | 4:25 PM | **No** |

- 3 are Oct 11, 2026 placeholder rows, a different future week, not Sunday
  Sept 13 scope.

**Actual Sunday, Sept 13 scope = 4 games, one single kickoff window
(4:25 PM ET / 20:25 UTC).** This is not the full real-world NFL Sunday
(a real Sunday typically runs 13-14 games across four kickoff windows:
1:00, 4:05, 4:25, 8:20 PM ET) -- it is what MANSA's canonical database
currently tracks. If more of the real slate gets seeded before Sunday (a
schedule-ingestion concern, separate from this MSF pipeline), the capacity
numbers in §3 scale linearly and are given as a formula for exactly that
reason.

**A newly-surfaced concrete blocker, not previously named**: all 4 of
these real games currently have **zero** `mysportsfeeds` `game_provider_ids`
rows. Every prior MSF pass (Gate B included) worked from a canonical
`game_id` whose MSF numeric game ID was already resolved (by inspection,
once, ahead of time). No mechanism exists yet to resolve *these* four
games' MSF ids automatically. This is a real, additional prerequisite --
folded into the build-order recommendation in §5, not glossed over.

---

## 3. Reduced provider call budget

### What changed and why

The prior design's 8-attempt, 30-minute-cadence budget was set to
comfortably cover the theoretical worst case without first asking what the
*minimum* safe schedule looks like. Redesigned to bias hard toward "one
successful call, once, per game" and to treat "not complete yet,"
"transient network hiccup," and "genuine provider failure" as three
different signals with three different responses -- exactly as HQ asked.

| Signal | What it means | Response |
|---|---|---|
| **Not-completed-yet** | `HTTP 200`, parses, `playedStatus != "COMPLETED"` -- MSF has nothing final to give yet. Real information, not an error. | Counts toward the per-game check budget below. No short retry -- checking again in seconds/minutes cannot produce a different answer for a game that legitimately isn't over. |
| **Transient network failure** | Timeout, connection reset, 5xx, 429 -- the request itself didn't complete meaningfully. | Up to 2 quick, local retries (immediate, then +60s) *within* the same scheduled check -- cheap, bounded, does not consume an extra check-budget slot beyond the one it's already part of. If still failing after those, that check is marked failed-this-cycle and deferred to the *next* scheduled check (not re-attempted early). |
| **Genuine provider failure** | A real 4xx tied to the request itself (bad request, 404 on an unresolvable MSF game id, 401/403 auth) or a non-JSON/malformed body -- retrying on the same cadence will not fix this. | **Escalates to manual review immediately** (1 occurrence, or 2 identical occurrences if HQ prefers a confirmation step) rather than silently burning the full check budget pretending it is merely "not ready yet." |

### Redesigned per-game check schedule

| Check | Offset from kickoff | Rationale |
|---|---|---|
| 1 (first) | `+3h30m` | Later than the prior `+3h` -- the realistic average NFL game (including a modest margin) is already over by this point, minimizing wasted early "not ready" checks. Under normal conditions **this one check succeeds**. |
| 2 | `+4h30m` | |
| 3 | `+5h30m` | 1-hour spacing (not 30 min) -- see the cache-interval note below; tighter spacing rarely yields new information. |
| 4 (last) | `+6h30m` | After this, escalate to a visible "stuck, needs manual review" state -- never polled further automatically. |

**Hard cap: 4 checks per game** (down from 8), spanning a 3-hour follow-up
window (`kickoff+3h30m` to `kickoff+6h30m`) -- still generous enough for
overtime and real provider publication lag, much tighter on call count.

### Why 1-hour (not 30-minute) follow-up spacing is evidence-based, not arbitrary

Every real MySportsFeeds response this project has ever captured --
including Gate B's own raw evidence, re-read directly from
`game_events.raw_payload->'response_headers'` for this audit -- carries
`cache-control: no-transform, max-age=10800` (a **3-hour CDN edge cache**)
and `x-cache`/`x-cache-hits` headers showing repeated identical requests
are served from cache, not MSF's origin. Gate B's own captured response
was itself already 904 seconds (~15 minutes) old at the cache layer when
MANSA received it. This means checking materially more often than the
underlying cache refreshes is unlikely to reveal fresher data anyway --
it mostly just re-serves a stale cached answer. That is direct evidence
*for* wider spacing, not a guess: 1-hour follow-up intervals are chosen
because tighter spacing has a real, documented reason to be low-value, not
merely to be conservative for its own sake.

### Expected / hard-maximum call counts

**Per game:**
- Expected (normal conditions): **1**
- Hard maximum (state-machine level, 4 scheduled checks): **4**
- Absolute pathological ceiling (every one of the 4 checks also hits a
  transient failure requiring both local retries): **12** -- a
  double-failure scenario (every check late *and* every check
  network-flaky), not a planning number.

**Actual Sunday, Sept 13 slate (4 games, per §2):**
- Expected total: **4 games x 1 = 4 calls**
- Hard maximum total (state-machine level): **4 games x 4 = 16 calls**
- Pathological ceiling: **4 games x 12 = 48**

This directly satisfies "prefer approximately ONE successful boxscore call
per game under normal conditions" and cuts the previous 128-call ceiling
by 8x for the actual slate size in scope.

**If the real slate grows before Sunday** (more games seeded), the same
policy scales linearly: expected = `N x 1`, hard maximum = `N x 4`. A full
13-14-game real NFL Sunday under this same policy would be expected ~13-14,
hard maximum ~52-56 -- still well under the prior design's 128 ceiling for
a 16-game assumption.

---

## 4. MSF plan / rate-limit knowledge -- audited, not called for

Audited: every prior MSF ops doc (`nfl-provider-bakeoff-2026-09-03.md`,
`nfl-provider-gap-test-mysportsfeeds-2026-09-03.md`, the Phase 8.0.5/8.2/8.3
series), the `mysportsfeeds.py`/`mysportsfeeds_game_boxscore.py` adapter
code, and the raw response headers already captured in `game_events` for
Gate B's real call (read live, no new request).

**No numeric MSF rate limit (requests/minute, requests/day, or any
`x-ratelimit-*` header) has ever been observed or documented anywhere in
this project.** This is confirmed **UNKNOWN**, not merely unstated:
- Gate B's own real, live-captured response headers (re-read for this
  audit) contain no `x-ratelimit-*` header of any kind.
- The one prior MSF bake-off/gap-test document names the subscribed tier
  ("NFL, Commercial Near-Realtime, CORE + STATS + DETAILS, 14-day trial")
  but records no numeric call-volume limit for it -- by contrast, that same
  document *does* record BALLDONTLIE's (5/min, confirmed via header) and
  API-SPORTS's (10/min soft, 100/day hard, confirmed via header) limits
  explicitly, so the absence for MSF is a real gap in what's been observed,
  not an oversight in searching.
- Every MSF response this project has ever captured instead carries
  `cache-control: no-transform, max-age=10800` (3-hour edge cache) and
  `x-cache`/`x-cache-hits` -- a real, repeatedly-confirmed capacity fact,
  just not a rate limit. Its practical effect on this design is covered in
  §3 above (it justifies wider check spacing; it does not tell us what
  MSF's actual origin-request ceiling is).
- One prior diagnostic (Phase 8.2's first players-identity probe) hit a
  `ReadTimeout` with empty response headers -- a latency/reliability data
  point, not a rate-limit signal either.

**Design stance: UNKNOWN, designed conservatively**, exactly as instructed.
The §3 budget (4 games x 4-attempt hard cap = 16 calls, worst case, for the
actual Sunday slate) is deliberately far below any plausible reading of
"Commercial Near-Realtime" tier limits for a paid subscription, so this
design does not depend on ever learning the real number to stay safe --
but confirming MSF's actual plan terms (a documentation/account-portal
question, not a provider call) remains worth doing before Sunday for
peace of mind, not because this design's ceiling is at risk without it.

---

## 5. Build order -- HQ's sequence reviewed, one addition, one note

HQ's proposed order:
`A (schema foundation) -> B (team identity) -> C (eligibility/call-control)
-> D (player activation/quarantine) -> E (ingestion worker) -> F
(one-game validation) -> G (Sunday enablement)`

**The dependency chain holds and this order is safe.** Specifically:
- **D genuinely depends on B**, not just conventionally -- the
  player-activation team-resolution pre-check (from the prior design's
  §3) cannot safely resolve a player's team without a working numeric
  `team_provider_ids` mapping, so B must land before D. HQ's order already
  reflects this correctly.
- **E depends on both C and D** -- the ingestion worker's job is to call
  C (is this game eligible right now?), then D (resolve/activate every
  player), then persist -- it has nothing to orchestrate until both exist.
  Correct as ordered.
- **B and C have no dependency on each other** and could technically be
  built in either order or in parallel -- the eligibility state machine
  (C) only needs `games.kickoff_at` and the new ingestion-state table (A),
  never team identity. Not a required change to HQ's sequence (B before C
  is perfectly safe), just a note that this pair is not itself
  order-constrained if HQ ever wants to parallelize the work.

**One addition this pass surfaces, not in HQ's original six steps**:
resolving the 4 real Sunday games' own MSF **game-level** identity
(`game_provider_ids` for `mysportsfeeds`) is a real prerequisite for E/F to
target real games at all (§2's newly-found 0/4 gap) -- this is the same
kind of identity-resolution work as B (team identity), just at the game
level instead of the team level, and belongs in the same phase of work as
B, before D/E/F. Recommend HQ treat this as **B'** (game identity,
alongside B's team identity) rather than adding a wholly separate step --
it's the same category of prerequisite work, discovered by this pass's
scope check, not a new architectural concern.

**One refinement to F**, using evidence already in hand rather than
spending a new provider call to get it: split F into two sub-steps --

- **F1 -- replay validation, zero new provider calls.** Run the new
  ingestion worker's identity-resolution and persistence code paths
  against the *already-captured* Gate B raw payload
  (`game_events.id = a9a13a2a-b7b4-48be-8257-f5ee95e1ee0b`) as if it had
  just arrived from a live call. This proves the new automated code
  reaches the exact same result the manual passes already proved
  (69/69 resolved, 69 rows persisted) with zero MSF cost and zero new
  risk, before ever trusting the pipeline with a live call.
- **F2 -- one real, fully-monitored live call.** Only after F1 passes,
  authorize one real live call against one actual upcoming game (e.g. one
  of the 4 real Sunday games, once its own game-level MSF identity from
  B' is resolved) to prove the live path end to end before G.

This is a safety refinement within HQ's own step F, not a reordering of
HQ's six-step sequence, which otherwise stands as proposed.

---

## Revised concrete blockers (supersedes the prior pass's list)

1. `team_provider_ids` widening + 32-team numeric-ID backfill -- still not
   applied (unchanged from the prior pass).
2. **New this pass**: game-level `mysportsfeeds` `game_provider_ids`
   resolution for the 4 real Sunday games -- currently 0/4. Folded into
   build-order step B' above.
3. ~~No standing MSF credential wired to any always-on service~~ --
   **retracted, was inaccurate.** The credential already exists on
   `sports-intel-layer`; the real gap is the standing code path (build
   steps C/D/E), not credential provisioning.
4. MSF's actual plan/rate-limit terms remain unconfirmed -- but per §4,
   this design's call budget is deliberately conservative enough not to
   depend on learning the real number before Sunday.
5. No prior automated end-to-end run of the full pipeline exists --
   addressed by the F1/F2 split in §5 (a zero-cost replay validation
   before any new live call).

No code, schema, or provider calls made this pass. No staging/production
touched.
