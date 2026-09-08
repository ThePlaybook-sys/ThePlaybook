# Phase 8.2 — Player / Roster / Depth Activation (2026-09-08)

**Status: real implementation built and tested, real DEV data activated
and verified directly against Supabase. DEV only. No new live
MySportsFeeds calls (the two Phase 8.2 diagnostics' already-captured
real data was reused). No BALLDONTLIE. No SportsDataIO. No purchases. No
recurring polling. No Probability Modeling integration. No Phase 8.1
stub changes. No Phase 4. No Milestone 5.6. No Phase 7.2/7.3. No
staging/prod.**

---

## 1. Files / schema changed

**Schema (migration `20260908150000_mysportsfeeds_provider_identity.sql`,
applied live to DEV):** widens `team_provider_ids`/`player_provider_ids`'
`provider_name` CHECK constraints to allow `'mysportsfeeds'`, same
pattern as the existing `balldontlie` widening
(`20260907193000_balldontlie_provider_identity.sql`).

**Code (permanent):**
- `app/persistence/roster_ingestion.py` — `persist_roster()` now takes
  `provider_name: str = "sportsdataio"` (replacing the module-level
  `_PROVIDER_NAME` constant) and `write_depth_chart_snapshot: bool =
  True`. Every existing caller (`app.master_refresh.run.
  run_master_refresh`, every pre-existing test) is unaffected by the
  defaults — confirmed by running the original 9 tests unchanged before
  writing any new ones, then again after.
- `app/adapters/providers/mysportsfeeds.py` (new) —
  `MySportsFeedsRosterAdapter`, implementing `RosterAdapter` against the
  real `players.json` shape both Phase 8.2 diagnostics confirmed live.
- `tests/test_roster_ingestion.py` — 2 new tests (provider_name
  threading, `write_depth_chart_snapshot=False` behavior).
- `tests/adapters/test_mysportsfeeds_roster_adapter.py` (new) — 13
  tests against real captured field shapes.

**Temporary (built, run, then fully reverted — code only, not data):**
`app/diagnostics/msf_roster_activation.py` and its `main.py` startup
hook, gated behind `RUN_MSF_ROSTER_ACTIVATION`. Same "temporary hook,
then revert" discipline as every prior probe in this project, with one
deliberate difference: unlike the two read-only Phase 8.2 diagnostics,
this hook performed a REAL write, so only the wiring was reverted —
the resulting rows are real, durable DEV data, confirmed still present
after the revert (`723/723` sports-intel-layer tests passing post-revert,
same as the pre-existing 708 + 2 + 13 = 723 permanent-code baseline).

**No Master Refresh wiring touched** — `run_master_refresh`'s own
`roster_adapter` default stays `SportsDataIORosterAdapter`, unchanged.

## 2. Provider generalization

`_PROVIDER_NAME = "sportsdataio"` (module-level, hardcoded) is gone.
`persist_roster(response, provider_name=..., write_depth_chart_snapshot=
...)` is now a real, explicit, provider-neutral callable — the exact gap
the earlier Phase 8.2 audit pass identified. `player_identity.py`/
`team_identity.py` needed no change (already provider-neutral). No
NFL-specific assumption was introduced into `players`/
`player_provider_ids`/`roster_memberships` — those tables were already
sport-agnostic (confirmed by schema read: `position` is free text, not
an NFL enum).

## 3. Real player identity results

**34 real MySportsFeeds players activated**, reusing the exact field
data both Phase 8.2 diagnostics already captured live (no new provider
call) — 17 New England Patriots, 17 Seattle Seahawks, the real
"expected lineup" players for game 163541 (NE @ SEA, 2026-09-10).
`players` table: 6 → 40 rows (the 6 pre-existing rows are unrelated
fixture data, untouched). All 34 carry a real `player_provider_ids` row
(`provider_name='mysportsfeeds'`, `provider_player_id` = MySportsFeeds'
own real numeric `player.id`, e.g. `9999` for Hunter Henry, `39182` for
Chris Paul Jr.). Verified directly via SQL join, not assumed from
application logs.

**Scope, disclosed plainly:** this is the 34-player "expected lineup"
subset both diagnostics already had full field data for — not each
team's complete ~53-man active roster. A future pass wanting full-roster
coverage needs a fresh `players.json` scan for every NE/SEA row (the
whole-league payload has all of them; only these 34 were ever
individually captured with full field data this project can point to
without a new live call).

## 4. Real roster results

