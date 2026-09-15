# SportsDataIO Canonical Game Reconciliation

**Date:** 2026-09-15
**Directive:** MANSA HQ — "SPORTSDATAIO CANONICAL GAME RECONCILIATION"
**Type:** IMPLEMENTATION — **zero provider calls.** No SportsDataIO, no Odds API, no MSF, no LLM.
**Schedule Refresh:** NOT run. `MASTER_REFRESH_ENABLED` remains unset (paused).

---

## 1. Exact reconciliation algorithm

Applied per schedule entry, inside `persist_schedule_entries`, **before** the insert path.

```
0. If (provider_name, game_external_id) already maps to a canonical game
   -> that mapping IS the identity. Reconciliation is never consulted.
      (Provider ids stay authoritative. This is the unchanged primary rule.)

1. Resolve the entry's two SportsDataIO team tokens through the authoritative
   `team_provider_ids` mapping -> canonical teams.id values.
   Either unresolved -> UNRESOLVED_TEAMS: refuse, report, never insert.

2. Candidates = every canonical NFL game whose OWN stored home_team/away_team
   text also resolves, through that same authoritative mapping, to canonical
   team ids, and whose (home_team_id, away_team_id) equals the entry's pair
   exactly. Games already carrying a SportsDataIO mapping are excluded.

3. exact = candidates whose scheduled_start EQUALS the entry's
     len == 1 -> MATCH (matched_exact_kickoff)
     len >  1 -> AMBIGUOUS

4. else near = candidates within ±KICKOFF_TOLERANCE
     len == 1 -> MATCH (matched_within_kickoff_tolerance)
     len >  1 -> AMBIGUOUS
     len == 0 -> NO_MATCH_INSERT

5. MATCH     -> link_reconciled_game(); the existing canonical row is KEPT and
                reconciled; a finalized row is never downgraded.
   NO_MATCH  -> insert a new canonical game and link it (unchanged behavior).
   AMBIGUOUS -> refused: nothing linked, nothing inserted, reported.
```

**Both sides go through team identity — text is never compared.** `games` stores teams as free
text, so a raw string comparison would be exactly the name matching Decision 2 forbids. A game whose
stored text does not resolve canonically is never a candidate at all. (Live: 19 of 23 dev games
resolve; the 4 legacy fixtures storing full team names do not, and must not.)

**Never used as evidence:** fuzzy/normalized team names, display-text parsing, scores, market or
odds data, hardcoded matchups. None are read by this module at any point.

**Home and away are not interchangeable** — a reversed matchup is the other leg of the season
series, a different game.

**Batched, not per-entry:** one canonical-games read, one team-mapping read, one existing-mappings
read per run, reused across all ~304 entries.

---

## 2. Kickoff tolerance, and why

**`KICKOFF_TOLERANCE = 15 minutes`**, applied *only* after exact matching has been tried and found
nothing.

Sized to absorb timestamp **representation** differences and nothing more: second-level truncation,
and minute-level rounding (an 8:20pm ET kickoff published as :15 or :30). It is deliberately far
below one hour so that a genuine **timezone or DST error can never be absorbed silently** —
SportsDataIO publishes both an Eastern-local `Date` and a `DateTimeUTC`, and confusing them skews by
4–5 hours. Such an entry fails to match and surfaces as a new row, which is the correct loud
failure. A regression test asserts the constant stays under an hour.

Collision risk is structurally low: a match already requires an exact canonical team pair, and the
same two teams cannot play twice within 15 minutes.

**Disclosed-conservative** — judgment, not measurement, matching this codebase's convention for
undecided numbers. No SportsDataIO Schedule response has been ingested yet, so there is no measured
distribution of provider disagreement to derive it from.

**Honest limitation:** a **flexed** game moved more than 15 minutes fails to match and inserts a new
row. Low risk, because tolerance only matters on a game's *first* reconciliation — afterwards
identity is by GameKey forever.

---

## 3. Ambiguity behavior

More than one candidate at either the exact or the tolerance step → **`AMBIGUOUS`**:

- nothing is linked;
- **nothing is inserted** — the entry is added to a `refused` set so it cannot fall through to the
  insert path (this was a real bug caught by the dry-run tests: refused entries were still being
  inserted, producing exactly the duplicate the rule exists to prevent);
- the conflict is reported on `SchedulePersistenceResult.ambiguous` with every candidate id.

`UNRESOLVED_TEAMS` and link conflicts are handled the same way: refused, reported, never guessed.

---

## 4. Tests and regressions

| Suite | Tests | Covers |
|---|---|---|
| `tests/test_game_reconciliation.py` | 23 | match rule, tolerance boundary, ambiguity, candidate loading, link idempotency/conflict |
| `tests/test_schedule_reconciliation_dry_run.py` | 11 | end-to-end against dev's real canonical shape (§5) |
| existing suites updated | — | `test_schedule_persistence.py`, `test_master_refresh.py`, `test_master_refresh_v2.py`, `test_load_concurrency_full_fleet.py` |

