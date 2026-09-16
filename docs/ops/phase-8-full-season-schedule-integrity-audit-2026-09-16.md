# Full-Season Schedule Integrity Audit — the 271 vs 272 Discrepancy

**Date:** 2026-09-16
**Directive:** MANSA HQ — "FULL-SEASON SCHEDULE INTEGRITY AUDIT"
**Type:** AUDIT ONLY — **zero provider calls**, zero writes. No odds, no recommendations.
**Verdict:** One game is genuinely missing. **Root cause found, exact game identified, no second
provider call required to diagnose it.**

---

## 1. Expected vs actual

| | Games |
|---|---|
| Expected (32 teams × 17 ÷ 2) | **272** |
| Actual SportsDataIO-mapped regular-season games | **271** |
| **Missing** | **1** |

The 4 legacy fixture rows are **excluded** — they carry no SportsDataIO mapping, are dated
2026-08-04 → 08-16 (preseason), and correspond to no 2026 regular-season game. They are not season
coverage and were not counted.

## 2–3. Per-team counts — exactly two teams short

| Home / Away | Teams | Which |
|---|---|---|
| 9 home / 8 away | 15 | all NFC except ATL |
| 8 home / 9 away | 15 | all AFC except CIN |
| **8 home / 8 away = 16 games** | **2** | **ATL, CIN** |

Thirty teams have exactly 17. The split is a perfect conference pattern — in 2026 the **NFC hosts**
the 17th interconference game — which makes the anomaly unambiguous: **ATL is one home game short,
CIN is one away game short.** One missing game explains both.

## 4. Week/team duplication — none

Zero exact duplicates, zero same-matchup-same-day duplicates, zero GameKeys mapped twice, zero
games carrying two GameKeys. No team appears twice in any week.

**The bye table localises the gap.** Counting idle teams per week gives 34 idle slots where 32
(one bye each) are expected. The two extras are exactly **CIN (idle weeks 6 *and* 9)** and **ATL
(idle weeks 9 *and* 11)**. Week 9 currently holds 14 games with ATL, CIN, PIT, TEN idle. Adding one
ATL–CIN game in Week 9 resolves every anomaly at once: Week 9 → 15 games, CIN's bye settles on
Week 6, ATL's on Week 11, and the season reaches 272.

## 5–6. Root cause — the row WAS returned, and was dropped before persistence

From `sports-intel-layer`'s own run log (deployment `67ebc435`, 12:45:55 UTC), the adapter's
row-level isolation skipped **33 rows**, in two classes:

**(a) 32 rows with `GameKey=None, Status=None`** — one per team. These are SportsDataIO's
**bye-week placeholder rows**, not games. Correctly skipped.

**(b) Exactly ONE real game, refused:**

```
skipping malformed/unrecognized schedule row (GameKey='202610902', raw Status='Scheduled'):
unrecognized StadiumDetails.Type 'Retractable Dome'
-- only ['Dome', 'Outdoor', 'RetractableDome'] are CONFIRMED from live data,
   not silently mapped
```

**This is the missing 272nd game**, and the arithmetic closes exactly:

> **271 persisted + 32 bye placeholders + 1 refused = 304 provider rows.**

That also vindicates the adapter docstring's long-standing "304 captured Schedules rows" figure —
and corrects what I told you last pass. I reported 271 as "the real regular season, a corrected
number, not a shortfall." **That was wrong.** The provider returned 304 rows as documented; 272 of
them are real games; one was dropped by our own code. I should have reconciled 271 against 32×17÷2
before calling it corrected.

**Decoding the GameKey confirms the identity.** The observed format is `2026 1 WW TT`, where `WW`
is the week and `TT` the home team's SportsDataIO TeamID (Week 2: `…0201`=ARI home, `…0202`=ATL
home, `…0203`=BAL home, `…0204`=BUF home). So `202610902` = **Week 9, home team 02 = ATL**.

**Missing game: CIN @ ATL, Week 9, GameKey `202610902`** — Atlanta hosting, which is exactly the
9th home game the NFC-hosts pattern requires ATL to have.

**Why only this row.** It is a per-row inconsistency in SportsDataIO's own data, not a venue
problem. ATL's other 8 home games persisted fine with `RetractableDome` → `retractable_dome`
(weeks 2, 5, 6, 7, 10, 13, 16, 17). This single row spells it `'Retractable Dome'` **with a space**.
Across all 271 persisted games the venue distribution is clean: 180 outdoor, 49 dome, 42
retractable_dome.

The adapter behaved exactly as designed — `_VENUE_TYPE_MAP` is a deliberate strict allowlist that
refuses unknown values rather than guessing, and it logged and isolated the row instead of failing
the whole fetch. **The refusal is correct behavior meeting genuinely new provider data.** Nothing
was silently swallowed; the evidence was in the log.

Not the cause, ruled out: season-type filtering (all 271 are `regular`), null/malformed team
identity (all teams resolved), duplicate GameKey (zero), reconciliation refusal (zero ambiguous,
zero unresolved-team, zero conflicts — the run reported none).

## 7. No unmapped canonical game would close the gap

`GameKey 202610902` appears nowhere in `game_provider_ids`. There is no orphan canonical row that
would bring the total to 272 — the game simply does not exist in the database. The only canonical
rows without a SportsDataIO mapping are the 4 preseason legacy fixtures (§1).

## 8. Week 1 and Week 2 integrity — intact