**34 `roster_memberships` rows, one per activated player, zero
duplicates.** Verified via SQL: `count(*) = 34`, `count(distinct
player_id) = 34`. Each player correctly linked to the real canonical
`teams.id` for New England Patriots or Seattle Seahawks (the same
canonical team rows BALLDONTLIE/SportsDataIO/The Odds API already
resolve to) via two real, explicitly-seeded `team_provider_ids` rows
(`provider_name='mysportsfeeds'`, `provider_team_id='NE'`/`'SEA'`) —
seeded directly via SQL, not guessed, since `team_identity.
resolve_team_ids` is read-only by design and never auto-creates a
mapping.

## 5. Real depth/lineup results

**Zero `depth_chart_snapshots` rows written this pass, by design.**
`write_depth_chart_snapshot=False` was passed for every activation call,
since `players.json` carries no depth/rank field of any kind (confirmed
absent in both diagnostics) — writing a "snapshot" of nulls would have
misrepresented roster membership as a real depth/lineup observation,
which HQ's own "do not infer depth from players.json" guardrail
explicitly forbids. Verified via SQL: `0` `depth_chart_snapshots` rows
joined to any `mysportsfeeds` team.

**Lineup-ID resolution verified deterministically**, per HQ's item 3:
every one of the 34 real player IDs the 2026-09-03 gap test's
`lineup.json` capture reported now resolves, through the
newly-populated `player_provider_ids`, to a real canonical `players.id`
— because these are the exact same 34 players this pass activated. This
confirms the join path (`lineup.json` player ID → `player_provider_ids`
→ canonical `players`) works correctly end to end; it does not mean
depth/lineup role itself is persisted anywhere yet — that remains a
separate, not-yet-built persistence path (see §10).

## 6. Identity/data-quality validation

- **Hunter Henry / MSF ID 9999 — resolves correctly.** `players` row:
  `name='Hunter Henry'`, `position='TE'`, team = New England Patriots,
  linked `player_provider_ids` row: `provider_player_id='9999'`. Not a
  placeholder, not a collision — a real, distinct player.
- **Chris Paul Jr. — resolves correctly.** `players` row:
  `name='Chris Paul Jr.'`, `position='ILB'`, team = Seattle Seahawks,
  `provider_player_id='39182'`.
- **No NBA identity contamination:** a direct `players` table search for
  `name ilike '%chris paul%'` returns exactly one row — this real NFL
  linebacker, correctly named with the "Jr." suffix this time (pass #1's
  own reference-tuple mis-split, corrected in the diagnostic #2 report,
  carried through correctly into this activation's own hardcoded real
  data). No separate "Chris Paul" (without suffix) row exists, no
  duplicate, no cross-sport collision of any kind.
- **Zero ID collisions:** a `GROUP BY provider_player_id HAVING
  count(*) > 1` query against every `mysportsfeeds` `player_provider_ids`
  row returns zero rows.

## 7. Idempotency / history validation

**Verified live, not just asserted from code review.** The activation
hook was deliberately fired a second time (safe — it makes zero live
MySportsFeeds calls, only Supabase writes from the same already-captured
data, so this doesn't touch the "no additional provider diagnostic"
guardrail). Real second-run result, read directly from Railway deploy
logs:

```
NE:  players_created=0, players_confirmed=17, memberships_inserted=0, memberships_unchanged=17
SEA: players_created=0, players_confirmed=17, memberships_inserted=0, memberships_unchanged=17
```

Zero new rows, zero duplicates — confirmed both by the result counters
and by re-querying Supabase directly afterward (`players` stayed at 40,
`roster_memberships` stayed at 34). **Historical/append-only semantics
remain intact**: `roster_memberships` has no `UPDATE`/`PATCH` path in
this module at all (only `POST`), matching the DB-level append-only
trigger; a real team change for one of these 34 players in a future
activation would insert a new row, never mutate this one.

## 8. Phase 8 dimensions newly unlocked (assessment, not implementation)

Per HQ's own framing ("reassess," "determine which can now move") this
is an analysis deliverable, not a code change — Phase 8.1's
`unsupported.py`/`engine.py` are untouched this pass, per guardrail.

