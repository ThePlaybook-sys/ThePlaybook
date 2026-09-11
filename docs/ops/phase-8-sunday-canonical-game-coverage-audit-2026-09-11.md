# Sunday Canonical Game Coverage Audit (2026-09-11)

MANSA HQ directive: "URGENT SUNDAY CANONICAL GAME COVERAGE AUDIT." Audit
only -- zero mutations, zero provider calls, zero schema changes. Sunday
ingestion build remains stopped pending this audit's findings.

**Headline finding, stated up front: MANSA's canonical database is not
corrupted. The home/away data is correct. The gap is coverage (9 real
Sunday games, plus 2 more real Week 1 games, were never seeded) and it
traces to a deliberate scope decision from an earlier directive, not a
bug.** The apparent home/away "reversal" HQ flagged came from my own prior
report's display formatting, not from the database. Full trace below.

---

## 1. Canonical games inventory

Queried `games` directly (dev, read-only). **12 total rows**, none
duplicated:

| Category | Count | Rows |
|---|---|---|
| Real, provider-sourced, current (2026 season) | 5 | SEA/NE (opener, captured/proven), LV/MIA, MIN/GB, PHI/WAS, LAC/ARI (all real BALLDONTLIE Week 1 games) |
| Seed/test fixtures (unrelated to the real season) | 4 | `seed-game-final` (Chiefs/Bills, Aug 4), `seed-game-live` (49ers/Eagles, Aug 7), `seed-game-upcoming` (Cowboys/Ravens, Aug 9), `seed-game-later` (Bills/Chiefs, Aug 16) -- all pre-dating the real season, all with synthetic `external_provider_id` values |
| Real, provider-sourced, future week (not Sunday Sept 13) | 3 | GB/CHI, SEA/SF, ARI/DET, all Oct 11, 2026 -- a separate, earlier discovery test, correctly out of scope for this Sunday |
| **Missing** (real Week 1 games confirmed by HQ, not present at all) | **11** | see §3/§4 |
| Duplicates | **0** | none found -- every row is a distinct real matchup/date/provider-id combination |

The 4 seed/test fixture rows and the 3 October rows are correctly inert
for Sunday Sept 13 purposes -- they were never mistaken for real Sunday
data by the ingestion design, and this audit found no evidence they ever
have been.

---

## 2. Home/away semantics -- traced to the actual source, not assumed

**Root of the trace: `games.home_team` and `games.away_team` are plain
text columns** (team abbreviation/name strings) -- there is no
`home_team_id`/`away_team_id` FK pair in this schema (confirmed via
`information_schema.columns` in a prior pass this session already
established, re-confirmed here by the query below).

**Live re-query of the 4 rows, exactly as stored:**

| `home_team` | `away_team` | kickoff (UTC) |
|---|---|---|
| LV | MIA | 2026-09-13 20:25 |
| MIN | GB | 2026-09-13 20:25 |
| PHI | WAS | 2026-09-13 20:25 |
| LAC | ARI | 2026-09-13 20:25 |

**HQ's stated official schedule**, read with the standard "away @ home"
convention (`MIA @ LV` = Miami travels to Las Vegas = LV is home):

| away (per "X @ Y") | home (per "X @ Y") |
|---|---|
| MIA | LV |
| GB | MIN |
| WAS | PHI |
| ARI | LAC |

**These match exactly, in both directions, for all 4 games.** The
database's `home_team`/`away_team` values are correct and were correct
before this audit began.

**Where the apparent reversal actually came from**: my own prior STOP AND
REPORT (the "Sunday Ingestion Preflight Correction" pass) displayed these
matchups as `"Las Vegas @ Miami"`, `"Minnesota @ Green Bay"`, etc. --
**home team listed first, away team second, joined with "@"**. Read under
the standard "away @ home" convention HQ (correctly) used, that display
reads backwards from what the database actually holds. This is
**hypothesis (c) from HQ's own audit list: the audit/report formatted
them backwards** -- confirmed, not any of the other three hypotheses:

- **Not a DB-row reversal**: the stored values, re-queried live just now,
  are correct (matches HQ's official schedule exactly, as shown above).
- **Not an adapter bug**: traced below (§5) -- the pass that seeded these
  rows explicitly recorded, in its own written PROGRESS.md entry from
  2026-09-07 ("Las Vegas Raiders (home) vs Miami Dolphins... Minnesota
  Vikings (home) vs Green Bay Packers... Philadelphia Eagles (home) vs
  Washington Commanders... Los Angeles Chargers (home) vs Arizona
  Cardinals"), that LV/MIN/PHI/LAC were identified as the home teams
  *before* the seed was written -- consistent with what is actually
  stored today. No transformation between that pass and today reversed
  anything.
  - **Note on iteration order, checked and ruled out as a red herring**: the
    live query above (and this audit's own re-query) can return these 4 rows
    in an order that puts LAC/ARI first (alphabetical by `home_team`,
    since all 4 share an identical kickoff timestamp with no secondary
    sort key specified) -- this is a row-ordering artifact of the query,
    not a per-row home/away swap, and does not affect any single row's own
    `home_team`/`away_team` values, which were checked individually above.
- **Not an upstream (BALLDONTLIE) misinterpretation**: the same 2026-09-07
  entry independently cross-checked BALLDONTLIE's own data against
  MANSA's pre-existing SEA/NE opener row and found it "matched this
  project's own DB exactly" -- BALLDONTLIE's home/visitor fields were
  being read correctly at the time, and the 4 Sunday rows were seeded
  using that same, already-validated reading.
- **Confirmed instead**: my subsequent chat-facing report display was the
  one place these values were ever presented backwards. PROGRESS.md's own
  permanent record was correct throughout.

---

## 3. The missing games -- confirmed absent, not hidden under a different id

Checked every one of HQ's 9 named-missing Sunday games, plus the
Thursday/Monday games named in §4, against all 12 rows in `games`
(matched on team-name pairs, since that is what this schema stores) --
**none of the 9 exist under any row, seed or real, in this database.**
No duplicate-under-a-different-id was found for any of them.

| Window | Games | Present in MANSA? |
|---|---|---|
| 1:00 PM ET | CHI@CAR, BAL@IND, ATL@PIT, CLE@JAC, TB@CIN, NYJ@TEN, NO@DET, BUF@HOU | **No, none of the 8** |
| 4:25 PM ET | ARI@LAC, GB@MIN, MIA@LV, WAS@PHI | **Yes, all 4** (as LAC/ARI, MIN/GB, LV/MIA, PHI/WAS -- see §2, correct) |
| 8:20 PM ET | DAL@NYG | **No** |

---

## 4. Full Week 1 universe

| Game | Day | Present in MANSA? |
|---|---|---|
| NE @ SEA | Wed night (season opener, 2026-09-10T00:20:00Z) | **Yes** -- captured, 69/69 players persisted, proven in the two prior passes |
| SF @ LA | Thursday | **No** |
| 13 Sunday games | Sunday | **4 of 13** (the 4:25 PM cluster only) |
| DEN @ KC | Monday | **No** |

**Total real Week 1 games MANSA canonically holds: 5 of 16.**

---

## 5. Root cause

**Confirmed root cause: a deliberate, HQ-directed activation-scope
decision from the 2026-09-07 "Current-Week Real Game Discovery" pass --
not a bug, not a BALLDONTLIE coverage gap, not pagination, not date/time
filtering, and not stale seed data.**

That pass's own record states plainly: a real, live BALLDONTLIE
`nfl/v1/games` call for Week 1, 2026 found **16 real games** (matching
HQ's full list in §4 exactly -- Thu + Sun-13 + Mon, 16 total). That
directive's own instruction was to select a small calibration cluster
("prefer 3-5" games), not seed the full slate -- so of the 16 real games
BALLDONTLIE actually returned, only 4 (the 4:25 PM window, chosen because
all 4 shared one exact kickoff timestamp, landing inside the "3-5"
preference) were ever written to `games`. The pass's own documentation
explicitly names the 8-game 1:00 PM cluster as "existed in the same
response; not selected, staying inside the directive's preferred 3-5
range" -- and is silent on the Thursday/Monday/SNF games entirely, which
were part of the same 16-game response but never surfaced or seeded
either.

**BALLDONTLIE's coverage itself was already complete and correct** -- the
provider returned all 16 real games in one call, four days ago. Nothing
about its coverage, pagination, or date filtering caused any gap. The gap
is entirely on MANSA's side: a prior directive intentionally limited what
got seeded, and nothing since has revisited that limit to seed the rest
of the real, already-discovered slate.

**One material consequence of how that pass was built, relevant to the
recovery plan below**: the raw BALLDONTLIE response for all 16 games was
**only logged** (`_logger.warning(...)`, Railway's own ephemeral log
stream), **never persisted** to any durable table -- unlike the Gate B MSF
diagnostic, which wrote its raw response into `game_events`. Confirmed by
reading the actual diagnostic source from git history
(`78265cbd6b55d7cac04b0337c3a57b066e50d7b1`, reverted the same day per
this project's standard temporary-probe discipline). The specific
BALLDONTLIE game ids and exact field values for the 11 unseeded games (8
from the 1 PM cluster, DAL@NYG, SF@LA, DEN@KC) were never written
anywhere durable -- only the 4 seeded games' ids survive, in both the
`games` rows themselves and in that pass's own PROGRESS.md prose. This is
a real, concrete constraint on the recovery plan, not a hypothetical one.

---

## 6. Recovery plan

**Nothing here has been applied. This is the recommended sequence for a
future, separately authorized pass.**

### What can be corrected from existing persisted evidence alone

**Nothing needs correcting.** §2 confirmed the 4 already-seeded games'
`home_team`/`away_team` values are already correct. There is no backfill,
no fix, and no data mutation required for LV/MIA, MIN/GB, PHI/WAS, or
LAC/ARI. The only thing that needs to change is how future reports
*display* these matchups (home-first, or an unambiguous `home vs away`
label instead of an "@"-joined string that silently assumes away-first) --
a reporting-discipline correction, not a data correction.

### What requires a new, real provider call -- named honestly, not avoided

The 11 missing real Week 1 games (8 at 1 PM, DAL@NYG at 8:20 PM, SF@LA
Thursday, DEN@KC Monday) **cannot be safely seeded from anything already
persisted in this repository or database.** The only record of their
existence is HQ's own message in this conversation (which names real
teams and windows, but not BALLDONTLIE's or any provider's actual game
ids) and an unpersisted, almost-certainly-rotated Railway log line from
four days ago. Per this pass's own explicit instruction -- "do not invent
games or provider IDs" -- team names alone are not sufficient to seed a
row that claims `external_provider_id = 'balldontlie:<id>'` truthfully;
that id has to come from a real call.

**Recommended sequence, once HQ authorizes a live call:**

1. **One real BALLDONTLIE `nfl/v1/games` call**, `seasons=[2026]`,
   `weeks=[1]` -- the exact same call the 2026-09-07 pass already made
   once safely and cheaply. This alone returns all 16 real games again
   (assuming the schedule hasn't changed in four days, itself worth a
   quick sanity check against HQ's list in §4/§1, which it should match).
2. **This time, persist the raw response durably before seeding
   anything** -- write it to `game_events` (the same pattern Gate B
   already uses for MSF, provider-neutral, no schema change needed) so a
   future audit never again has to rely on Railway's ephemeral log stream
   for the source-of-truth payload.
3. **Seed the 11 missing games** using the same pattern already proven
   for the 4 existing ones: `manual_seed=true`, `external_provider_id =
   'balldontlie:<real id>'`, `week=1`, `season_type='regular'`,
   `home_team`/`away_team` taken directly from BALLDONTLIE's own
   `home_team`/`visitor_team` fields (not re-derived from HQ's prose, to
   keep a single, traceable source of truth) -- with an explicit
   byte-for-byte comparison against HQ's official list (§3/§4) as a
   safety check before considering the seed correct, exactly the kind of
   independent cross-check the original 2026-09-07 pass already did for
   SEA/NE.
4. **Team-provider-id completeness check** (no new team creation needed --
   all 32 canonical teams already exist, confirmed live this pass): any
   of the 11 newly-seeded games' teams missing a `the_odds_api`
   `team_provider_ids` row would need one added, the same additive,
   no-schema-change step already used for LV/LAC/MIA/MIN/WSH in the prior
   pass.
5. **Only after that**, the Sunday ingestion design's own §2 (MSF
   game-level identity resolution, "B'" in the build-order review) can
   proceed against the *complete* real slate rather than a 4-game subset.

### Does correction require any paid/provider call?

**Yes, for the 11 missing games -- no way around it, and this audit does
not try to invent one.** One real BALLDONTLIE call (already a paid,
already-used credential on this exact endpoint, at the exact cost profile
the 2026-09-07 pass already incurred and documented) is the minimum real
step required to seed them with genuine, non-invented provider ids. **No
provider call is needed to fix anything about the 4 already-seeded
games** -- they were never wrong.

---

## Out of scope, exactly as instructed

No mutation was made to any table. No schema change. No provider call
(BALLDONTLIE, MySportsFeeds, or otherwise). No Sunday worker
implementation. Sunday ingestion build remains stopped pending HQ's
review of this audit and explicit authorization for the recovery
sequence in §6.
