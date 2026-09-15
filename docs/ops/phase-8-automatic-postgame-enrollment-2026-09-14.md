# Automatic Postgame Enrollment (2026-09-14 → 2026-09-15)

MANSA HQ directive: "AUTOMATIC POSTGAME ENROLLMENT." Implements the
smallest deterministic mechanism that makes the existing MSF postgame
dispatcher self-sustaining — no more manually-initialized rows for any
future game, DEN@KC included. **Zero manual MSF calls. Zero manual row
initialization for DEN@KC.** All provider calls this pass were made by
the existing, unmodified permanent worker, triggered entirely by the
existing cron schedule.

## Root cause

`select_due_msf_postgame_games` (the dispatcher's own selection query)
only ever reads rows that already exist in `game_postgame_ingestion_
state`. Nothing anywhere automatically created the *first* `scheduled`
row for a newly-relevant game — every row that existed before this pass
(13 Sunday games, SF@LAR) came from a one-time, manually-authorized SQL
initialization, not a self-sustaining mechanism. Confirmed live before
building anything: DEN@KC had no ingestion-state row despite having a
real MSF mapping.

## Implementation location

`apps/sports-intel-layer/app/workers/msf_postgame_dispatcher.py` — the
same module the Postgame Dispatcher + Sunday Recovery pass already
introduced. New: `select_unenrolled_eligible_games` (read-only discovery)
and `MAX_ENROLLMENTS_PER_DISPATCH_TICK` (bounding constant), both wired
into `dispatch_due_msf_postgame_games` as a distinct Phase 1, run before
the existing Phase 2 (selection + bounded dispatch, unchanged). No new
service, no new cron, no new table — the existing `cron-msf-postgame`
schedule now does strictly more per tick, nothing else changed about how
it fires.

## Enrollment eligibility rule (deterministic, uses only persisted data)

A canonical game is enrolled once, and exactly once, when all three hold:

1. A real `game_provider_ids` row exists for `mysportsfeeds`.
2. `games.scheduled_start <= now()` — kickoff has occurred. This is the
   literal reading of "eligible for the postgame pipeline": before
   kickoff there is no completed game to check yet.
3. No `game_postgame_ingestion_state` row exists yet for `(game_id,
   mysportsfeeds)`.

A qualifying game gets exactly one row created via the **existing,
unmodified** `ensure_scheduled_row` — enrollment invents no new mutation
primitive, it only discovers which `game_id`s should be handed to a
function that already knew how to enroll one safely. This is why every
required safety property holds with zero new code for the property
itself:

- **Idempotent / duplicate-safe / concurrency-safe**: inherited entirely
  from `ensure_scheduled_row`'s own pre-existing check-then-insert (never
  an upsert) plus the real `UNIQUE (game_id, provider_name)` constraint's
  409-recovery path — confirmed live via `pg_constraint`, and now covered
  by a dedicated test (`test_ensure_scheduled_row_recovers_from_
  concurrent_insert_race`) that didn't exist before this pass.
- **Restart-safe**: nothing about eligibility depends on dispatcher-local
  memory; every tick re-derives candidates fresh from persisted data.
- **Generic, not hard-coded**: the query has no game-specific literal
  anywhere — proven live twice over (Section "DEN@KC proof" below).
- **Bounded**: `MAX_ENROLLMENTS_PER_DISPATCH_TICK=20`, separate from the
  real-work cap (`MAX_GAMES_PER_DISPATCH_TICK=2`) since enrollment itself
  never makes a provider call — a mass-mapping event still can't create
  an unbounded burst of inserts in one tick (§1.1 principle #11's
  "bounded workload" discipline, applied at this cheaper tier).
- **Claim protection / retry limits / terminal-state exclusion / raw
  preservation / quarantine behavior**: all completely untouched — a
  freshly-enrolled game is never claimed or fetched in the same tick that
  enrolls it (its own `next_eligible_attempt_at`, computed via the
  existing `first_check_at`, is always in the future relative to its own
  just-passed kickoff), and every game that does become due goes through
  the exact same unmodified `run_msf_postgame_capture` path every other
  game already did.

## Tests

16 new tests, all passing, zero real network calls in any of them:

- **`select_unenrolled_eligible_games`** (6): finds a mapped/unenrolled/
  past-kickoff candidate; excludes an already-enrolled game regardless of
  its state; excludes an unmapped game (and proves the short-circuit —
  the enrolled-check and games lookup are never even called when nothing
  is mapped); excludes a mapped-but-future game (proves the eligibility
  rule itself, not just the mapping check); orders oldest-kickoff-first;
  raises on a genuine read failure.
