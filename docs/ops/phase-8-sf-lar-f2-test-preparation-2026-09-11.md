# SF@LAR F2 Test Preparation (2026-09-11)

MANSA HQ directive: "SF@LAR POSTGAME TEST PREPARATION." Audit/design only
-- zero provider calls, zero mutations, zero schema changes, no
implementation begun. Prepares tonight's SF @ LAR game as the F2
controlled end-to-end test named in the Sunday ingestion design
(`docs/ops/phase-8-sunday-completed-game-ingestion-design-2026-09-10.md`
Section 5's F1/F2 split).

---

## 1. Canonical game verification

| Field | Value |
|---|---|
| Canonical `game_id` | `50d14afd-2861-4e07-b235-90ea857f004d` |
| Kickoff (`scheduled_start`) | `2026-09-11 00:35:00+00` UTC |
| Home team | `LAR` (Los Angeles Rams) |
| Away team | `SF` (San Francisco 49ers) |
| BALLDONTLIE provider mapping | `game_provider_ids`: `provider_name='balldontlie'`, `provider_game_id='1392217'` -- real, created in the Week 1 Canonical Schedule Recovery pass |
| MySportsFeeds provider mapping | **None exists yet** -- zero `game_provider_ids` rows for `provider_name='mysportsfeeds'` on this game |
| Current local `status` | `'live'` -- a snapshot from the moment this row was created (BALLDONTLIE's own `status_state` at capture time, ~2026-09-11 01:06 UTC), **not live-updated since** -- do not treat this field as current game state (see Section 5) |

**No "team IDs" exist on `games` to report** -- `games.home_team`/
`away_team` are plain text abbreviation strings, not foreign keys (this
schema has no `home_team_id`/`away_team_id` columns at all, confirmed
directly against `information_schema.columns`, consistent with what the
canonical-coverage audit already established). Resolving to canonical
`teams.id` requires a name match, done here for completeness, not as a
data-integrity concern:

| Abbreviation | Canonical `teams.id` | `teams.name` |
|---|---|---|
| SF | `a3000000-0000-0000-0000-000000000003` | San Francisco 49ers |
| LAR | `ee5402d5-2d20-4ad5-9144-03253fb5b069` | Los Angeles Rams |

**A real, concrete gap surfaced by this check, not previously named**:
neither SF nor LAR has a `mysportsfeeds` row in `team_provider_ids` --
only 12 teams do (ARI, ATL, BAL, BUF, CAR, CHI, DAL, MIA, NE, NYG, NYJ,
SEA, from the earlier NE/SEA Gate B work plus a 10-team backfill).
This matters directly for tonight's test -- see Section 4.

---

## 2. Existing persisted MSF evidence for SF@LAR -- searched, none found

Checked every place real MSF evidence could legitimately exist, without
making a call:

- **`game_events`** (the only durable raw-capture table): exactly 2 rows
  total exist in the entire database -- Gate B's real MSF `game_boxscore`
  capture (game 163541, NE@SEA) and this session's real BALLDONTLIE
  schedule capture (which carries BALLDONTLIE ids only, no MSF ids).
  **Neither contains an MSF game id for SF@LAR or any reference to it.**
- **`game_provider_ids`**: zero `mysportsfeeds` rows for this canonical
  game (confirmed above).
- **`team_provider_ids`**: zero `mysportsfeeds` rows for SF or LAR.
- **Repository docs/fixtures**: searched every prior MSF ops doc and
  fixture for any MSF numeric id near "Rams"/"49ers"/"SF"/"LAR" --
  the only matches found are incidental, unrelated mentions of "49ers"
  in other contexts (example data in unrelated audits), not a real MSF
  game id for this matchup.

**Conclusion: no legitimate source of SF@LAR's real MSF game id exists
anywhere in this project today.** It has not been inferred, guessed, or
recorded anywhere -- consistent with HQ's explicit instruction.

---

## 3. MSF identity resolution -- not yet proven; minimum-cost path identified

Since the exact MSF game id is **not** already proven (Section 2), per
HQ's own branching instruction this section reports the minimum-cost
legitimate resolution path rather than designing a mapping-insertion
(there is nothing yet to insert).

**Recommended path: one MSF seasonal/weekly schedule-level request, not
16 individual lookups.** Every MSF endpoint this project has used so far
follows the same `/nfl/{season}/...` shape (`{season} =
"2026-2027-regular"`, the exact string Gate B's own diagnostic already
uses). MySportsFeeds' schedule feed for a season (optionally filtered to
one week) is the direct MSF analog of the BALLDONTLIE `nfl/v1/games` call
this project just used to recover all 16 real BALLDONTLIE ids in one
shot -- the same shape of problem, the same shape of solution. **One such
call, filtered to Week 1, would be expected to return every Week 1 game's
MSF numeric id alongside its home/away teams and date** -- exactly enough
to deterministically reconcile all 16 canonical Week 1 games (not just
SF@LAR) against MSF identity in a single bounded request, mirroring
exactly how the BALLDONTLIE recovery pass just closed the equivalent gap
for BALLDONTLIE identity.

**This has not been called.** It is named here as the recommended next
authorization, not executed -- per HQ's explicit "STOP before mutation"
instruction for exactly this branch, and this pass's own "no provider
calls" instruction. If HQ authorizes it, the resulting reconciliation
(matching MSF's returned games to canonical rows by team pair + kickoff,
the same deterministic method already proven for BALLDONTLIE) would be a
natural follow-on pass, not a mutation made here.

---

## 4. Tonight test readiness

### Already proven (Gate B and the two subsequent activation passes)

- `parse_game_boxscore` -- pure adapter, proven against a real captured MSF boxscore (NE@SEA, 69/69 players).
- `write_raw_game_events` -- proven twice now on real provider responses (Gate B's MSF capture, this session's BALLDONTLIE capture) -- durable, pre-normalization preservation works.
- The identity-first, provider-id-as-dedup-key player creation pattern (`ensure_player`'s logic) -- proven manually via the Full Game Player Activation pass (47 players, zero duplicates, idempotent rerun).
- `persist_player_stats`-equivalent writing -- proven manually (69 real player-game rows, verified byte-identical, idempotent).
- The `activation_run_markers` claim-then-call idempotency guard and the temporary-diagnostic-then-revert discipline -- proven across every live call this project has made, including this session's two (Gate B's original call is a third, earlier proof).
- **Credential**: `MYSPORTSFEEDS_API_KEY` already exists on `sports-intel-layer`/dev (confirmed two passes ago) -- no provisioning gap.

### Not yet implemented (design only, from the Sunday ingestion design pass)

- `game_postgame_ingestion_state` table -- designed, not applied.
- `player_identity_quarantine` table -- designed, not applied.
- The completed-game eligibility state machine as reusable code -- designed, not built.
- The automated player-identity-activation wrapper (collision/team/name-similarity guardrails around `ensure_player`) -- designed, not built as reusable code; every real activation to date has been one-off, HQ-authorized, hand-built SQL, not a standing function.
- Any standing Postgame MSF Boxscore Worker / internal HTTP endpoint -- not built.
- `team_provider_ids` unique-constraint widening for MSF's numeric team-id scheme -- designed, not applied (not a blocker for SF@LAR specifically, since MSF's abbreviation scheme is what every team mapping to date has used).

