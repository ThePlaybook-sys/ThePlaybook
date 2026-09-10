# Sunday Completed-Game Ingestion Design (2026-09-10)

MANSA HQ directive: "SUNDAY COMPLETED-GAME INGESTION DESIGN." Design only --
zero provider calls, zero schema changes, zero implementation. Builds on
Phase 8's proven single-game pipeline (`parse_game_boxscore` +
`persist_player_stats(provider_name="mysportsfeeds")`, 69/69 real players
persisted for Gate B's game) and the two remaining known blockers from that
work: no automated call trigger, and the `team_provider_ids` numeric-ID gap.

This document is the permanent design MANSA HQ can authorize for
implementation in a future pass. Nothing here is built or applied.

---

## 1. Completed-game detection: a conservative state machine

**`games.status` is a hint, never the authority.** It is written by schedule
ingestion (a different provider, a different cadence) and can be stale,
wrong, or simply not yet updated when a game actually finishes. The only
authority for "this game is really over" is the postgame provider response
itself -- MSF's own `game.playedStatus` field on the boxscore payload
(`"COMPLETED"` in the real Gate B response). Everything before that is a
*candidate signal* that widens or narrows when MANSA is willing to spend a
call checking, never a fact MANSA persists as true.

### Proposed per-(game, provider) state machine

```
scheduled
   |  kickoff_at reached (from games.kickoff_at, the schedule-ingestion field
   |  already trusted for scheduling -- not being redefined here)
   v
eligible_for_postgame_check  <-------------------+
   |  first attempt fires at kickoff + T_min       |  provider says "not final yet"
   |  (see timing below)                           |  (response 200, playedStatus
   v                                                |   != COMPLETED, or a clean
capture_in_progress  -- (claimed by one worker) ----+  "not published" signal) --
   |                                                   reschedule next attempt,
   |  HTTP/transient failure (timeout, 5xx,            stay in this state
   |  connection reset) -- see policy below
   |------------------------------------------------> capture_failed_transient
   |                                                    (bounded retry, short backoff,
   |                                                     returns to eligible_for_
   |                                                     postgame_check when budget
   |                                                     remains, else escalates)
   |
   |  HTTP 200, parses, playedStatus == COMPLETED
   v
captured           (raw response persisted -- see §2)
   |  parse_game_boxscore succeeds structurally
   v
validated
   |  every player/team identity resolves (or is safely
   |  auto-activated -- see §3) with zero unresolved
   |  conflicts for this game
   v
confirmed_complete  (player_stats persisted -- terminal, never re-attempted)

-- side branches, terminal or manual-review, not silent dead ends --
capture_failed_permanent    (retry budget exhausted -- never auto-retried again,
                              flagged for manual review, never silently dropped)
validation_failed           (payload didn't parse -- raw kept, flagged, never
                              auto-retried against the same raw payload;
                              a fresh capture attempt IS allowed on a manual
                              "re-check this game" trigger, never automatic)
partially_confirmed         (some players persisted, one or more quarantined --
                              see §3 -- game stays in this state, visible,
                              until the quarantine entries are resolved)
```

**Postponed/delayed games** are handled by the same mechanism, not a special
case: if `games.kickoff_at` changes (schedule re-ingestion already does
this), any row still in `scheduled` simply computes its eligibility window
off the new timestamp. A game already in `eligible_for_postgame_check` whose
kickoff moved *later* (rare, but possible for a live postponement) should
have its `next_eligible_attempt_at` pushed out by the same delta rather than
left checking on the old schedule -- this is the one piece of this state
machine that needs to listen for a kickoff-time change on an already-open
row, not just read it once at entry.

**Already-captured games never re-enter the machine.** `confirmed_complete`
is terminal. The very first thing any worker tick does for a game is check
its current state; a `confirmed_complete` row is skipped before any
provider-call cost is even considered. This is what makes "never repeatedly
charge for a game already captured" a property of the state machine itself,
not a manual precaution.

### Timing: kickoff, duration, overtime, provider lag

- **Normal NFL game duration**: average ~3h10m real time, occasionally
  shorter, rarely much longer without OT.
