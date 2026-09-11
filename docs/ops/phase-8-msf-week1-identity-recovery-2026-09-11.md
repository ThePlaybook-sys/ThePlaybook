# MSF Week 1 Identity Recovery (2026-09-11)

MANSA HQ directive: "MSF WEEK 1 IDENTITY RECOVERY." One real,
HQ-authorized MySportsFeeds schedule-level request (`week/1/games.json`)
to recover MSF's real game/team identity for Week 1. This is IDENTITY
RECOVERY, not postgame ingestion -- no boxscore call, no player
creation, no player-game persistence, no `team_provider_ids` mutation.

## Endpoint provenance (not guessed)

`week/{N}/games.json` (and the whole-season `games.json`) are the exact,
already-exercised MSF schedule-listing request shapes from the
2026-09-03 NFL provider bake-off
(`docs/ops/nfl-provider-gap-test-mysportsfeeds-2026-09-03.md`,
"Cross-cutting findings"). That bake-off's own calls used a **prior**
season (2025) and got a real, reproducible `403` -- a disclosed,
plan-specific restriction on **historical** game listings (that same
plan's `standings.json` for that exact prior season succeeded, ruling
out a blanket season gate). The **current** 2026-2027 season's own
`week/{N}/games.json` had never been called before this pass -- the
shape was proven, the current-season outcome was not assumed either
way, exactly as reported in the preceding preparation pass.

## What was built and fired

Same temporary-diagnostic-then-revert pattern as every prior live-call
pass. Reused the existing, standing `build_msf_game_boxscore_diagnostic_client`
(a general MSF client builder despite its boxscore-specific name --
`MYSPORTSFEEDS_API_KEY` bound, 120s timeout, credential never read
outside that one function) rather than adding a second credential
reader for the same key. 10 new tests (respx-mocked, zero live calls)
passing before the flag was set; full suite 793/793 before firing.

Fired via one `set-variables` call (deploy allowed, the explicit point
of this call), confirmed `SUCCESS` via `list-deployments`, flag reset
immediately after (`skipDeploys: true`). Diagnostic module, test file,
and startup hook fully reverted after use -- 783/783 full suite
re-confirmed, zero regressions.

## The one real call: result

**HTTP 200. 16 games found.** Full raw response (33,528 bytes) persisted
durably to `game_events` before any parsing, anchored to the SEA/NE
canonical `game_id` (the same disclosed FK-anchor modeling choice
already used for the BALLDONTLIE recovery pass -- `raw_payload` is
un-normalized jsonb, unaffected by which game anchors the row).

**The prior-season 403 restriction did not apply to the current
season** -- a real, now-resolved uncertainty, not assumed away in
advance.

## Validation and reconciliation

All 16 returned games matched, unambiguously, against MANSA's complete
16-game canonical Week 1 universe -- by **team pair AND exact kickoff
timestamp together** (never name alone):

| MSF game id | Away | Home | Kickoff (UTC) | `playedStatus` | Canonical match |
|---|---|---|---|---|---|
| 163541 | NE | SEA | 2026-09-10 00:20 | **COMPLETED** | `280e7b05...` (already mapped from Gate B -- confirmed identical, not re-inserted) |
| 163542 | SF | LA | 2026-09-11 00:35 | **COMPLETED** | `50d14afd...` (SF@LAR) |
| 163543 | CHI | CAR | 2026-09-13 17:00 | UNPLAYED | `9623ad48...` |
| 163544 | TB | CIN | 2026-09-13 17:00 | UNPLAYED | `c675d23b...` |
| 163545 | NO | DET | 2026-09-13 17:00 | UNPLAYED | `d4b2efd9...` |
| 163546 | BUF | HOU | 2026-09-13 17:00 | UNPLAYED | `e7a682d0...` |
| 163547 | BAL | IND | 2026-09-13 17:00 | UNPLAYED | `7eedf4ff...` |
| 163548 | CLE | JAX | 2026-09-13 17:00 | UNPLAYED | `43a81aab...` |
| 163549 | ATL | PIT | 2026-09-13 17:00 | UNPLAYED | `2e54ffc4...` |
| 163550 | NYJ | TEN | 2026-09-13 17:00 | UNPLAYED | `991b9a9f...` |
| 163551 | ARI | LAC | 2026-09-13 20:25 | UNPLAYED | `57316028...` |
| 163552 | MIA | LV | 2026-09-13 20:25 | UNPLAYED | `42eae7bd...` |
| 163553 | GB | MIN | 2026-09-13 20:25 | UNPLAYED | `898b65d1...` |
| 163554 | WAS | PHI | 2026-09-13 20:25 | UNPLAYED | `cd0f612b...` |
| 163555 | DAL | NYG | 2026-09-14 00:20 | UNPLAYED | `a4c0d61b...` |
| 163556 | DEN | KC | 2026-09-15 00:15 | UNPLAYED | `32764b10...` |

**Exact coverage, per HQ's requested breakdown:**
- MSF games returned: **16**
- Exact canonical matches: **16**
- Unmatched MSF games: **0**
- Unmatched canonical games: **0**
- Ambiguous matches: **0**
- Home/away conflicts: **0** -- every MSF home/away pairing matched the canonical row exactly
- Kickoff conflicts: **0** -- every MSF `startTime` matched the canonical `scheduled_start` exactly (to the second)

**SF@LAR is real and finished**: `163542`, `playedStatus: "COMPLETED"` --
confirmed by MSF itself, not inferred from elapsed time (see the
preparation pass's own Section 5 requirement, now satisfied by real
data rather than a clock).

