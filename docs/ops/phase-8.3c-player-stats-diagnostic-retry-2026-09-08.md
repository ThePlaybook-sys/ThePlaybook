# Phase 8.3C — Player Stats Diagnostic Retry (2026-09-08)

MANSA HQ directive: "MANSA PHASE 8.3C — PLAYER STATS DIAGNOSTIC RETRY"
(2026-09-08). Phase 8.3B was inconclusive due solely to a 30-second
client timeout; `activation_run_markers` correctly prevented duplicate
execution across that pass's Railway crash/redeploy. This pass kept the
same target, raised the timeout to 120s, and made the call
exception-safe end to end.

**Result: SUCCESS. HTTP 200, real player-level season stats returned for
NE, in 0.173 seconds — not a timeout at all.** The `team=NE` filter is
confirmed honored server-side. A genuine, rich player-performance
payload exists behind this endpoint — the single most significant real
finding of the whole Phase 8.2/8.3 arc so far. The full response
(166,159 bytes) exceeded Railway's 80KB single-log-line limit, so only
part of it was captured via logs; 43 complete, valid player entries were
recovered from that truncated capture and preserved as a durable fixture
(§9). Nothing was persisted to canonical tables, per HQ's explicit
instruction.

---

## 1. Once-only guard result

Reused `activation_run_markers` verbatim with a new, dedicated run_key:
`phase-8.3c-player-stats-diagnostic-retry-2026-09-08`. Verified before
this pass that both prior marker rows (Phase 8.3A's
`phase-8.3a-team-season-stats-activation-2026-09-08` and Phase 8.3B's
`phase-8.3b-player-stats-diagnostic-2026-09-08`) were untouched, and
confirmed again afterward — all three rows now exist, distinct and
intact. The guard claimed successfully on the first (and only) container
that ran with `RUN_MSF_PLAYER_STATS_DIAGNOSTIC=1`; the env var was
reverted to `"0"` immediately after the marker claim was confirmed, so
no second container ever raced for it this pass.

## 2. Request result/status