- **Overtime**: adds up to roughly another 15-30 minutes.
- **Provider publication lag**: MSF publishing a fully-finalized boxscore
  (all stat categories, not just the final score) can trail the final
  whistle by some margin -- Gate B's own real capture shows
  `lastUpdatedOn` sitting meaningfully after kickoff+duration, so the
  design must not assume "final whistle time" equals "boxscore ready time."

Proposed schedule (per game, all relative to `kickoff_at`):

| Event | Offset | Rationale |
|---|---|---|
| First eligibility check | `kickoff_at + 3h00m` | Covers a normal-length game with margin; earlier is pure wasted calls since MSF cannot have a final boxscore yet |
| Recheck cadence while `eligible_for_postgame_check` | every 30m | Tight enough to catch a finished game promptly, loose enough to stay well under any reasonable rate limit |
| Retry budget (this state) | 8 attempts | Spans `kickoff+3h` to `kickoff+7h` -- covers OT, provider lag, and a genuinely late night game with real margin |
| Escalation to `capture_failed_permanent` | after 8th unsuccessful attempt | Never infinite -- becomes a visible, queryable "stuck" row instead of silent forever-polling |

This is intentionally conservative on the early side (no call before
kickoff+3h) and bounded on the late side (stop after kickoff+7h without
success, surface it, do not keep polling into Monday unattended).

---

## 2. Provider call control

### Durable per-game state, not in-memory scheduling

A new table (design only, **not applied this pass**) carries every fact the
policy above needs, and is the single source of truth a worker consults
before making any call:

```
game_postgame_ingestion_state
  id                     uuid, pk
  game_id                uuid, fk -> games.id
  provider_name          text  -- 'mysportsfeeds' (room for a second provider later)
  state                  text  -- the state-machine values above
  attempt_count          int, default 0
  last_attempt_at        timestamptz, nullable
  next_eligible_attempt_at timestamptz, nullable
  last_http_status        int, nullable
  last_error              text, nullable
  raw_capture_id          uuid, fk -> game_events.id, nullable
  captured_at              timestamptz, nullable
  quarantine_reason        text, nullable
  updated_at                timestamptz
  unique (game_id, provider_name)
```

This is the same shape of idea as `activation_run_markers` and
`master_refresh_runs` -- state lives in Postgres, not in a worker's memory,
so a redeploy costs nothing (see the Sunday Operating Plan below).

### Claim pattern (idempotent across concurrent workers / restarts)

Before calling MSF for a game, a worker tick does one atomic claim:

```
UPDATE game_postgame_ingestion_state
SET state = 'capture_in_progress', last_attempt_at = now(), attempt_count = attempt_count + 1
WHERE game_id = $1 AND provider_name = 'mysportsfeeds'
  AND state = 'eligible_for_postgame_check'
  AND next_eligible_attempt_at <= now()
RETURNING id;
```

Only a worker that gets a row back proceeds to call MSF. Two overlapping
cron ticks (or two worker instances) racing on the same game: exactly one
wins the claim, the other's `UPDATE` affects zero rows and it moves on.
This is the same guarantee `activation_run_markers`' unique-constraint
claim already gives the project elsewhere -- reused, not reinvented.

**Stale `capture_in_progress` recovery**: if a worker crashes mid-call (a
Railway restart, an unhandled exception before the state transition
completes), the row is stuck in `capture_in_progress`. A recovery sweep
(the same worker tick, or a lightweight separate check) treats any row in
`capture_in_progress` for longer than a short staleness window (e.g. 10
minutes -- far longer than any single HTTP call should ever take) as
abandoned and returns it to `eligible_for_postgame_check` with
`next_eligible_attempt_at = now()`, consuming one attempt from the budget
(the attempt was already counted at claim time, so this never grants extra
calls beyond the 8-attempt budget).

### Transient failure vs. accepted-but-not-ready

These are different signals and must be handled differently:

- **Transient (HTTP/network failure)** -- timeout, connection reset, 5xx,
  429: the request itself did not complete meaningfully. Retry on a short
  independent backoff (e.g. 30s, 2m, 10m -- 3 tries) *before* falling back
  to the standard 30-minute state-machine cadence. This short retry
  sequence is bounded and counted within the same attempt budget, not an
  unbounded side loop.