- **`dispatch_due_msf_postgame_games` enrollment integration** (4):
  enrolls via the real `ensure_scheduled_row` call shape and does NOT
  invoke the worker for it in the same tick; repeated dispatch calls
  against a still-unenrolled candidate don't skip re-attempting discovery
  (restart-safety, with the real duplicate-prevention delegated to
  `ensure_scheduled_row`'s own proven idempotency); the enrollment cap is
  respected independently of the dispatch cap; enrollment and dispatch
  phases don't interfere with each other in the same tick.
- **`ensure_scheduled_row` 409-race recovery** (1, in `test_game_
  postgame_ingestion_state_persistence.py`): two racing callers, real
  unique-constraint conflict shape, same row returned to both, never a
  duplicate, never a raise.
- **Response-shape updates** (existing endpoint tests) for the new
  `enrolled_game_ids` field.

Full `apps/sports-intel-layer` suite: **884 collected, 879 passing** —
the same 5 pre-existing, unrelated `test_odds_cadence_persistence.py`
failures already disclosed in the prior two passes, confirmed unrelated
again (this pass touched none of that module).

**Live proof, existing rows unchanged**: the 13 Sunday `confirmed_
complete` rows and SF@LAR were re-read immediately after deploying this
change and again after the first several natural ticks — every `state`/
`attempt_count`/`raw_capture_id` byte-identical to their pre-deployment
values. Enrollment's own `WHERE ... game_postgame_ingestion_state IS
NULL` shape structurally cannot touch a row that already exists.

## DEN@KC — automatic-enrollment proof

**No manually-created row.** Confirmed live, immediately after
deployment: `game_postgame_ingestion_state` had exactly one row missing —
DEN@KC — same as before this pass, deliberately left alone.

**The very first natural tick after kickoff enrolled it automatically**:

| | |
|---|---|
| Kickoff | 2026-09-15 00:15:00 UTC |
| Enrollment tick | 2026-09-15 00:16:05 UTC (**66 seconds after kickoff**) |
| Resulting state | `scheduled`, `attempt_count=0` |
| `next_eligible_attempt_at` | `2026-09-15 03:45:00 UTC` (= kickoff + 3h30m, via the existing, unmodified `first_check_at` — untouched by this pass) |
| Manual action taken | **None** |

This is exactly the generic mechanism at work, not a DEN@KC special case
— the same query, same code path, same tick that enrolled DEN@KC had
already proven itself hours earlier on a completely different game (next
section).

Per HQ's own instruction, normal cron automation is left alone from here:
DEN@KC's actual completion check will fire automatically at 03:45 UTC
(and up to 3 more times an hour apart if not yet COMPLETED, per the
existing, unchanged call-control policy) — no further action needed or
taken by this pass.

## Provider calls made during this pass

**Not zero — one real, unplanned-but-correct call, and it is exactly the
proof the mechanism is genuinely generic.** Immediately upon this
change's first live tick (2026-09-14 23:02:07 UTC, well before DEN@KC
even kicked off), the same generic query discovered a second real
backlog item: **NE@SEA** (MSF game `163541`), the original Gate B fixture
game from 2026-09-10 — real, mapped, kickoff long passed, but never
formally enrolled into `game_postgame_ingestion_state` before (its only
prior evidence was two informal diagnostic-era `game_events` captures
from days earlier, made via a different, unrelated code path entirely).
The same tick's dispatch phase found it immediately due (`next_
eligible_attempt_at` computed from a kickoff days in the past) and made
one real, new MSF call for it.

**Outcome, verified clean**: `state='confirmed_complete'`, `attempt_
count=1`, exactly one new `game_events` raw capture, **162 real player-
stat rows**, **0 quarantines**, 0 errors. A live sweep immediately after
confirmed this was the *only* other such backlog item in the entire
database — nothing else was silently mapped-but-unenrolled.

This was not anticipated when DEN@KC was named as "the next clean
forward-looking proof," but it is the correct, intended behavior of a
mechanism explicitly required to be "generic for future NFL games, not
hard-coded to DEN@KC" — flagged here in full, not minimized, because an
unplanned real provider call deserves exactly that regardless of how
clean the outcome was.

**Total real MSF calls this pass: 1** (NE@SEA). **DEN@KC: 0 calls so
far** (correctly not due until 03:45 UTC) — will make its own calls
automatically, without further action, per the unchanged existing
schedule.

## Is the postgame pipeline now truthfully self-sustaining?

**Yes.** Two independent real games — one a previously-missed backlog
item discovered without being named, one a genuinely future game whose
kickoff hadn't even happened when this pass began — were both enrolled
automatically, by the same generic code path, with zero manual
intervention for either. The system no longer depends on a human (or an
HQ directive) naming which `game_id` needs a row: any real, MSF-mapped,
kicked-off NFL game will be found and enrolled by the existing cron
schedule on its own, and will then flow through the exact same, already-
proven claim → fetch → raw-preservation → validation → identity/stat-
persistence → terminal-state chain every prior game in this pipeline has
already gone through.

## Documentation

`apps/sports-intel-layer/app/workers/msf_postgame_dispatcher.py`'s own
module docstring now states the full chain explicitly: **canonical game +
provider mapping → automatic enrollment → dispatcher → per-game worker →
raw capture → validation → identity/stat persistence → terminal durable
state** — the "Automatic Enrollment" docstring section added by this
pass names every stage and which module/function owns it. No Volume 2
amendment was made this pass (HQ's directive scoped this task to
implementation + test + live proof, distinct from the prior pass's
Blueprint-level architecture lock) — Volume 2 §8's existing MSF Postgame
Dispatcher note remains accurate as written and is not contradicted by
this addition; a future pass may fold this mechanism into that note if
HQ wants it Blueprint-level too.

## Out of scope, exactly as instructed

No Context Intelligence. No recommendation work. No unrelated debt
cleanup (the previously-recorded debt items are untouched, not
re-litigated here). No manual DEN@KC row. No manual MSF call — the one
real call made (NE@SEA) was fired entirely by the existing, unmodified
automatic cron/dispatcher/worker chain, not by this session directly.