## Real MSF identity evidence extracted

**Game IDs**: all 16, table above.

**Team numeric IDs** (from `schedule.awayTeam.id`/`homeTeam.id` on every
game -- since a full week's slate touches all 32 teams exactly once,
this one response yields all 32 teams' real MSF numeric ids):

| Abbrev (MSF) | Numeric id | Abbrev (MSF) | Numeric id | Abbrev (MSF) | Numeric id | Abbrev (MSF) | Numeric id |
|---|---|---|---|---|---|---|---|
| NE | 50 | SEA | 79 | SF | 78 | LA | 77 |
| CHI | 60 | CAR | 69 | TB | 71 | CIN | 57 |
| NO | 70 | DET | 61 | BUF | 48 | HOU | 64 |
| BAL | 56 | IND | 65 | CLE | 58 | JAX | 66 |
| ATL | 68 | PIT | 59 | NYJ | 51 | TEN | 67 |
| ARI | 76 | LAC | 75 | MIA | 49 | LV | 74 |
| GB | 62 | MIN | 63 | WAS | 55 | PHI | 54 |
| DAL | 52 | NYG | 53 | DEN | 72 | KC | 73 |

**One naming note, disclosed**: MSF's own abbreviation for the Los
Angeles Rams is `"LA"`, not `"LAR"` (BALLDONTLIE's abbreviation, already
used for this team's canonical `games.home_team`/the F2 prep report) --
same real team, different provider convention, consistent with the
WAS/WSH and JAX/JAC notes from the two prior recovery passes. Not
acted on here (display convention only, no identity ambiguity -- the
numeric id 77 plus the kickoff/opponent match make the identity
unambiguous regardless of which abbreviation string is used).

## `game_provider_ids` persisted -- reconciliation was unambiguous

Per HQ's explicit branch ("if and only if reconciliation is
unambiguous"): all 16 matches were unambiguous (team pair + exact
kickoff, zero conflicts of any kind), so the mappings were persisted.
One atomic, idempotent SQL statement (same `WHERE NOT EXISTS` pattern
proven in both prior recovery passes) with a provider-id collision guard
AND a per-game single-mapping guard. **15 new rows inserted** (163541
correctly skipped -- it already existed from Gate B, and its value was
confirmed byte-identical to this fresh call's own report, a clean
cross-check). **Rerunning the identical statement inserted zero rows** --
idempotency proven, not asserted. Final state: **16/16** real Week 1
canonical games now carry a real `mysportsfeeds` `game_provider_ids`
mapping.

## `team_provider_ids` -- reported, not mutated, per explicit instruction

**Current real MSF team-identity coverage: 12/32 teams** (ARI, ATL, BAL,
BUF, CAR, CHI, DAL, MIA, NE, NYG, NYJ, SEA) -- all via MSF's
**abbreviation** scheme, from earlier passes. **Zero of the 32 teams have
MSF's numeric-id scheme mapped** (the `team_provider_ids` unique
constraint is `(team_id, provider_name)`, one row per team per provider
-- already identified as a real gap in an earlier design pass, not
newly discovered).

**This one call's real, usable byproduct**: the 32-team numeric-id table
above is real evidence, sitting in the persisted raw response, ready for
a future authorized pass to apply. Nothing was inserted this pass.

**Migration/backfill that would be required** (unchanged from the design
already on record, now backed by a complete real dataset rather than a
partial one):
1. Widen `team_provider_ids`'s unique constraint from `(team_id,
   provider_name)` to `(team_id, provider_name, provider_team_id)` --
   lets both the existing abbreviation-scheme rows and new numeric-scheme
   rows coexist per team per provider.
2. One real-data backfill inserting all 32 teams' numeric MSF ids (table
   above) -- a plain additive `INSERT`, no schema change beyond (1),
   following the exact "schema via migration, real data via execute_sql"
   convention already used for every prior real-data activation in this
   project.

## SF@LAR: proven, per HQ's explicit ask

| Question | Answer |
|---|---|
| Exact MSF game id | **163542**, confirmed, now persisted to `game_provider_ids` |
| Exact SF MSF team identity | Numeric id **78**, abbreviation `"SF"` -- **not yet** in `team_provider_ids` (0/32 coverage for the numeric scheme, per above) |
| Exact LAR MSF team identity | Numeric id **77**, abbreviation `"LA"` -- **not yet** in `team_provider_ids` |

Game-level identity is now fully resolved for SF@LAR. Team-level MSF
identity for both SF and LAR is real and known (captured in this
response) but not yet persisted anywhere, per this pass's explicit
scope boundary.

## Architectural distinction preserved

This pass recovered **identity** only: which real MSF game id and team
ids correspond to which canonical rows. Nothing about **postgame
ingestion** was built or exercised -- no boxscore call was made, no
player was created, no player-game stats were persisted, no eligibility/
call-control logic was built or run. The F2 controlled test (MSF final
box score -> raw preservation -> validation -> automatic identity
activation -> player-game persistence -> confirmed complete) remains a
separate, later, separately-authorized pass -- this one only removed one
of its two named blockers (SF@LAR's own MSF game id; the team-level
mapping gap for SF/LAR remains open, as reported above, not silently
closed).

## Out of scope, exactly as instructed

No boxscore call. No player creation. No player-game persistence. No
`team_provider_ids` schema change or mutation. No Context Intelligence.
No recommendation work. Staging and production untouched.