- **Accepted-but-not-ready** -- HTTP 200, response parses, but
  `playedStatus != "COMPLETED"` (or MSF's equivalent "not published yet"
  shape): this is not a failure, it's real information -- the game legitimately
  isn't final from MSF's point of view yet. No short-interval retry;
  return to `eligible_for_postgame_check` on the normal 30-minute cadence.
  A 200 response received here is **not** persisted as a raw capture (see
  below) -- only an accepted, complete boxscore gets written to
  `game_events`, so an incomplete/interim payload never contaminates the
  raw evidence layer with something that looks like a final capture but
  isn't.

### Raw preservation before normalization

Every response MANSA accepts as a genuine final capture (`playedStatus ==
"COMPLETED"`, parses at the JSON level) is written via the existing,
unmodified `write_raw_game_events` **before** `parse_game_boxscore` is even
called -- exactly the Gate B precedent. If `parse_game_boxscore` then fails
structurally, the raw evidence is already durably saved; only the
*processing* of it failed (`validation_failed`), never the *capture*.

### Worst-case MSF request count for a Sunday slate

Assumptions: a full, non-bye-week Sunday slate (16 games), every single one
hits the full 8-attempt retry budget before succeeding (the true worst
case -- every game runs unusually long, MSF is slow to publish every one of
them, and every game needs its full window).

```
16 games x 8 attempts (state-machine level)  = 128 requests
```

Transient-failure short-retries are a separate, smaller multiplier that is
already bounded (max 3 extra tries per state-machine attempt if that
specific attempt hit a network failure) -- in the true worst case where
*every* attempt of *every* game also hit a transient failure before
succeeding, the theoretical ceiling would be `128 x 4` (the failed attempt
itself plus 3 retries) `= 512`. This is a pathological double-failure
scenario (every game late *and* every check network-flaky) rather than a
realistic planning number.

**Realistic/expected case**: one successful call per game once it actually
finishes, plus a small number of "not ready yet" checks for the one or two
games still wrapping up in the same 30-minute window as an earlier one's
first eligible check -- **roughly 20-30 calls for a full Sunday slate**,
not 128. The 128 figure is the deliberately conservative planning ceiling
this policy guarantees will not be exceeded under normal-failure
assumptions, not an expectation.

---

## 3. Automatic player identity activation

Reuses the exact pattern already proven manually in the Full Game Player
Activation pass (`app.persistence.player_identity.ensure_player`:
check-for-existing-mapping-first, create `players` + `player_provider_ids`
together only if genuinely absent) -- automated, with stricter guardrails
than a human audit needs, since no one is double-checking each one before
it lands.

### Per-player decision sequence (during the IDENTITY RESOLVED stage, §5)

For every `PlayerStatLine` in a validated boxscore not already resolved via
an existing `player_provider_ids(provider_name='mysportsfeeds',
provider_player_id=X)` mapping:

1. **Collision check (primary safety gate).** Does this MSF
   `provider_player_id` already exist in `player_provider_ids` mapped to a
   *different* `player_id` than the one about to be created? This should
   be structurally impossible (provider_player_id is meant to be unique
   per provider) but must be checked, not assumed -- if found, this is a
   real data-integrity conflict: **stop, do not create, quarantine** (see
   below). This is never auto-resolved.
2. **Team resolution.** Which canonical `team_id` does this player belong
   to? Resolved from which side of the boxscore payload the player
   appeared under (home/away), mapped through that team's own
   `team_provider_ids` row for `mysportsfeeds` -- **never** inferred from
   the player's name or any other heuristic. If the team itself cannot be
   resolved (see §4 -- the numeric-vs-abbreviation gap), this player
   cannot be safely activated: **stop, do not create, quarantine** with
   reason `team_unresolved`. This does not block any *other* player in the
   same game whose team already resolves.