### Must be resolved before tonight's F2 test specifically

1. **SF@LAR's real MSF game id must become known.** This is the hard blocker -- nothing downstream can start without it, and Section 2 confirms it does not exist anywhere yet. Requires the Section 3 call (or an equally legitimate, narrower one) to be separately authorized and made.
2. **SF and LAR both need real `mysportsfeeds` `team_provider_ids` rows** (abbreviation scheme, e.g. `"SF"`/`"LAR"`, matching the convention the other 12 teams already use) **before** automatic player-identity activation can safely resolve any player in this game to a team -- without this, every SF/LAR player in the boxscore would correctly quarantine on `team_unresolved` per the ingestion design's own guardrail (§3 of that design), not silently guess. This is a real-data backfill, not a schema change -- the same kind of step already done for the other 12 teams.
3. **Given neither the eligibility state machine nor the automated activation wrapper exist as reusable code yet**, F2 -- if run tonight -- would necessarily be executed the same way every real pass to date has been: a new, narrowly-scoped, HQ-authorized temporary diagnostic (one MSF `game_boxscore` call, gated, reverted after use) plus a hand-verified SQL reconciliation, **not** a demonstration of a standing automated worker. That worker is Sunday-enablement scope (build steps C/D/E and G from the accepted build order) and is not being built by this preparation pass. This is a scope clarification, not a blocker -- F2 can still meaningfully prove the pipeline's *logic* end to end even though it isn't run through the eventual *automated* pipeline yet.
4. **The playedStatus gate must hold** -- see Section 5.

None of the above requires a schema change; (1) and (2) are the two real
data gaps standing between tonight and a safe F2 attempt, and both
require exactly one more authorized, bounded provider call each (or one
combined call, per Section 3) -- not a redesign.

---

## 5. Timing -- elapsed time is not a completion signal

This game's kickoff was `2026-09-11T00:35:00Z`. As of this report
(`2026-09-11T01:22Z`, ~47 minutes post-kickoff), the only real signal
this project has already captured about its state is the BALLDONTLIE
schedule snapshot taken at `01:06:49Z`, which showed this exact game
**`status_state: "in_progress"`, "1:31 - 1st"** -- barely into the first
quarter at that point. That snapshot is now itself over 15 minutes old
and was never a live feed to begin with (one point-in-time schedule
capture, not a subscription) -- it should not be extrapolated forward
into "the game is probably done by now" at any point tonight.

**Restated per HQ's explicit instruction, not assumed**: whenever a real
MSF `game_boxscore` call is eventually authorized for this game (tonight
or later), the sole authority for treating it as complete is MSF's own
`playedStatus == "COMPLETED"` field on that response -- exactly the rule
the Sunday ingestion design already locked in Section 1 of that design
(`games.status`, elapsed real-world time, and this project's own stale
local snapshot above are all hints at best, never the trigger). A call
made before the real game is over would legitimately come back
not-final, which is a normal, expected outcome under that rule, not a
failure -- and must not be treated as license to skip the check on a
later attempt.

---

## Out of scope, exactly as instructed

No provider call made. No mutation. No schema change. No Sunday
ingestion worker implementation begun. Staging and production untouched.
