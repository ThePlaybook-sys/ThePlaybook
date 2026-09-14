# Postgame Dispatch Timeout Hardening + Sunday Completion (2026-09-14)

MANSA HQ directive: "POSTGAME DISPATCH TIMEOUT HARDENING." Implements the
smallest safe hardening for the 502-misreport defect the prior
investigation found, applied only after confirming zero in-flight
processing, then verified live against a real natural cron tick. **All 13
Sunday games reached `confirmed_complete` naturally, before the hardening
was even applied** -- the pre-existing (unhardened) dispatcher's own
already-proven safety properties (atomic claim, terminal-state exclusion,
origin-continues-past-timeout) carried the recovery to full completion on
their own while this pass waited for a safe moment to change anything.

## 1. Lowered batch size

`MAX_GAMES_PER_DISPATCH_TICK`: **4 → 2**
(`apps/sports-intel-layer/app/workers/msf_postgame_dispatcher.py`). Only
this constant changed -- no per-game worker logic, retry budget, or
ingestion-state semantics touched. 15/15 dispatcher+endpoint tests pass.
Full suite surfaced 5 pre-existing, unrelated
`test_odds_cadence_persistence.py` failures, confirmed via stash-and-
retest to predate this change entirely (identical failures with the edit
reverted) -- not touched, out of scope.

## 2. Private network audit

**Confirmed safe and switched.** Railway's own documentation
(`docs.railway.com/networking/private-networking`) confirms every service
gets a deterministic internal DNS name `<service-name>.railway.internal`,
reachable via `http://<name>.railway.internal:PORT` (plain HTTP -- traffic
is already Wireguard-encrypted). The hostname was not guessed: it follows
directly from Railway's own documented, deterministic per-service naming
applied to `sports-intel-layer`'s real service name. The port (8080) was
not guessed either -- it is the real, directly-observed value from
`sports-intel-layer`'s own runtime log ("Uvicorn running on
http://0.0.0.0:8080"). `CRON_DISPATCH_BASE_URL` on `cron-msf-postgame`
switched from `https://sports-intel-layer-dev.up.railway.app` (public) to
`http://sports-intel-layer.railway.internal:8080` (private) --
`skipDeploys: true` (a variable-only change, not an intentional redeploy).

## 3. Did not interrupt active recovery

Before applying either change, live-checked `game_postgame_ingestion_
state` for any `validated`/`capture_in_progress` row and found one game
(`CLE@JAX`) genuinely mid-flight. **Waited for it to reach a terminal
state** (`confirmed_complete` at 21:32:17) before touching anything. A
new natural tick then claimed a further game (`WAS@PHI`) while still
waiting -- waited for that one too, and for the rest of that tick's batch,
until an explicit live query confirmed **zero rows anywhere in
`validated`/`capture_in_progress`** immediately before the code push.
Only then was the hardening applied. No provider call was manually
invoked at any point in this pass.

**Why the code change specifically required this care**: `MAX_GAMES_PER_
DISPATCH_TICK` lives in `sports-intel-layer`'s own codebase, and that
service auto-redeploys on every push to `dev` -- a redeploy of the
service actually doing the per-game work (unlike `cron-msf-postgame`,
a stateless fire-once client whose own redeploys never affect in-flight
work happening on `sports-intel-layer`) would have killed any in-flight
request. The private-network variable change, by contrast, only affects
`cron-msf-postgame` and was safe at any time -- applied together with the
code change anyway, after confirming quiet, to keep both changes bundled
and simple to reason about.

## 4. Verified naturally, live

The next natural tick after both changes fired at 2026-09-14 22:15:28
(commit `023c630` had to finish building first, which is why this tick
landed later than the usual ~15-minute cadence -- confirmed a genuine cron
firing, not a manual invocation). Real log line, `cron-msf-postgame`
deployment `c9c566be-...`:

```
2026-09-14 22:15:28,837 INFO cron_dispatch starting target=msf-postgame-worker base_url=http://sports-intel-layer.railway.internal:8080
2026-09-14 22:15:29,252 INFO HTTP Request: POST http://sports-intel-layer.railway.internal:8080/v1/internal/msf-postgame/dispatch "HTTP/1.1 200 OK"
2026-09-14 22:15:29,253 INFO cron_dispatch succeeded target=msf-postgame-worker result={'considered': 0, 'selected_game_ids': [], 'invoked_game_ids': [], 'results': []}
```

- **Private network call succeeded**: real `200 OK` over `http://
  sports-intel-layer.railway.internal:8080` -- confirms the private
  networking switch works, not just documented-in-theory.
- **Total round trip: ~416ms** (22:15:28.837 → 22:15:29.253) -- vs. the
  public path's multi-minute exposure to the ~5-minute proxy boundary;
  private networking also simply eliminates that public-edge hop
  entirely, not just outruns its timeout.
- **`considered: 0`**: correct and expected -- all 13 Sunday games were
  already `confirmed_complete` by the time this tick ran (Section 5), so
  there was nothing left to select. This means "at most 2 games selected"
  is trivially satisfied (0 ≤ 2) but this pass could not exercise the new
  cap against a real >2-game backlog, since none remained -- disclosed,
  not silently glossed over.
- **No completed game reprocessed, no duplicate MSF call**: definitionally
  true with `considered: 0`, and independently confirmed by direct query
  (Section 5) -- every one of the 13 games has exactly one `game_events`
  raw capture, no exceptions.