3. **Name-similarity safety check.** Before creating a new canonical
   player, fuzzy-compare the incoming name against existing canonical
   players **without** a `mysportsfeeds` mapping already (the same check
   run manually before the Full Game Player Activation pass, cutoff 0.82).
   A hit above threshold is not proof of a duplicate, but it is exactly
   the kind of ambiguity a human reviewed manually last time and an
   automated pipeline must not silently resolve either way: **stop, do
   not create or merge, quarantine** with reason `name_similarity`,
   carrying both candidate names for a human to adjudicate.
4. **Create, atomically, only if all three checks pass.** One
   `players` row + one `player_provider_ids` row, gated by the same
   `WHERE NOT EXISTS` idempotency pattern used manually -- safe to run
   this exact check again on a retry or a redeploy; it will find the row
   already exists and do nothing.

**MSF player ID is the sole primary identity evidence.** Name and position
are stored as attributes on the row once created, never used as the
matching key for "is this an existing player" beyond the safety-net
similarity check in step 3, which exists purely to *block* an unsafe
auto-create, never to *perform* one.

### Quarantine, not silent guessing

A new table (design only, **not applied this pass**):

```
player_identity_quarantine
  id                 uuid, pk
  game_id            uuid, fk -> games.id
  provider_name      text
  provider_player_id text
  raw_player_name    text
  team_hint          text        -- whatever raw team signal was available
  conflict_type       text       -- 'id_collision' | 'team_unresolved' | 'name_similarity'
  candidate_player_id uuid, fk -> players.id, nullable  -- the ambiguous match, if any
  detected_at          timestamptz
  resolved_at           timestamptz, nullable
  resolution_note        text, nullable
```

A quarantined player's stat line is **not** persisted to `player_stats` --
but it is not lost either. The raw boxscore payload already contains it
(preserved permanently per §2), and the quarantine row itself is a
permanent, queryable, human-visible record of exactly what was ambiguous
and why. A game with one or more quarantined players lands in
`partially_confirmed` (§1), not `confirmed_complete` -- so "this game's
persistence is incomplete" is itself a visible, honest state, never
silently reported as done. Resolving a quarantine entry (manually, a
future pass) and re-running identity resolution for that one player is
designed to be safe and idempotent, reusing the same create-if-absent gate.

---

## 4. MSF team identifiers: is the widening still correct?

**Yes -- and it now goes from "designed but optional" to "required before
this pipeline can run unattended."** The manual Gate B/activation passes
worked around the gap by resolving NE and SEA's numeric IDs by hand; an
automated Sunday pipeline processing 13-16 games' worth of *different* team
pairs cannot do that. Every game's home/away numeric MSF team ID needs to
resolve to a canonical `team_id` without a human in the loop, and today
`team_provider_ids` only carries the abbreviation-scheme mapping for
`mysportsfeeds` per the `(team_id, provider_name)` unique constraint.

**The previously designed fix remains the correct minimal one**: widen the
unique constraint to `(team_id, provider_name, provider_team_id)`. This
lets both the existing abbreviation row and a new numeric-ID row coexist
for the same team under the same provider, with zero change to how any
existing reader queries the table (both rows are just `provider_name =
'mysportsfeeds'` rows, distinguished by which `provider_team_id` scheme
they carry). No alternative (a second table, a provider-name suffix hack
like `mysportsfeeds_numeric`) is simpler or more consistent with how this
project already models multi-provider identity.

**One addition this pass makes to that design**: automated ingestion also
needs the *numeric* MSF team ID actually populated for all 32 teams before
Sunday, not just NE/SEA. That is a one-time real-data backfill (same
"schema via migration, real data via execute_sql" convention already used
for the player activation pass) -- **not applied this pass**, but it is a
concrete, named prerequisite alongside the constraint widening itself, and
belongs in the same future authorization.

**Not applied this pass, per HQ's explicit instruction** -- named here as
the one schema change this design actually requires before the ingestion
pipeline can be built.

---

## Pipeline: RAW -> VALIDATED -> IDENTITY RESOLVED -> PLAYER-GAME PERSISTED