| Dimension | Status after this activation |
|---|---|
| `roster_role` | **Real data now exists** (34 real `roster_memberships` rows) — but only for 2 of 32 NFL teams and only the "expected lineup" subset, not full rosters. Building the real dimension logic (comparable-pool construction, sample-size floor, etc.) is separate future work, not done here. |
| `depth_lineup` | **Still fully blocked.** No `depth_chart_snapshots` data exists for any provider — this activation deliberately did not write any, per §5. |
| `player_performance` | **Partially unlocked** — real player identity now exists for 34 players, but no player-stats source is activated by this pass; stats remain the separate, unaddressed gap the original Phase 8.2 audit named. |
| `injuries` | Unchanged — still blocked by the BALLDONTLIE unpaid-invoice issue, unrelated to this activation. |
| `team_performance` | Unchanged — still blocked by missing team-stats persistence work. |
| `game_state_pbp` | Unchanged — still blocked by PBP/box-score validation, explicitly out of scope. |

## 9. Remaining blockers

1. Only 2 of 32 NFL teams have any real roster/identity data, and only
   the 34-player "expected lineup" subset within those two — not
   full-roster coverage.
2. No depth/lineup persistence path exists yet (`lineup.json`'s real
   role-label shape doesn't map onto `depth_chart_snapshots`'
   SportsDataIO-shaped numeric-rank convention without new design work
   — a real architecture decision, not resolved this pass).
3. No recurring polling exists for any of this — every real row here
   came from a one-time manual activation, per guardrail.
4. Phase 8.1's dimension logic itself (`roster_role`, `depth_lineup`)
   still needs to be built even once more data exists — this activation
   only proves the identity substrate, not the contextual-intelligence
   consumer of it.

## 10. Recommendation for the next Phase 8 pass

Two independent, real next steps, not both required together:

- **Broaden identity coverage**: one real `players.json` call (already
  proven reliable, ~1.2s uncached) scanned against every NE/SEA row (not
  just the 34 already-known) would give full-roster coverage for these
  two teams; extending to all 32 teams is the same mechanism, more rows.
- **Depth/lineup persistence design**: a real architecture decision on
  how `lineup.json`'s role-label shape (`"Offense-RB-1"`, etc.) should
  populate `depth_chart_snapshots` — likely a new jsonb shape distinct
  from SportsDataIO's numeric `DepthOrder` convention, or a schema
  extension. Worth a dedicated design pass before building the writer,
  not force-fit into the existing `write_depth_chart_snapshot=True`
  path.

Building real `roster_role`/`depth_lineup` dimension logic into Phase
8.1's engine is a reasonable follow-on once either of the above lands,
but is explicitly not proposed as the very next step — HQ's own "Do NOT
wire contextual intelligence into Probability Modeling yet" applies with
equal force to not prematurely building a dimension against 2-team,
partial-roster data.

---

## Diagnostic execution debt (item 8 — named, not fixed this pass)

Both prior Phase 8.2 diagnostic passes disclosed the same real
operational failure mode: setting a Railway environment variable to
trigger a one-shot startup hook can produce two overlapping deployments
rather than one, and the protective mitigation (poll, then flip the
variable back before the second container boots) is timing-sensitive —
it worked in diagnostic #1 and this pass's roster activation, but missed
the window in diagnostic #2, causing two real MySportsFeeds calls
instead of one.

**This pass's own activation hook was NOT exposed to this risk in the
same way** (its "second call" was a deliberate, safe, zero-live-call
idempotency test, not an accidental one) — but the underlying Railway
behavior is unchanged and will recur for any future one-shot hook.

**Recommended for a future pass, not built here (explicitly out of
scope per HQ's "do NOT build that infrastructure in this pass"):** an
inherently once-only execution mechanism, e.g. a durable "has this
one-shot flag already fired" marker (a tiny dedicated table or a
Supabase-backed lock, checked and set atomically at the top of the
hook) so a second overlapping container observes the marker and skips,
rather than relying on a human polling Railway's deployment API fast
enough to win a race. This would make future diagnostic/activation
passes robust to the same overlapping-deployment behavior without
requiring perfect timing from whoever runs them.

---

**Guardrails held throughout:** DEV only; zero new live MySportsFeeds
calls (both diagnostics' already-captured real data reused); zero
BALLDONTLIE calls; zero SportsDataIO calls; zero purchases; zero
recurring polling configured; zero Probability Modeling integration;
zero Phase 8.1 stub changes; zero Phase 4/Milestone 5.6/Phase 7.2-7.3
touched; zero staging/prod. No invented data anywhere — every persisted
field traces to a real, previously-captured MySportsFeeds API response.
723/723 sports-intel-layer tests passing after the temporary activation
wiring was reverted (15 new permanent tests: 2 roster_ingestion
generalization + 13 adapter — the 3 tests for the temporary activation
module were removed along with it).
