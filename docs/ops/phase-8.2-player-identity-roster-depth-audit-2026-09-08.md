# Phase 8.2 — Player Identity + Roster/Depth Activation Audit (2026-09-08)

**Status: audit/design only. Zero code changes, zero schema changes, zero
Supabase writes, zero new live provider calls (beyond re-reading
already-obtained, locally-cached evidence). DEV only. No Probability
Modeling integration. No Phase 4 changes. No Milestone 5.6. No Phase
7.2/7.3. No NBA implementation. No SportsDataIO call. No purchases/
upgrades. No invented player/roster/depth data.**

This pass explicitly does **not** rely on prior reports where live state
could have drifted — every finding below was re-confirmed against the
actual repo, the actual DEV database, or a genuinely re-read primary
source produced by an earlier live diagnostic. Where a prior report's
characterization turned out to be stale or incomplete, that is called out
directly rather than repeated.

---

## 1. Live player/roster/depth data state (re-confirmed via live Supabase reads, not memory)

| Table | Rows | Real or fixture |
|---|---|---|
| `players` | 6 | 100% fixture/seed (`"Seed QB Chiefs"`, `external_provider_id="seed-p1"`, etc.) |
| `player_provider_ids` | 0 | n/a |
| `roster_memberships` | 0 | n/a |
| `depth_chart_snapshots` | 0 | n/a |

Zero real player identity, zero real roster membership, zero real depth
data exists anywhere in DEV today. This exactly reconfirms Phase 8.0.5's
closeout conclusion — no drift found here.

---

## 2. Existing ingestion code state

### 2a. Two coexisting player-identity mechanisms (a real, disclosed duality)

- A legacy single column, `players.external_provider_id` — used only by
  the 6 fixture rows above.
- A newer, provider-neutral mapping table, `player_provider_ids`
  (canonical `player_id` ↔ `provider_name` ↔ `provider_player_id`) — the
  intended real design, currently 0 rows.

### 2b. `apps/sports-intel-layer/app/persistence/player_identity.py` (137 lines)

Already fully provider-name-parameterized: `resolve_player_ids()`,
`link_provider_player_id()`, `ensure_player()` all take `provider_name` as
a plain argument. This module is a genuinely reusable building block for
**any** future provider, not just SportsDataIO. No changes needed to use
it with BALLDONTLIE or MySportsFeeds identity.

### 2c. `apps/sports-intel-layer/app/persistence/roster_ingestion.py` (216 lines) — **correction to a prior characterization**

Phase 8.0.5's closeout described this module as "complete... never
invoked against a live provider," implying it was ready to point at any
provider. **That characterization is incomplete.** Live code reading this
pass found:

```
_PROVIDER_NAME = "sportsdataio"   # line 59, module-level constant
```

`persist_roster()` uses this hardcoded constant internally when calling
`resolve_team_ids`/`ensure_player`/`resolve_player_ids`/
`link_provider_player_id` — it is **not** callable today against a
non-SportsDataIO source without a small, real generalization (threading a
`provider_name` parameter through from the caller instead of the
module-level constant). This is a genuine, previously-unflagged gap, not
a large one — but "complete and provider-neutral" was not accurate as
stated. Corrected here per this pass's own "do not rely on prior reports
if live state differs" instruction.

The rest of the module's logic is sound and worth keeping as-is:
- `_sync_membership()` inserts a new `roster_memberships` row only on
  first observation, a team change, or a rejoin (observed team != latest
  known team) — never touches/overwrites an existing row.
- Never infers release or free-agent status from absence.
- `depth_chart_snapshots` gets one unconditional insert per capture
  (matches `odds_snapshots`/`weather_snapshots`/`injury_reports`'
  "every poll is a new row" convention, not the insert-on-change pattern
  `team_stats`/`player_stats` use).

### 2d. Adapter layer

- `RosterAdapter` ABC (`app/adapters/base.py`) returns roster **and**
  depth chart merged in one call: `fetch_roster(team) ->
  AdapterResponse[list[RosterEntry]]`.
- `RosterEntry` (`app/adapters/models.py`): `team, player_external_id,
  player_name, position, depth_chart_rank` — genuinely provider-neutral
  shape.
