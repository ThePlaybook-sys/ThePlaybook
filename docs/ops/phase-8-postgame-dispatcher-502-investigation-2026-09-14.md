# Postgame Dispatcher — 502 Investigation (2026-09-14)

MANSA HQ directive: investigate, READ-ONLY, the HTTP 502 the `cron-msf-
postgame` dispatcher's own client (`cron_dispatch`) received approximately
5 minutes into its first natural scheduled invocation (2026-09-14 21:00
UTC). **Zero MySportsFeeds calls made in this pass beyond what the cron
schedule itself already fired on its own before this investigation
began. No manual invocation, no retry, no repair, no redeploy, no config
change.** Every finding below is either a direct live read (Supabase,
Railway logs/deployment state) or an inference explicitly labeled as such.

## 1. What actually happened inside `sports-intel-layer`

The request **completed successfully, end to end, server-side** — the
502 was not an application failure. Evidence:

- `sports-intel-layer`'s own deployment (`8acc04ed-...`) has been running
  continuously since 2026-09-14 13:10:57 with **zero restarts or new
  deployments** through and past the 502 (confirmed via `list-deployments`
  showing exactly one active entry for that service across the whole
  window) — ruling out a process/container crash at the origin.
- `game_postgame_ingestion_state` shows all 4 games claimed in this tick
  reached `confirmed_complete` with `error_classification=null`,
  `last_error=null` — the exact clean-finish signature
  `run_msf_postgame_capture`/`_finish_processing_completed_game` produce
  only on an uninterrupted, exception-free run through raw capture,
  validation, identity activation, and persistence for every player.
- Two of the four games' own `updated_at` timestamps
  (`991b9a9f`=21:05:08, `c675d23b`=21:06:42) are **after** the 502 the
  client logged at 21:05:04 — the server kept working and finished
  correctly after the client had already been told the connection failed.