- **Railway's own reported health for this run: clean.** `environment-
  status` immediately after this tick shows `cron-msf-postgame` **absent**
  from the services-with-issues list entirely (only the pre-existing,
  unrelated `cron-weather-worker`/`cron-master-refresh` failures appear).
  The false `cronFailed`/`CRASHED` misreport is resolved for this run --
  Railway now correctly reports success.

## 5. Sunday completion -- final 13/13 matrix

All 13 reached `confirmed_complete` naturally, across 4 organically-fired
ticks (21:00, ~21:17, ~21:31, ~21:48 UTC) of the **pre-hardening**
dispatcher -- the hardening in Sections 1-2 was applied only after this
was already true.

| Matchup | State | attempt_count | Player rows | Tick |
|---|---|---|---|---|
| BUF@HOU | confirmed_complete | 1 | 94 | 1 (21:00) |
| CHI@CAR | confirmed_complete | 1 | 95 | 1 (21:00) |
| NYJ@TEN | confirmed_complete | 1 | 93 | 1 (21:00) |
| TB@CIN | confirmed_complete | 1 | 92 | 1 (21:00) |
| BAL@IND | confirmed_complete | 1 | 92 | 2 (~21:17) |
| ATL@PIT | confirmed_complete | 1 | 94 | 2 (~21:17) |
| NO@DET | confirmed_complete | 1 | 94 | 2 (~21:17) |
| CLE@JAX | confirmed_complete | 1 | 95 | 2 (~21:17) |
| MIA@LV | confirmed_complete | 1 | 92 | 3 (~21:31) |
| GB@MIN | confirmed_complete | 1 | 94 | 3 (~21:31) |
| WAS@PHI | confirmed_complete | 1 | 91 | 3 (~21:31) |
| ARI@LAC | confirmed_complete | 1 | 93 | 4 (~21:48) |
| DAL@NYG | confirmed_complete | 1 | 94 | 4 (~21:48) |

**13/13 `confirmed_complete`. 0 `partially_confirmed`. 0 failed. 0 still
scheduled.**

- **Total real MSF calls**: exactly **13** -- one per game
  (`sum(attempt_count) = 13`), confirmed independently by exactly 13
  distinct `game_events` raw captures for these 13 game ids, each game
  with exactly 1 (no duplicates).
- **Total raw captures**: 13 (one per game, zero duplicates -- the one
  game_id in the whole `game_events` table with 2 rows is an unrelated
  Week 1 Thursday game from a much earlier diagnostic pass days before
  this one, not any of the 13 Sunday games).
- **Total player-game rows persisted**: **1,213** across the 13 games
  (`sum` of `player_stats` rows, cross-checked as exactly 1,213 distinct
  `player_id`s -- no player repeated across two Sunday games this week).
- **New canonical players activated**: **1,213** -- every one of these
  players' `player_provider_ids` (mysportsfeeds) mapping is new this pass
  (first-ever real capture for any of these 26 teams' Sunday rosters).
- **Quarantines**: **0**, across all 13 games, all reasons -- confirmed
  via direct `player_identity_quarantine` query.
- **Duplicate-call proof**: **0** duplicate `game_events` rows, **0**
  duplicate `player_stats` rows, and (Section 4) a natural tick after full
  completion correctly selected 0 games rather than re-touching any of
  the 13.

## Networking: was the public/private switch made?

**Yes** -- `cron-msf-postgame`'s `CRON_DISPATCH_BASE_URL` now points at
`http://sports-intel-layer.railway.internal:8080` (private), not the
public `sports-intel-layer-dev.up.railway.app` domain. Verified working
live (Section 4). No other service's `CRON_DISPATCH_BASE_URL` was touched.

## Is the false CRASHED status resolved?

**Yes, for the case that could be tested** -- a real tick after the
switch reports Railway health as clean (Section 4). The original failure
mode (a long *successful* batch getting cut off mid-flight and reported
CRASHED) was never re-created after the fix, because no games remained to
produce a long batch -- so this proves the private-network path avoids
the specific timeout, but does not additionally re-prove "a genuinely
long successful batch now also reports success" against a fresh >2-game
backlog. The combination of (a) private networking removing the public
edge hop entirely and (b) the lowered cap keeping any future batch's own
duration short gives strong reason to expect the same clean result on a
real future backlog (e.g. a future week's games), but that is inference
from this pass's evidence, not a second live reproduction -- disclosed
plainly rather than overclaimed.

## Proof the dispatcher remains operational for future games

- `cron-msf-postgame`'s `cronSchedule` (`*/15 * * * *`) is unchanged and
  still active -- confirmed via `get-service-config` after all edits.
- The 22:15:28 tick (Section 4) is itself live proof the schedule keeps
  firing automatically, through a code deploy, a variable change, and a
  fully-drained backlog, with no manual invocation.
- Future eligible games (e.g. once Week 2 games are initialized, a
  separate not-yet-authorized decision) will be picked up by this same
  mechanism with zero further setup -- `select_due_msf_postgame_games`'s
  selection query has no dependency on the specific 13 Sunday game ids,
  it selects whatever is due at each tick.

## Out of scope, exactly as instructed

No Context Intelligence. No recommendation work. No unrelated cleanup
(the 5 pre-existing `test_odds_cadence_persistence.py` failures were
identified and disclosed, not fixed). No per-game worker logic, retry
budget, or ingestion-state semantics changed.