**Totals: `sports-intel-layer` 979 passed / 5 failed; `ai-orchestrator` 987 passed; `apps/workers`
45 passed.** The 5 failures are the same pre-existing wall-clock rot in
`test_odds_cadence_persistence.py` documented in the previous pass (hardcoded 2026-09-14 kickoff now
in the past) — unrelated, and unchanged by this work.

**One deliberate behavior change to note:** a failure reading canonical team identity now **blocks**
schedule persistence. Without it there is no way to tell an existing game from a new one, and the
fallback — inserting — is the duplication this exists to prevent. Failing a refresh is strictly
better than splitting canonical identity. Roster-phase team failures remain non-blocking and
isolated, unchanged; `test_team_identity_error_for_one_team_does_not_crash_master_refresh` was
rescoped to the roster-phase lookup it was always about.

---

## 5. Dry run against dev's current shape

Reproduces the canonical shape verified live before writing: 16 finalized Week 1 games, a future
manual-seed game, a legacy full-name fixture, **zero** `sportsdataio` game mappings, **32/32**
`sportsdataio` team mappings. No SportsDataIO production game ids are fabricated for live rows —
GameKeys are synthetic `TEST-GK-*` tokens.

| Scenario | Result |
|---|---|
| existing **finalized Week 1** games | **reconciled 2, created 0, insert route never called** |
| finalized game's terminal state | guarded PATCH carries `status` and is rejected; follow-up PATCH omits `status`; `final_score`/`finalized_at` never writable |
| existing **future manual-seed** game | reconciled 1, created 0 |
| **genuinely missing Week 2** game | **created 1**, reconciled 0 |
| mixed run (3 existing + 1 missing) | reconciled 3, created 1 |
| **ambiguous** (two identical canonical rows) | reconciled 0, created 0, nothing linked, 1 reported |
| tolerance **inside** (+10 min) | reconciled within tolerance, no insert |
| tolerance **outside** (−5 h) | not absorbed; created 1 |
| **second run** (already mapped) | created 0, reconciled 0, no link, reconciliation reads skipped entirely |
| two entries claiming one game | one reconciles, other inserts; existing game linked exactly **once**, never rewritten |
| unresolvable teams | reported; never matched by name; still inserted as its own row |

---

## 6. Proof of the required safety properties

1. **One GameKey → one canonical game.** Database-enforced: `UNIQUE (provider_name, provider_game_id)`.
2. **One canonical game cannot gain conflicting GameKeys silently.** Database-enforced:
   `UNIQUE (game_id, provider_name)`. In code, `link_reconciled_game` reads the existing mapping
   first and **raises** on a different GameKey rather than letting `link_provider_id`'s
   `resolution=merge-duplicates` rewrite it. Same GameKey → idempotent no-op, no write at all.
   Within a single run, a reconciled game is immediately marked mapped so a second entry cannot
   claim it.
3. **Repeat execution is idempotent.** Once mapped, identity resolves by GameKey and the
   reconciliation path is never entered again — proven by a test asserting the candidate and team
   reads are not even performed on a second run.
4. **Finalized games remain terminal.** The `finalized_at=is.null` guard already shipped; a
   reconciled finalized game is linked, refreshed on non-status fields, and keeps its score and
   `final` status.
5. **Mapping an existing game does not create a second row.** The insert path is only reached on
   `NO_MATCH_INSERT`; the dry run asserts the insert route is never called for existing games.

---

## 7. Blueprint amendment

`CHANGELOG.md` → **v4.29 (Volume 3) — MINOR**, four-field format, and
`docs/blueprint/volume-3-database-architecture.md` header bumped v4.28 → v4.29.

Recorded rule: *provider-specific game ids are authoritative when already linked; when a provider
lacks a mapping, deterministic cross-provider reconciliation may use canonical home team + away team
+ bounded kickoff identity; fuzzy/name-only reconciliation remains prohibited.*

No schema migration — the required uniqueness constraints already existed.

---

## 8. Is the ONE SportsDataIO Schedule call now safe to authorize?

**Yes, with one caveat that is a reporting matter, not a safety one.**

What is now proven: existing games link instead of duplicating; finalized Week 1 games keep their
scores and terminal status; genuinely missing Week 2 games still insert; ambiguity refuses rather
than guesses; a re-run writes nothing; uniqueness is database-enforced in both directions.

The caveat: the dry run proves the *algorithm* against dev's real canonical shape, but no real
SportsDataIO Schedule payload has ever been ingested, so the exact kickoff timestamps SportsDataIO
publishes for these specific games are unverified. If its kickoffs differ from the balldontlie-sourced
values already stored by more than ±15 minutes, those entries will insert new rows instead of
reconciling. That is the **loud, visible** failure mode by design — it would show up immediately as
`created` far exceeding the ~285 genuinely-new games, with `reconciled` near zero.

Recommended guard when authorizing: run it, then check `reconciled` ≈ 19 and `created` ≈ 285 before
anything else consumes the result. If `reconciled` is near zero, the tolerance needs revisiting
against real data rather than assumption — and no finalized game will have been harmed either way,
since the terminal guard is independent of reconciliation.