**Honest caveat**: `sports-intel-layer`'s own HTTP access log, as returned
by this session's log tooling, shows no line at all for `POST /v1/
internal/msf-postgame/dispatch` in this window, even though nearby
`odds-worker` calls appear on both sides of it. This is almost certainly a
sampling/window limit of the log tool itself (the same tool also misses
multiple expected `news-worker` cycles in the same excerpt), **not**
evidence the request never reached the app -- the database is the
authoritative record here, and it proves conclusively that the app did
receive, process, and correctly complete the request for at least all 4
games.

## 2 & 3. Games claimed before the 502, and their exact state

All 4 claimed simultaneously (`last_attempt_at = 2026-09-14 21:00:04.239878+00`
-- one `now` computed once per tick and passed to every game, expected
behavior, not a bug):

| Game | State | attempt_count | raw_capture_id | MSF call | Raw evidence | Player stats | Completed |
|---|---|---|---|---|---|---|---|
| BUF@HOU | confirmed_complete | 1 | `4cb50d14-...` | yes | yes (1 row) | 94 rows | yes (21:01:45) |
| CHI@CAR | confirmed_complete | 1 | `e11e0df4-...` | yes | yes (1 row) | 95 rows | yes (21:03:31) |
| NYJ@TEN | confirmed_complete | 1 | `3a2fb532-...` | yes | yes (1 row) | 93 rows | yes (21:05:08) |
| TB@CIN | confirmed_complete | 1 | `c3936855-...` | yes | yes (1 row) | 92 rows | yes (21:06:42) |

Zero quarantines across all 4 (`player_identity_quarantine` checked per
game, all 0). Zero errors. Exactly one `game_events` row per game (no
duplicate raw captures).

## 4. Exact total MSF calls from this cron invocation

**4** -- one per game, each with a distinct `raw_capture_id` and
`attempt_count=1`. No local transient retry was needed for any of the
four (each succeeded on its first HTTP round trip to MSF).

## 5. Root cause of the 502

**HTTP/proxy/request-duration timeout on the path between `cron-msf-
postgame`'s client and `sports-intel-layer`'s public domain -- not an
application exception, not a process/container failure, not a broader
Railway infrastructure outage.** Reasoning, from the evidence above:

- **Not an application exception**: a Python exception mid-loop would
  have left the later games completely untouched (the dispatcher's `for`
  loop has no exception handling of its own, so an uncaught error stops
  the whole request). Instead, all 4 games finished cleanly, 2 of them
  after the client already saw a 502.
- **Not a process/container failure**: `sports-intel-layer` never
  restarted; one continuous deployment throughout.
- **Not a broader Railway outage**: `odds-worker` calls to the same
  domain succeeded normally at 21:00:19 and 21:15:22, immediately
  bracketing the failed window.
- **Consistent with a timeout**: the 502 landed at 21:05:04, almost
  exactly 5 minutes (300s) after the dispatch request began (~21:00:04)
  -- a common default gateway/edge timeout value -- while the client's
  own `httpx` timeout was already bumped to 600s in this pass's own code
  (`apps/workers/app/cron_dispatch.py`), meaning the client itself was
  still willing to wait. Something *between* the client and the origin
  cut the connection at ~5 minutes regardless of the client's own patience
  and regardless of the origin's continued, successful work -- the
  textbook signature of an intermediate reverse-proxy/gateway timeout,
  most plausibly Railway's own edge layer in front of the **public**
  `sports-intel-layer-dev.up.railway.app` domain that `CRON_DISPATCH_
  BASE_URL` currently points at (as opposed to Railway's private network,
  which every other same-project service-to-service call in this
  codebase already uses and which typically has no such intermediate
  proxy). This session's tooling cannot directly inspect Railway's own
  edge/proxy logs, so this is the best-evidenced explanation available,
  not a certainty -- flagged as inference, not fact.

## 6. Did synchronous sequential batch processing exceed a request-duration boundary?

**Yes.** Real, measured wall-clock duration for the 4-game batch: from
request start (~21:00:04) to the last game's completion (21:06:42) is
**~6 minutes 38 seconds** -- longer than the ~5-minute boundary the 502
appeared at. `MAX_GAMES_PER_DISPATCH_TICK=4` was sized off the single
SF@LAR data point (~2 minutes/game); four real games at realistic,
slightly-varying per-game durations pushed the aggregate past whatever
that intermediate boundary actually is.

## 7. Did processing continue after the client received the 502?

**Yes, proven directly.** `NYJ@TEN` finished at 21:05:08 (4 seconds after
the 502) and `TB@CIN` finished at 21:06:42 (98 seconds after) -- both
reached `confirmed_complete` with zero errors, fully after the client-side
502. The origin kept running the request to completion regardless of the
client connection's fate.

## 8. Would another natural tick risk a duplicate MSF call?

**For already-`confirmed_complete` games: no -- proven live, not just
theoretically.** A second natural tick already fired on its own regular
schedule (21:15/21:17, deployment `2e7e0d17-...`) while this investigation
was underway. It selected exactly 2 **new, previously-untouched** games
(`BAL@IND`, then `ATL@PIT`) and did **not** re-touch any of the 4 games
already at `confirmed_complete` -- because `select_due_msf_postgame_games`
only ever selects `scheduled` / `eligible_for_postgame_check` / `validated`
rows, and `confirmed_complete` is excluded by construction. This is direct
live confirmation that the dispatcher cannot duplicate a call against a
finished game.

**For a game left at `validated` (raw captured, COMPLETED, persistence
not yet finalized) when a new tick starts: no new MSF call, by design --
consistent with observed behavior, not freshly re-proven this pass.**
`run_msf_postgame_capture`'s own resume path reads the already-preserved
raw payload via `raw_capture_id` and reprocesses persistence idempotently
(`upsert_player_stat_row_if_changed` per player) -- it never re-fetches
from MSF. This is the same guarantee already proven in the existing test
suite (`test_msf_postgame_worker.py`) and demonstrated conceptually in the
SF@LAR idempotency proof; this pass did not need to re-derive it, since
no game reached a genuinely stuck `validated` state long enough to
directly re-exercise it live (the one game sitting at `validated` during
this investigation, `ATL@PIT`, was mid-flight on its very first attempt,
not a resumed second attempt).

**Real, disclosed residual risk, not yet observed but structurally
possible**: if a tick's own HTTP request keeps running server-side past
the ~5-minute proxy boundary (as just proven it does) AND a second natural
tick fires 15 minutes later while the first is *still* running, the
second tick's own selection query would simply skip every game the first
tick has already claimed (`capture_in_progress`/`validated` are excluded
from `_DISPATCHABLE_STATES` or make zero-call by design respectively) --
so no duplicate provider call would result even in that overlap case. This
matches the code's own design intent but was not independently re-derived
against a live overlapping-tick scenario in this pass.

## Current exact state of all 13 Sunday games (live snapshot, still moving)

**This table is a snapshot taken during this investigation while the
second natural tick was still in progress on its own schedule -- it was
not paused or waited on further, per HQ's explicit instruction to stop
observing and investigate instead.**

| Matchup | State | attempt_count | Player rows | Notes |
|---|---|---|---|---|
| CHI@CAR | confirmed_complete | 1 | 95 | tick 1 |
| TB@CIN | confirmed_complete | 1 | 92 | tick 1 |
| NO@DET | scheduled | 0 | 0 | not yet attempted |
| BUF@HOU | confirmed_complete | 1 | 94 | tick 1 |
| BAL@IND | confirmed_complete | 1 | 92 | tick 2 |
| CLE@JAX | scheduled | 0 | 0 | not yet attempted |
| ATL@PIT | validated | 1 | 82 (in progress) | tick 2, mid-flight as of snapshot |
| NYJ@TEN | confirmed_complete | 1 | 93 | tick 1 |
| MIA@LV | scheduled | 0 | 0 | not yet attempted |
| GB@MIN | scheduled | 0 | 0 | not yet attempted |
| WAS@PHI | scheduled | 0 | 0 | not yet attempted |
| ARI@LAC | scheduled | 0 | 0 | not yet attempted |
| DAL@NYG | scheduled | 0 | 0 | not yet attempted |

**6/13 touched** (5 `confirmed_complete`, 1 `validated` mid-flight),
**7/13 still `scheduled`, untouched, awaiting a future natural tick.**
Zero failures, zero quarantines, zero duplicate rows/captures anywhere in
either tick. Total real MSF calls across both ticks so far: **6** (4 from
tick 1 + 2 from tick 2 as of this snapshot).

## Recommendation

The dispatcher's actual behavior is safe on every property this pass
could check: no duplicate calls, no data corruption, no lost work, correct
skip-of-finished games, and continued-to-completion server-side behavior
even through the timeout. **The only real defect found is cosmetic but
important**: Railway's own reported cron health (`cronFailed`/`CRASHED`)
is misleading -- it reflects the client-side 502, not the actual outcome,
which was a full success. Left uncorrected, this could cause a future
operator (human or automated) to misjudge dispatcher health from Railway's
UI alone. Two independent, not-mutually-exclusive fixes exist for the
underlying timeout (neither implemented in this pass, per instruction):
point `CRON_DISPATCH_BASE_URL` at Railway's private network instead of
the public domain, and/or lower `MAX_GAMES_PER_DISPATCH_TICK` so a tick's
real duration comfortably stays under whatever the actual proxy boundary
is. Recommend HQ decide which (or both) before authorizing further
automatic recovery ticks, though nothing observed this pass indicates the
remaining 7 games are at risk of being processed incorrectly if the
schedule is simply left running as-is.

## Out of scope, exactly as instructed

No manual dispatcher invocation. No retry of the failed tick. No
additional MSF calls beyond what the cron schedule fired on its own. No
state repair. No redeploy. No configuration change. No Phase 7, Context
Intelligence, or recommendation work touched.