| Check | Result |
|---|---|
| Week 1 games | **16** |
| Week 1 `status='final'` | **16** |
| Week 1 `finalized_at` set | **16** |
| Week 1 score/timestamp fingerprint | **`483f677b…` — identical to the pre-refresh baseline** |
| Week 2 games | **16**, all SportsDataIO-mapped |

---

## Answers

- **Expected season total:** 272
- **Actual real season total:** 271
- **Exact missing game:** **CIN @ ATL, Week 9, SportsDataIO GameKey `202610902`**
- **Root cause of 271:** our adapter's strict `_VENUE_TYPE_MAP` allowlist refused the row because
  SportsDataIO spelled that one game's `StadiumDetails.Type` as `'Retractable Dome'` (space)
  instead of `'RetractableDome'`. The provider returned the row; we dropped it before persistence.
  Correct-by-design refusal, logged and isolated — but it cost one real game.
- **Is a second provider call required?** **Not to diagnose — the diagnosis is complete from logs
  and persisted data.** To *recover* the game, yes: one Schedule call is needed, but only **after**
  a one-line code fix, otherwise the same row is refused again. Not urgent: Week 9 is ~7 weeks out
  (early November), and once the fix ships the already-authorized daily cron picks it up on its
  next enabled run at no extra cost.
- **Proposed fix (not applied — needs authorization):** add `"Retractable Dome": "retractable_dome"`
  to `_VENUE_TYPE_MAP` in `app/adapters/providers/sportsdataio.py`. Preferred variant: normalise by
  stripping whitespace before lookup, so any spaced variant of a known value maps correctly while
  genuinely unknown values still raise. Either keeps the strict-allowlist discipline intact.

## Is schedule integrity safe enough to proceed to an Odds Worker proof?

**Yes.** The defect is one game in Week 9, seven weeks away, and it is fully understood. Everything
the Odds Worker proof depends on is sound:

- **Week 2 is complete: 16/16, all mapped, zero duplicates** — that is the slate odds would poll.
- Canonical identity is clean across the whole season: no duplicates, no conflicting mappings.
- Week 1's finalized games are untouched.

The missing game cannot affect odds collection for Week 2, and the gap is loud and recorded rather
than silent. I would fix the allowlist before the next enabled refresh, but it is not a blocker for
proceeding.

---

## Addendum — venue alias fix APPLIED (2026-09-16)

**Directive:** MANSA HQ — "SPORTSDATAIO VENUE ALIAS FIX". **Zero provider calls.**

> **Note:** that directive's message was **truncated mid-sentence** ("…while the strict venue
> allowlist recognizes the known equivalent spelling"). The fix itself was unambiguous — named in
> the title, root cause confirmed in the body, and already proposed and accepted — so it is applied
> here. Anything the message went on to say (in particular whether the recovery Schedule call is
> authorized) was **not** acted on. See "Not done" below.

### What changed

`app/adapters/providers/sportsdataio.py` — `_normalize_venue_type` now matches on the value with
**whitespace removed and case folded**, via a new `_VENUE_TYPE_BY_COSMETIC_KEY` derived from the
existing `_VENUE_TYPE_MAP`.

**The allowlist is not loosened.** It is still exactly the same three CONFIRMED concepts —
`Outdoor`, `Dome`, `RetractableDome`. What changed is that separator and letter-case are now treated
as *formatting of* a value rather than part of it. A genuinely different concept still raises,
is logged, and the row is still isolated rather than aborting the fetch.

The reasoning, recorded in the code: the strict allowlist was not wrong to refuse
`'Retractable Dome'` — refusing unknown strings is what kept this honest and loud. It was refusing
a *cosmetic respelling of something it already knew*, and that distinction is what cost a real game.

### Tests — 15 added, all driven by the real production value

| Test | Proves |
|---|---|
| `…resolves_through_cosmetic_spelling` (5 cases) | `RetractableDome`, **`Retractable Dome`** (the exact value that cost us the game), `retractable dome`, `RETRACTABLE DOME`, padded — all → `retractable_dome` |
| `…other_two_confirmed_venue_types_are_equally_tolerant` (4) | `Outdoor`/`out door`/`Dome`/`DOME` resolve too |
| `…genuinely_unknown_venue_concept_still_raises` (4) | `OpenAirWithPartialCanopy`, `Open Air`, **`Retractable`**, `Roof` still refused — a *partial* match is not a match |
| `…non_string_venue_type_is_refused_not_coerced` | `42` refused, never coerced |
| `…one_refused_row_no_longer_costs_a_game_in_a_multi_row_response` | regression in the real incident shape: a 2-row response where one carries the spaced spelling now persists **both**, not n−1 |

The pre-existing `test_schedule_unrecognized_venue_type_is_isolated_and_skipped` still passes
unchanged — its fixture uses `OpenAirWithPartialCanopy`, a genuinely unknown concept.

**Suite: `sports-intel-layer` 994 passed / 5 failed** — the same pre-existing wall-clock failures in
`test_odds_cadence_persistence.py`, unrelated. Up from 979; +15 tests, zero new failures.

### Not done — needs authorization

- **No provider call made.** The missing game (`202610902`, CIN @ ATL, Week 9) is **still absent**;
  the season is still 271. The fix means the next enabled Schedule refresh will admit it, but that
  refresh has not been authorized or run.
- `MASTER_REFRESH_ENABLED` untouched (**false**); `cron-schedule-refresh` untouched (`0 9 * * *`).
- No odds, recommendations, rosters, or Railway changes.