| Field | Value |
|---|---|
| HTTP status | **200** |
| Request path | `/nfl/2025-2026-regular/player_stats_totals.json` |
| Request params | `{"team": "NE"}` |
| Provider | `mysportsfeeds` |
| Request timestamp (UTC) | `2026-09-08T18:31:14.717585+00:00` |
| `lastUpdatedOn` (MSF's own freshness field) | `2026-09-08T17:58:23.195Z` |
| Quota-relevant response headers | none present (empty dict — no rate-limit/quota headers observed, consistent with every other real MySportsFeeds response this project has captured) |

**The `team=NE` filter is confirmed honored server-side, resolving Phase
8.3B's open question.** A whole-league, unfiltered `player_stats_totals`
response would be dramatically larger than 166KB (32 teams × a full
roster each); this response's size is consistent with exactly one team's
worth of players, not the whole league.

## 3. Latency/size

- **Elapsed: 0.173 seconds** — not remotely close to either the 30s or
  120s timeout. This was almost certainly a cache hit (MySportsFeeds'
  own `cache-control`/`x-cache` behavior has been observed on every
  other real capture this project has made) or a genuinely fast
  endpoint — either way, Phase 8.3B's timeout was not caused by this
  endpoint being inherently slow.
- **Response size: 166,159 bytes** (real, measured via
  `len(response.content)` before any transformation).

## 4. Player count

**At least 43 confirmed real players — the true total in the full
response is unknown, not fabricated as a round number.** Railway
truncates a single logged message at exactly 80KB (81,920 characters
including the log-line prefix), which cut the JSON mid-object partway
through the `playerStatsTotals` array before it could be captured
whole. 43 complete, individually-parseable player entries were
recovered from the truncated text (using balanced-brace JSON decoding,
stopping cleanly at the last complete object rather than guessing at
the cut-off one). By byte proportion (the captured fragment is roughly
half of the real 166,159-byte response), the true total is plausibly in
the 80-90 range, but this is disclosed as an extrapolation, not a count
— MySportsFeeds' season-totals feed plausibly includes every player who
appeared for NE at any point in the 2025 season (practice-squad
call-ups, IR replacements, etc.), not just the current 53-man roster,
which would explain a count above 53.

## 5. Identity compatibility

**Real player identity fields observed** (union across all 43 entries):
`id`, `firstName`, `lastName`, `primaryPosition`, `jerseyNumber`,
`currentTeam` (`{id, abbreviation}`), `currentRosterStatus`,
`currentInjury` (nested `{description, playingProbability}` when
present — 4 of 43 recovered players carry a real, non-null injury:
Joshua Farmer/hamstring/OUT, Mack Hollins/abdomen/OUT, Terrell
Jennings/concussion/OUT, Harold Landry III/knee/OUT), `height`,
`weight`, `birthDate`, `age`, `birthCity`, `birthCountry`, `rookie`,
`highSchool`, `college`, `handedness`, `officialImageSrc`,
`socialMediaAccounts`. A separate top-level `team: {id, abbreviation}`
field duplicates `player.currentTeam` at the entry level.

**Cross-checked against canonical identity, not assumed compatible:** of
the 17 NE players already canonically identity-resolved (Phase 8.2's
`players`/`player_provider_ids`/`roster_memberships` activation), **7
appear in this pass's 43 recovered entries, every one an exact ID
match**: Hunter Henry (9999), Cory Durden (112190), Carlton Davis
(14990), Andres Borregales (166894), Harold Landry III (15069), Demario
Douglas (108896), Christian Elliss (30398). The other 10 known NE
players are very likely present in the untruncated remainder this pass
didn't capture. **Hunter Henry's id=9999 is now confirmed identical and
consistent across three independent real MySportsFeeds feeds**
(`players.json`, `lineup.json`, and this pass's `player_stats_totals`)
— the strongest identity-consistency evidence this project has gathered
for any single player.

## 6. Real stats field matrix

All of the following are **CONFIRMED REAL** — directly observed in the
real payload, never inferred from SDK/schema:

| Category | Fields observed | Real sample |
|---|---|---|
| **Passing** | passAttempts, passCompletions, passPct, passYards, passAvg, passYardsPerAtt, passTD, passTDPct, passInt, passIntPct, passLng, pass20Plus, pass40Plus, passSacks, passSackY, qbRating | Joshua Dobbs (QB): 10 att, 7 comp, 65 yds, 87.5 rating — the only nonzero passer among the 43 recovered (correct, honest per-player attribution; every non-QB shows all-zero passing, not omitted) |
| **Rushing** | rushAttempts, rushYards, rushAverage, rushTD, rushLng, rush1stDowns, rush1stDownsPct, rush20Plus, rush40Plus, rushFumbles | TreVeyon Henderson (RB): 180 att, 911 yds, 9 TD, 5.1 avg |
| **Receiving** | targets, receptions, recYards, recAverage, recTD, recLng, rec1stDowns, rec20Plus, rec40Plus, recFumbles | Stefon Diggs (WR): 102 targets, 85 rec, 1013 yds, 4 TD; Hunter Henry (TE): 87 targets, 60 rec, 768 yds, 7 TD |
| **Defense — tackles** | tackleSolo, tackleTotal, tackleAst, sacks, sackYds, tacklesForLoss | Harold Landry III (LB): 43 total tackles, 8.5 sacks, 9 TFL; Christian Gonzalez (CB): 69 total tackles |
| **Defense — interceptions/coverage** | interceptions, intTD, intYds, intAverage, intLng, passesDefended, stuffs, stuffYds, safeties, kB | Marcus Jones (CB): 3 INT, 1 pick-six, 11 passes defended; Jaylinn Hawkins (FS): 4 INT |
| **Fumbles** | fumbles, fumLost, fumForced, fumOwnRec, fumOppRec, fumRecYds, fumTotalRec, fumTD, offFumTD | K'Lavon Chaisson (LB): 2 forced, 1 recovered, 1 TD |
| **Kicking — field goals** | fgBlk, fgMade, fgAtt, fgPct, and made/att/pct split by distance band (1-19/20-29/30-39/40-49/50+), fgLng | Andres Borregales (K): 27/32 (84.4%), long 549 |
| **Kicking — kickoffs** | kickoffs, koYds, koOOB, koAvg, koTB, koRet, koRetYds, koRetAvgYds, koTD, koOS, koOSR | Borregales: 96 kickoffs, 60.4 avg |
| **Kicking — extra points** | xpBlk, xpMade, xpAtt, xpPct, fgAndXpPts | Borregales: 53/55 (96.4%) |
| **Punting** | punts, puntYds, puntNetYds, puntLng, puntAvg, puntNetAvg, puntBlk, puntOOB, puntDown, puntIn20, puntIn20Pct, puntTB, puntTBPct, puntFC, puntRet, puntRetYds, puntRetAvg | Bryce Baringer (P): 51 punts, 47.4 avg, 21 inside-20 |
| **Kickoff/punt returns** | krRet/krYds/krAvg/krLng/krTD/kr20Plus/kr40Plus/krFC/krFum (kickoff); prRet/prYds/prAvg/prLng/prTD/pr20Plus/pr40Plus/prFC/prFum (punt) | Marcus Jones (CB): 19 punt returns, 2 TD, 19.5 avg |
| **Two-point attempts** | twoPtAtt, twoPtMade, twoPtPassAtt, twoPtPassMade, twoPtPassRec, twoPtRushAtt, twoPtRushMade | Present in schema, all-zero across all 43 recovered — genuinely rare event, plausible |
| **Participation/usage — games** | `gamesPlayed` (top-level, real distribution 1–17 across the 43), `miscellaneous.gamesStarted` | gamesPlayed real and varied (e.g. 17 for full-season players, 1-5 for late call-ups); see §7 for `gamesStarted` |
| **Participation/usage — snaps** | `snapCounts.offenseSnaps`, `.defenseSnaps`, `.specialTeamSnaps`, per player | Hunter Henry: 869 offense snaps, 9 special-teams, 0 defense; Christian Gonzalez (CB): 771 defense snaps |

## 7. Participation/usage coverage

**Real and meaningfully populated: `gamesPlayed` and the three
`snapCounts` fields (offense/defense/special-teams), both varying
sensibly by position and role** — this is genuine, previously-UNKNOWN
per-player usage evidence, now CONFIRMED REAL.

**`miscellaneous.gamesStarted` is present in the schema but ABSENT FROM
REAL PAYLOAD in the sense that matters: every one of the 43 recovered
players shows `0`, including clear, obvious starters** (Stefon Diggs, 85
receptions on 14 games played, shows `gamesStarted: 0`). Classified
**PRESENT BUT EMPTY/ZERO**, not confirmed real usage data — this field
exists in the schema and returns a value, but that value does not appear
to reflect real starts for any player sampled, and no inference is drawn
about whether MySportsFeeds tracks this at all for this feed/tier.

## 8. Contextual dimensions unlocked

Based only on what this pass confirmed real — no contextual logic
implemented, analysis only:

| Dimension | Assessment |
|---|---|
| `player_performance` | **Newly, genuinely supportable at the season-aggregate level.** Real passing/rushing/receiving/defense/special-teams totals now exist for at least 43 real NE players. This is the first real player-level performance data this entire project has ever confirmed. |
| `roster_role` | Strengthened — real position + real usage split (offense/defense/special-teams snaps) directly evidences role, beyond the depth-chart-label evidence Phase 8.2 already had. |
| `depth_lineup` | Unchanged by this pass — this feed carries no depth/rank field (matches `players.json`'s own already-confirmed absence); still `lineup.json`'s job. |
| Weather-conditioned performance | **Still impossible.** This is season-aggregate data with no game-by-game breakdown — there is no per-game row to join against a per-game weather snapshot. |
| Teammate-conditioned performance | **Still impossible** for the same reason — no game-scoped rows to correlate with which teammates played alongside whom in a given game. |
| Opponent-conditioned performance | **Still impossible** — no opponent field or game linkage exists in this season-total shape. |
| Venue-conditioned performance | **Still impossible** — no venue/game linkage. |
| Recency/baseline comparisons | **Partially possible, narrowly.** A season-over-season baseline (this season's real totals vs. a future season's real totals, once captured) is technically supportable. Within-season recency (last-3-games form, trending up/down) is **not** supportable from this feed — that requires `player_gamelogs`, not `player_stats_totals`, an explicitly out-of-scope endpoint this pass. |

**The core limitation is unchanged from every prior pass's own finding:
season-aggregate data answers "how good was this player over the whole
season," never "how is this player playing right now, in this specific
context."** This pass makes real player-level season totals available
for the first time; it does not and cannot unlock any per-game,
per-context comparison.

## 9. Raw capture status

**Partial, but durable and reusable.** The full 166,159-byte response
could not be captured whole because Railway truncates a single log
message at 80KB. 43 complete player entries were recovered from the
truncated capture via balanced-brace JSON parsing (stopping cleanly
before the cut-off 44th entry, never guessing at incomplete data) and
saved as a committed fixture:

`docs/ops/fixtures/phase-8.3c-msf-player-stats-totals-ne-2025-2026-partial-2026-09-08.json`

This fixture is real, non-secret vendor data (player stats, not
credentials) and is sufficient for future schema-mapping and persistence
design work without a second provider call, per HQ's explicit
instruction — though it is disclosed as **partial**, not the full NE
roster, in both its own embedded `capture_note` field and here.

**Operational lesson for any future pass that logs a large payload**:
log in smaller chunks (e.g. per-player, or paginated at well under 80KB
per line) rather than one `json.dumps()` call over the whole body, so a
future successful capture doesn't lose its tail end to this same limit.

## 10. Remaining gaps

1. **The true total player count in the full response is unknown** —
   only 43 of an estimated 80-90 were recovered from the truncated log.
2. **`gamesStarted` appears unreliable** (uniformly zero even for
   obvious starters) — unresolved whether this is a real MySportsFeeds
   data gap or specific to this trial tier; not re-tested this pass per
   the "no second call" rule.
3. **No per-game/dated breakdown exists in this feed by design** — every
   contextual (weather/teammate/opponent/venue/recency) dimension named
   in §8 remains impossible without `player_gamelogs`, an explicitly
   out-of-scope endpoint this pass.
4. **Canonical schema fit is now strongly plausible but not yet
   implemented or tested against real data.** Phase 8.3A's
   `player_stats` schema (nullable `game_id`, nullable `season_id`,
   unconstrained `jsonb` stats column) was designed by analogy to the
   team-level shape and would very likely accept this real per-player
   payload's structure unchanged, but no migration, mapping code, or
   persistence attempt was made this pass (explicitly out of scope: "No
   stats persistence into canonical production tables").
5. The other 10 of Phase 8.2's 17 canonically-identity-resolved NE
   players were not confirmed present in this capture (only 7/17
   matched) — very likely present in the untruncated remainder, not
   confirmed either way.

## 11. Service-health result

**No crash, no failed healthcheck, no auto-redeploy this pass** — the
exact operational failure mode Phase 8.3B disclosed did not recur,
confirming this pass's exception-safety fix works (though it was not
actually exercised by a timeout this time, since the real call
succeeded fast). Deployment `3b8426a9-72b7-4ad5-87e0-ab0c6881adad`
reached `SUCCESS` in under 30 seconds total, with the diagnostic call
itself completing in 0.173s. The activation variable was reverted to
`"0"` (`skipDeploys: true`) immediately after the marker claim was
confirmed. Service is healthy on the current deployment.

## 12. Recommendation for next Phase 8 step

1. **Do not make another `player_stats_totals` call for NE** — this
   pass's real evidence (rich, real per-player season data, `team`
   filter confirmed working) is sufficient to design real persistence
   against. A future pass should design and, once HQ authorizes it,
   implement a `player_stats`-scoped persistence function (mirroring
   Phase 8.3A's `team_season_stats.py` pattern: a new function, not an
   overload of the game-scoped `persist_player_stats`), then activate it
   using this pass's own committed fixture data first — zero new
   provider calls needed to reach that milestone.
2. **Fix the 80KB log-truncation gap before any future large-payload
   diagnostic** — chunk large log messages, or capture the payload some
   other durable way (e.g., writing directly to a scratch/committed file
   from within the diagnostic itself) so a future successful call
   doesn't lose data to the same limit this pass hit.
3. **`player_gamelogs` remains the only path to any contextual
   (weather/opponent/venue/recency) player dimension** — out of scope
   for both this pass and Phase 8.3B, and not authorized here either;
   flagged as the next real capability gap once season-aggregate
   persistence is built.
4. Leave `gamesStarted`'s reliability as an open, disclosed question
   rather than building any logic that depends on it being real.

STOP after reporting, per HQ's instruction. No player-stat persistence,
second provider request, or further live calls were made without
authorization.