```
 MSF response (accepted, playedStatus == COMPLETED)
        |
        v
 [RAW]  write_raw_game_events (unmodified, existing) -- ALWAYS persisted
        before any parsing is attempted. Failure beyond this point never
        loses the underlying evidence.
        |
        v
 [VALIDATED]  parse_game_boxscore (unmodified, existing pure adapter)
        |
        |-- structural parse failure --> validation_failed (raw kept,
        |                                 flagged, never silently retried
        |                                 against the same payload)
        v
      success: structured list[PlayerStatLine] + team/game identifiers
        |
        v
 [IDENTITY RESOLVED]  per-player resolution per §3, per-team resolution per §4
        |
        |-- one or more players quarantined --> those lines excluded,
        |                                        game marked partially_confirmed
        |                                        (visible, not silently dropped)
        |
        v
      every remaining line resolved to a canonical player_id
        |
        v
 [PLAYER-GAME PERSISTED]  persist_player_stats(provider_name="mysportsfeeds")
        (unmodified, existing, idempotent, append-only-enforced) --
        game marked confirmed_complete if zero quarantines, else
        partially_confirmed
```

Every arrow that can fail lands in a named, queryable, non-silent state.
Nothing before RAW can corrupt historical intelligence, because nothing is
written to `player_stats` until the very last stage, and every stage before
it either passes its output forward intact or stops and quarantines --
never partially transforms and continues.

---

## Sunday Operating Plan

### Worker/scheduler behavior

Reuses this project's own established pattern (the Railway Cron Job
dispatcher, `apps/workers/app/cron_dispatch.py`, and the existing Postgame
Ingestion Worker's own "status-scan game-final detection... bounded
reconciliation" precedent from Phase 3E-8 -- this design is a provider
extension of that same shape, not a new architecture). A cron tick, every
15-30 minutes during the Sunday afternoon-through-night window:

1. Query `game_postgame_ingestion_state` (join `games`) for every row in
   `eligible_for_postgame_check` with `next_eligible_attempt_at <= now()`,
   plus the stale-`capture_in_progress` recovery sweep (§2).
2. For each, attempt the atomic claim (§2). Skip any that lose the race.
3. For each successfully claimed game, run RAW -> VALIDATED -> IDENTITY
   RESOLVED -> PLAYER-GAME PERSISTED end to end, updating
   `game_postgame_ingestion_state` at every stage transition.

### Concurrency limits and provider-rate protection

Process claimed games with small bounded concurrency (e.g. 2-3 in flight at
once), not full slate-wide parallelism -- MSF's exact rate-limit terms
aren't confirmed (a named blocker below), so the design stays conservative
by default rather than assuming headroom. The 30-minute state-machine
cadence itself is the primary rate-limiting mechanism: even a completely
serial worker only ever issues one call per eligible game per 30-minute
tick, never a burst against every game in the slate simultaneously (ticks
naturally stagger by whichever games are actually eligible at that moment,
which itself staggers by kickoff time across the 1pm/4pm/8pm windows).

### Idempotency and recovery after Railway restart/deploy

Every fact this pipeline needs lives in Postgres
(`game_postgame_ingestion_state`, `game_events`, `player_provider_ids`,
`player_stats`), never in worker memory. A Railway restart or redeploy
mid-Sunday loses nothing: the next cron tick re-reads state and resumes
exactly where it left off, using the same claim pattern that already
protects against concurrent workers. This mirrors `master_refresh_runs`
and `activation_run_markers`' own already-proven redeploy-safety, not a
new guarantee being invented for this pipeline.

### Observability

- `game_postgame_ingestion_state` itself **is** the primary observability
  surface -- no new dashboard or log-mining required to answer "what's the
  state of every game right now."
- Structured log line per state transition (`game_id`, `provider_name`,
  `from_state`, `to_state`, `http_status`, `attempt_count`, `timestamp`) --
  consistent with this project's existing logging conventions, ties a
  Railway log trace directly to a specific durable-state row.
- Existing Sentry wiring (already live on every backend service) captures
  unhandled exceptions in the worker the same way it does everywhere else
  in this codebase -- no new error-tracking integration needed.

### Monday-morning proof

One query, grouping `game_postgame_ingestion_state` by `state` for every
game whose `kickoff_at` fell on Sunday, answers exactly what HQ asked for:

```sql
SELECT g.id, g.home_team, g.away_team, g.kickoff_at,
       s.state, s.attempt_count, s.captured_at, s.quarantine_reason
FROM games g
LEFT JOIN game_postgame_ingestion_state s
  ON s.game_id = g.id AND s.provider_name = 'mysportsfeeds'
WHERE g.kickoff_at::date = '<that Sunday>'
ORDER BY g.kickoff_at;
```

- `confirmed_complete` -> fully captured and persisted, zero quarantines.
- `partially_confirmed` -> captured, but one or more players quarantined
  (join `player_identity_quarantine` on `game_id` for exactly which ones
  and why).
- `capture_failed_permanent` / stuck in `eligible_for_postgame_check` past
  its budget -> never successfully captured, visible with its full attempt
  history (`attempt_count`, `last_http_status`, `last_error`).
- No row at all for a game that should have one -> never attempted (a
  scheduling/deployment problem, immediately visible as an anomaly rather
  than a silent gap).

This is a durable, queryable record from the moment each event happens --
not a Monday-morning reconstruction from logs.

---

## Required schema/code changes (named, not applied this pass)

**Schema (design only):**
1. `game_postgame_ingestion_state` -- new table, §2.
2. `player_identity_quarantine` -- new table, §3.
3. `team_provider_ids` unique constraint widened to
   `(team_id, provider_name, provider_team_id)` -- §4, confirmed still the
   correct minimal fix, now load-bearing for this design rather than
   optional.
4. One-time real-data backfill of all 32 teams' numeric MSF
   `provider_team_id` (data-only, no migration beyond #3) -- §4.

**Code (design only):**
1. A pure eligibility function (no I/O), mirroring the
   `point_in_time.py` convention already established, computing state
   transitions from `kickoff_at` + current time + the existing state row.
2. A Postgame MSF Boxscore Worker -- either an extension of the existing
   Postgame Ingestion Worker's provider set (3E-8 precedent, same worker,
   `mysportsfeeds` as a second provider alongside its current one) or a
   parallel MSF-specific cron-dispatched worker sharing the same pattern --
   this choice is an implementation-time decision, not a design blocker.
3. An automated identity-activation wrapper around the existing
   `ensure_player`, adding the collision/team/name-similarity guardrails
   from §3 as pre-checks before it is ever called.
4. A real `MYSPORTSFEEDS_API_KEY` wired as a standing Railway environment
   variable on whichever service hosts the new worker -- every MSF call to
   date has gone through the temporary-diagnostic-and-flag pattern, which
   is not a credential story a permanent worker can reuse.

---

## Concrete remaining blockers (only real ones, nothing speculative)

1. **`team_provider_ids` widening + 32-team numeric-ID backfill not yet
   applied.** Blocks automated team resolution for every team pair except
   NE/SEA (already manually resolved). This is the one schema change this
   design actually requires -- everything else in this document can be
   built against the existing schema.
2. **No standing MSF credential wired to any always-on service.** Every
   MSF call so far has used the temporary-diagnostic pattern (flag ->
   deploy -> marker -> reset). A permanent Sunday worker needs
   `MYSPORTSFEEDS_API_KEY` set durably, which is a credential-provisioning
   step, not a design gap.
3. **MSF's actual rate-limit/plan terms are not confirmed.** The
   concurrency and cadence numbers in this design (2-3 concurrent, 30-minute
   ticks, 128-call worst-case ceiling) are conservative defaults, not
   validated against MSF's real published limits for this project's plan
   tier -- should be confirmed before Sunday so the worst-case ceiling is
   known to fit inside whatever the plan actually allows.
4. **No prior automated end-to-end run of this exact pipeline exists.**
   Every piece (`parse_game_boxscore`, `persist_player_stats`, `ensure_player`)
   is individually proven on real data; this design is the first time they
   are proposed to run together, unattended, across many games. A staged
   dry run against one or two real games before trusting it for a full
   Sunday slate is a reasonable implementation-time step, not a design gap
   in itself.

None of these are data-integrity concerns with the design -- they are
concrete, named prerequisites (one schema change, one credential, one
confirmation, one dry run) standing between this design and a safe first
build.