- **Only one concrete implementation exists anywhere in the codebase:
  `SportsDataIORosterAdapter`** (`app/adapters/providers/sportsdataio.py`,
  line 342), which calls SportsDataIO's `/Players/{team}` and
  `/DepthCharts` and merges `DepthOrder` into `depth_chart_rank`. **No
  BALLDONTLIE or MySportsFeeds `RosterAdapter` exists anywhere** — not
  partially built, not stubbed, genuinely absent.

### 2e. Invocation/cron gaps

`roster_ingestion.persist_roster()` is never called from any cron worker
or startup hook today. There is no `cron-roster-worker` and no roster
call inside any existing worker. Activating it for real requires both (a)
a real adapter for the chosen provider and (b) a real invocation path —
neither exists yet.

### 2f. Historical/versioning behavior (item 4's underlying investigation)

`supabase/migrations/20260818070000_roster_memberships_and_depth_chart_redesign.sql`,
read in full: `roster_memberships` is append-only (DB trigger blocks
`UPDATE`), one row per real membership change, never overwritten.
`depth_chart_snapshots` is team-scoped (corrected by this same migration
from an earlier game-scoped design that had zero rows/writers) and
append-only, one unconditional snapshot per capture. Reading the actual
`_sync_membership()`/persistence logic in `roster_ingestion.py` confirms
the code-level behavior matches this schema-level intent exactly — new
rows are inserted on real change, nothing is ever mutated in place.

**Conclusion on item 4: the design already correctly guarantees "who was
on this team / in this role at that point in time" answerability.** No
new design is needed here — schema and code both already do the right
thing. The only reason this can't be exercised today is that zero real
rows exist yet, not a design gap.

---

## 3. Provider availability/cost/access matrix

### 3a. BALLDONTLIE — the tier-access question, resolved

This pass found the resolving evidence already sitting in this
project's own prior reports, dated the same day (2026-09-07), in
sequence:

1. `docs/ops/phase-8-contextual-intelligence-audit-2026-09-07.md` (earlier
   that day) still describes BALLDONTLIE as "paid GOAT, active DEV
   credential" and lists current-season rosters (`/players/active`) as
   **GREEN**.
2. `docs/ops/phase-8.0.5-weather-activation-closeout-2026-09-07.md`
   (later that same day) records HQ's own correction: *"GOAT entitlement
   is documented as including Player Injuries... The user's Sep 5
   BALLDONTLIE invoice is OPEN/unpaid, so paid GOAT entitlement is not
   currently confirmed active — this, not a code defect, is the likely
   cause of the real 401. Games works today because it is available on
   the Free tier; Player Injuries remains unavailable pending confirmed
   paid entitlement."*

**This resolves the open question from the prior summary.** The #1
report's "GREEN" conclusion for rosters predates the #2 report's invoice
discovery and is now stale. The current directive's own statement —
*"Team Roster is documented as GOAT-only"* — combined with the confirmed
open/unpaid invoice means: **any BALLDONTLIE endpoint that requires GOAT
entitlement, roster/team-roster included, cannot be treated as currently
accessible.** Only `Games` is confirmed Free-tier-accessible. `/nfl/v1/
players` and `/nfl/v1/players/active` were live-GREEN on 2026-09-03, but
that result cannot be trusted to reflect today's account state, since the
same account's GOAT entitlement is now confirmed not-currently-active for
a different endpoint (Injuries) on the identical billing/tier boundary.
**Verdict: BALLDONTLIE roster/player-active access is UNCONFIRMED, likely
blocked by the same unpaid-invoice condition as Injuries — not a
"clearly available, zero/known incremental cost" path today.** This
correction is the single most important finding of this pass's provider
audit.

No live BALLDONTLIE call was made this pass to re-test this — doing so
would violate "do not make repeated paid-endpoint calls" for a question
this project's own existing evidence already answers.

### 3b. MySportsFeeds — full audit from scratch this pass

- **Existing integration state:** no adapter exists in the codebase
  (confirmed by search — zero references to `mysportsfeeds` under
  `apps/sports-intel-layer/app`). `MYSPORTSFEEDS_API_KEY` was set on
  `sports-intel-layer`/DEV during the 2026-09-03 gap test and, per that
  report, was never removed — it should still be present (not re-checked
  this pass to avoid an unnecessary credential read; the gap test's own
  revert only removed the temporary diagnostic code and reset
  `RUN_MSF_BAKEOFF=0`, not the key itself).
- **Trial window:** the 2026-09-03 report describes a "14-day trial"
  under evaluation. From 2026-09-03, that trial window runs through
  approximately 2026-09-17 — still open as of today (2026-09-08), but
  narrowing. This is a real time pressure worth naming to HQ even though
  it wasn't asked for directly.
- **What the existing gap test already found, real and live-confirmed
  (2026-09-03, 22 live calls, fully reverted afterward):**
  - **Lineups — GREEN.** `/nfl/{season}/games/{id}/lineup.json` returned
    real depth-chart-level detail even 7 days pre-game:
    `teamLineups[].expected.lineupPositions[]` with real position labels
    (`"Offense-RB-1"`, `"Defense-DE-1"`) and a named player where
    confirmed, honest `null` where not yet announced. **This is real
    depth/role data, not merely a roster list** — closer to
    `RosterEntry.depth_chart_rank` than a bare roster.
  - **Team stats — GREEN** (not directly requested by this directive, but
    confirms the trial credential is live and broadly functional).
  - **Injuries — YELLOW** (rich bio data, weaker injury-description
    quality than BALLDONTLIE/API-SPORTS).
  - **Play-by-play / box scores — UNKNOWN**, not this pass's concern
    (HQ's own directive: "PBP/box-score validation remains separate").
  - No player-identity-mapping work was attempted in that pass (no writes
    were made at all).
- **A real gap in that prior test, found by this pass:** the 2026-09-03
  gap test never exercised a dedicated player/roster **reference** feed —
  only game-scoped lineups, team stats, injuries, and standings. This
  pass re-read the official `mysportsfeeds-node` v2.0/2.1 SDK
  (`API_v2_0.js`, already locally extracted from an earlier pass, zero
  new live calls) and confirmed a **separate, real, season-independent
  feed exists**:
    ```
    players: { season: false, endpoint: 'players' }
    ```
    This is MySportsFeeds' own player-reference feed — the natural
    source for canonical player identity + current-team affiliation,
    distinct from the per-game `lineup.json` depth/role feed. **This
    feed has never been called, tested, or observed by this project.**
    It is architecturally the right target for a first controlled roster/
    identity diagnostic, but its real shape (does it carry `currentTeam`?
    pagination? completeness for a 14-day trial?) is genuinely unknown
    until one real call is made.
- **No dedicated "team roster" feed by name was found in the SDK** —
  `lineup.json` (per-game expected roles) and `players.json` (global
  player reference) are the two real, closest-fit endpoints; team-level
  "who is currently on this roster, independent of any specific game" is
  not directly served by a single named feed and would likely be derived
  from `players.json`'s own team-affiliation field, unconfirmed until
  tested.

### 3c. Already-captured data — can it seed canonical player identity without new spend?

**No.** The real captured data this project already holds
(`team_provider_ids`: 59 rows across sportsdataio/the_odds_api/
balldontlie; `game_provider_ids`: 17 rows) is entirely team- and
game-scoped. Nothing in the current real dataset carries any player-level
identity, name, or provider player ID. There is no free lunch here — any
canonical player identity, from any provider, requires at least one new
real call against a player/roster-shaped endpoint. This does not
contradict "zero/known incremental cost" for MySportsFeeds, since that
provider's trial is already provisioned and a single call has no
incremental dollar cost — it does mean BALLDONTLIE cannot be substituted
for free using only already-captured rows.

### 3d. SportsDataIO

Reserved call remains untouched and unspent, per guardrail. Not evaluated
further this pass.

### Summary matrix

| Provider | Rosters/identity | Depth/lineup | Cost right now | Access confirmed today? |
|---|---|---|---|---|
| BALLDONTLIE | Unconfirmed (`/players`, `/players/active` — same GOAT tier as the blocked Injuries endpoint) | Not offered (no depth/rank field in the SDK at all) | $0 incremental if GOAT were active, but entitlement is not confirmed active | **No** — blocked pending the open Sep 5 invoice, same root cause as the Injuries blocker |
| MySportsFeeds | `players` feed exists, real, never yet called | `lineup.json` — real, live-GREEN, depth-chart-level | $0 incremental — trial already provisioned, key already set | **Yes, with caveats** — trial active but time-boxed (~through 2026-09-17), only lineup/team-stats/injuries/standings have been live-tested so far, not `players` |
| SportsDataIO | Reserved, unspent | Reserved, unspent | Prohibited this pass | N/A — out of scope by guardrail |

---

## 4. Canonical player identity design (provider-neutral, sport-agnostic)

The existing schema already gets the shape right; this section confirms
and names it explicitly rather than proposing something new, per HQ's
"design/review" framing.

```
canonical player (players)
    ↕ (1:N)
provider player identity (player_provider_ids: player_id, provider_name, provider_player_id)
    ↕ (1:N, time-aware)
roster membership (roster_memberships: player_id, team_id, observed_at, ...)
    ↕ (1:N, time-aware, team-scoped)
depth/lineup role (depth_chart_snapshots: team_id, player_id, depth_chart_rank, captured_at)
    ↕ (per-game, separate concept entirely)
game participation (not modeled by any of the above — a distinct future concept: did this
player actually appear/play in this specific game, which neither roster membership nor a
depth-chart rank guarantees)
```

Four genuinely distinct concepts, deliberately not collapsed:

1. **Player identity** — "this human exists and has this canonical
   record," provider-neutral, permanent, never sport-specific in its core
   fields (name, DOB if known, sport — NOT position, NOT team, NOT jersey
   number pinned to one league's conventions).
2. **Roster membership** — "this player was affiliated with this team as
   of this observation," time-aware, append-only, never inferring
   release/free-agency from absence of a newer row.
3. **Depth/lineup role** — "this player's expected/announced role/rank
   within the team's depth chart at this snapshot," team-scoped (not
   game-scoped), also time-aware and append-only. Distinct from roster
   membership because a player can be rostered without appearing in any
   current depth chart entry (practice squad, injured reserve, etc.).
4. **Game participation** — "this player actually took the field in this
   specific game." **Not modeled anywhere in the current schema.** This
   is correctly out of scope for Phase 8.2 (HQ's guardrails: no PBP/
   box-score work, no Milestone 5.6) — flagged here only so it is never
   confused with roster membership or depth rank, which is exactly the
   distinction HQ's directive asked to preserve.

**NFL now / NBA later:** nothing in `players`, `player_provider_ids`,
`roster_memberships`, or `depth_chart_snapshots` carries an NFL-specific
column today (position is a free-text/string field, not an NFL position
enum) — confirmed by schema read. The design already satisfies "core
player model never NFL-specific." The only NFL-specific surface in the
current substrate is the adapter/ingestion layer (`SportsDataIORosterAdapter`,
`roster_ingestion.py`'s SportsDataIO-shaped field mapping), which is
expected and correct — adapters are supposed to be sport/provider-specific
translators into the neutral core, not the other way around.

---

## 5. Historical roster/depth design

Already covered in §2f: the schema and code both already guarantee
append-only, time-aware, never-overwritten roster/depth history. **No
new design is being proposed — the existing design is confirmed correct.**
The only gap is that zero real rows exist to exercise it against.

---

## 6. Activation decision — exact controlled activation plan (proposed only, not executed)

Per HQ's own decision criteria — "clearly available, already authorized,
zero/known incremental cost, and architecture-compatible" — **BALLDONTLIE
fails this test today** (entitlement not confirmed active, same blocker
as Injuries). **MySportsFeeds passes it**, with one caveat: the trial
window is time-boxed, so "zero incremental cost" holds only while the
trial remains open.

**Recommended path: MySportsFeeds, smallest safe activation, in this
exact order, as a proposal for a future pass — nothing below is executed
in this pass:**

1. **One single, narrow diagnostic call** against MySportsFeeds'
   `players` feed (season-independent, per §3b) — the one real endpoint
   this project has never observed. Goal: confirm the real response
   shape (does each player object carry `currentTeam`? what identity
   fields exist? is there pagination at this trial's data volume?).
   Same "temporary diagnostic module, gated behind an env flag, fully
   reverted after" pattern this project has used for every prior
   provider probe (2026-09-03 bake-off, 2026-09-03 gap test, Pass 2.2's
   live proof) — zero permanent code, zero Supabase writes.
2. **Generalize `roster_ingestion.py`'s `_PROVIDER_NAME` hardcoding**
   (§2c) into a real parameter threaded from the caller, defaulting to
   `"sportsdataio"` only for existing callers so today's (currently
   unused) behavior is unchanged. Small, mechanical, low-risk — this is
   the one real code change this plan would eventually need regardless
   of which provider is chosen.
3. **Build a new `MySportsFeedsRosterAdapter`** implementing the existing
   `RosterAdapter` ABC, combining: `players` feed for canonical identity +
   current-team affiliation, and `lineup.json` for depth/role data
   (mapping into `RosterEntry.depth_chart_rank` the same way
   `SportsDataIORosterAdapter` already does with SportsDataIO's
   `DepthOrder`). This is new code, not proposed as written in this
   pass — audit/design only, per guardrails.
4. **One controlled, manual `persist_roster()` run** for a small number
   of already-tracked teams/games (the 8 real Phase 7/8 games this
   project already has, not a full-league pull) — proving the pipeline
   end to end against real data without committing to recurring polling.
5. **Do not wire recurring polling/cron** in this plan — matches HQ's
   explicit "DO NOT activate recurring polling in this pass unless
   already clearly HQ-authorized." No such prior authorization exists for
   roster/depth polling specifically (Phase 7's authorized recurring
   workers are odds, news, weather — not roster/depth).

This plan makes zero purchases, spends the MySportsFeeds trial's already-
provisioned access only, and treats BALLDONTLIE roster access as blocked
until HQ separately resolves the open invoice — at which point the exact
same generalized `roster_ingestion.py` (step 2) would work against a new
`BallDontLieRosterAdapter` with no further architecture change needed,
since the identity layer is already provider-neutral.

---

## 7. Phase 8 consequences — which insufficient-evidence dimensions unlock

Phase 8.1's six `UNSUPPORTED_DIMENSIONS`: `player_performance`,
`injuries`, `roster_role`, `team_performance`, `depth_lineup`,
`game_state_pbp`.

| Dimension | Unlocked by successful activation above? | Why |
|---|---|---|
| `roster_role` | **Yes** | Directly what `roster_memberships` real rows would provide. |
| `depth_lineup` | **Yes** | Directly what `depth_chart_snapshots` real rows (from MySportsFeeds `lineup.json`) would provide. |
| `player_performance` | **Partial only** | Identity would become real, but no player *statistics* source is activated by this plan — stats remain a separate, unaddressed gap. |
| `injuries` | **No** | Blocked by the BALLDONTLIE unpaid-invoice issue, unrelated to roster/identity activation. |
| `team_performance` | **No** | Blocked by missing team-stats persistence work, unrelated to this plan. |
| `game_state_pbp` | **No** | Blocked by PBP/box-score validation, explicitly separate per HQ's own framing this pass. |

**No Phase 8.1 stub code is changed by this pass** — this section is a
mapping/forecast only, per guardrail.

---

## 8. Remaining blockers

1. BALLDONTLIE's Sep 5 invoice remains open/unpaid — a human billing
   action, not something this session can resolve. Blocks BALLDONTLIE
   roster/player-active access (and Injuries, unchanged from Phase 8.0.5).
2. MySportsFeeds' `players` feed has never been called — its real shape
   is unconfirmed until the one diagnostic call in §6 step 1 runs.
3. MySportsFeeds' 14-day trial (from 2026-09-03) is time-boxed — any
   activation work should happen before ~2026-09-17 or be explicitly
   re-evaluated against a paid/renewed trial state.
4. `roster_ingestion.py`'s `_PROVIDER_NAME` hardcoding is real code debt
   blocking any non-SportsDataIO roster path until generalized (§6 step 2).
5. No `MySportsFeedsRosterAdapter` exists — real new code, not started.
6. No invocation path (cron or manual) exists for roster/depth ingestion
   today, regardless of provider.

## 9. Recommendation for the next pass

Authorize exactly the smallest first step — §6 step 1, the single
`players`-feed diagnostic call against MySportsFeeds, temporary and fully
reverted, same pattern as every prior provider probe this project has
used. That one call resolves remaining blocker #2 and gives HQ real
evidence (not a design guess) before any of steps 2-4 are built. Treat
BALLDONTLIE roster access as not-currently-available until the invoice is
separately resolved by HQ; no BALLDONTLIE work is recommended for the
next pass.

---

**Guardrails held throughout this pass:** DEV only; audit/design only,
zero code/schema changes; no Probability Modeling integration; no Phase 4
changes; no Milestone 5.6; no Phase 7.2/7.3; no NBA implementation; no
SportsDataIO call; no purchases/upgrades; no invented player/roster/depth
data; no staging/prod touched. Zero new live provider calls were made —
every finding above came from live Supabase reads (read-only), live
repository code reads, or re-reading already-obtained evidence from prior
diagnostic passes (the 2026-09-03 bake-off and gap-test reports, and the
locally-extracted `mysportsfeeds-node` v2.0 SDK source already present in
this session's scratchpad from an earlier pass).
