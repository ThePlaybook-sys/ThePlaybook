# Phase 8.2 — Lineup / Depth Activation (2026-09-08)

**Status: real implementation built and tested, real DEV depth/lineup
data activated and verified directly against Supabase. No new live
MySportsFeeds calls (the already-captured real `lineup.json` evidence
was reused, exactly as HQ preferred). DEV only. No BALLDONTLIE. No
SportsDataIO. No purchases. No recurring polling. No Probability
Modeling integration. No Phase 8.1 logic changes. No Phase 4. No
Milestone 5.6. No Phase 7.2/7.3. No staging/prod.**

**One real execution issue is disclosed up front, not buried:** the
same overlapping-Railway-deployment race the two prior Phase 8.2
diagnostic passes already named as debt happened again this pass —
this time producing 4 real `depth_chart_snapshots` rows (2 per team)
instead of the intended 2. Both rows per team are byte-identical in
content (confirmed by direct comparison), so nothing is corrupted or
inconsistent — but the row count is a real duplicate, not the clean
single-write this pass intended, and it is reported that way in §4/§6
below rather than presented as clean.

---

## 1. Existing depth model verdict

**Schema is sufficient — no migration needed.**
`depth_chart_snapshots(id, team_id, depth_chart_data jsonb not null,
captured_at)` carries zero DB-level shape constraint on
`depth_chart_data` (confirmed by direct schema read of migration
`20260818070000`). The existing SportsDataIO-facing write path
(`roster_ingestion.py`) already uses this same column for a bare array
of `{player_external_id, name, position, depth_chart_rank}` objects —
a shape built around SportsDataIO's own simpler `DepthOrder`-only
semantics. **MySportsFeeds' real `lineup.json` shape carries real,
useful information that bare-array shape has no room for**: a
per-response `lastUpdatedOn` (provider's own freshness timestamp,
distinct from our `captured_at`), a source game context, and each named
slot's own compound label (e.g. `"Offense-RB-1"`) encoding side +
position-group + sometimes a numeric rank, not just a bare integer.

**Resolution, not a schema change:** this pass's new persistence module
writes its own enriched jsonb *object* shape (not the bare array) into
the same unconstrained column — `roster_ingestion.py`'s existing
SportsDataIO write path is completely untouched, zero regression risk.
Both shapes are equally valid JSON under the same always-unconstrained
column; there is no cross-provider uniform reader today (zero real rows
existed for any provider until this project's own activations began),
so nothing downstream currently depends on one fixed shape.

**Conceptual separation preserved:** the new module
(`app.persistence.lineup_depth_ingestion`) never calls `ensure_player`
or writes `roster_memberships` — it only resolves already-known
identity (read-only, via the same `player_identity`/`team_identity`
functions the roster pass already established as provider-neutral) and
writes depth/lineup data. Player identity, roster membership, and
lineup/depth role remain three separate write paths, never merged.

## 2. MSF lineup mapping

`parse_lineup_slot(label)` splits MySportsFeeds' real compound slot
label into `(side, group, rank)` via regex — `"Offense-RB-1"` →
`("Offense", "RB", 1)`; `"Offense-C"` (no trailing digit) →
`("Offense", "C", None)`, never defaulted to `1`. **Ordering/rank is
only ever recorded when the label itself carries a real digit** — per
HQ's explicit "unknown stays unknown."

**Position fidelity, not label-derived:** each persisted entry's
`position` field comes from the player's own real `position` field
(e.g. `"OLB"`, `"FB"`), not from the label's coarser group segment
(e.g. `"LB"`) — the more directly authoritative source, matching how
canonical identity already stores `primaryPosition`. The raw label
itself is preserved separately as `lineup_slot`, never discarded.

**A real observed data-quality quirk, disclosed rather than
reconciled:** player MSF id `168249` (Brock Lampe, Seattle) has
`player.position == "FB"` but appears under the `"Defense-CB-2"` slot
label in the real captured evidence — an apparent inconsistency inside
MySportsFeeds' own data, not introduced by this pass. Both values are
preserved verbatim in the persisted row (`position: "FB"`,
`lineup_slot: "Defense-CB-2"`), confirmed directly in the activated
Supabase data, neither silently "fixed."

**Unconfirmed slots dropped, never fabricated:** of 80 total lineup
slots in the real captured evidence (40 per team), only the 34 with a
real named player were ever persisted — a `player: null` slot (an
announced-but-unconfirmed depth position) has no `players.id` to
resolve to and is excluded entirely, not represented as a placeholder.

## 3. Files / schema changed

**Schema:** none. (Verdict from §1.)

**Code (permanent):**
- `app/persistence/lineup_depth_ingestion.py` (new) —
  `parse_lineup_slot`, `persist_lineup_depth_chart`,
  `LineupDepthIngestionResult`/`LineupDepthIngestionError`. Read-only
  identity resolution, no player/roster-membership creation.
- `tests/test_lineup_depth_ingestion.py` (new) — 10 tests, including
  the real Brock Lampe mismatch case and an explicit test proving this
  table's append-only (not deduplicated) behavior is intentional and
  matches `odds_snapshots`/`injury_reports`/`weather_snapshots`'
  existing convention.

**Temporary (built, run, then reverted — code only, not data):**
`app/diagnostics/msf_lineup_depth_activation.py` and its `main.py`
startup hook, gated behind `RUN_MSF_LINEUP_DEPTH_ACTIVATION`. Embedded
the real, already-captured `lineup.json` body verbatim — zero new live
calls. Same "temporary hook, but real data persists" discipline as the
prior player/roster activation pass.

## 4. Real depth/lineup rows activated

**4 real `depth_chart_snapshots` rows exist (2 per team), not the
intended 2 — see the disclosure above.** Root cause: the same
overlapping-Railway-deployment race named as debt in both prior Phase
8.2 diagnostic passes recurred; this time the protective flag-flip
landed after a second container had already started and completed its
own real write (confirmed via that container's own deploy log,
timestamped ~15:52:15, thirty seconds before the container whose logs
were actually inspected in real time, ~15:52:45). **Both rows per team
are byte-identical in `depth_chart_data` content** (confirmed by direct
row-by-row comparison) — the duplication is a real extra write, not
data corruption or non-determinism in the mapping logic. Left as-is,
not deleted: per this project's own established precedent (Pass 2.2's
News quota work), quietly removing real rows to present a cleaner
count would be dishonest bookkeeping.

Per team, per snapshot: **17 entries, 17 distinct players, zero
internal duplication.** `depth_chart_data.provider_name =
"mysportsfeeds"`, `.provider_last_updated_on = "2026-09-03T19:24:29.492Z"`
(MySportsFeeds' own real freshness timestamp, correctly distinct from
this project's own `captured_at` column), `.source_game_external_id =
"163541"`.

## 5. Identity resolution

**34 of 34 named lineup players resolved on the first attempt, zero
unresolved.** Every player in the real lineup evidence was already
linked to a canonical `players.id` by the prior player/roster
activation pass (the same 34-player set), so `resolve_player_ids`
succeeded for all of them without any new identity work. `unresolved_
players`/`unresolved_team` were empty on every real run — confirmed
directly from the deploy log's own structured result, not assumed.

## 6. Provenance / history / idempotency

**Provenance preserved, not fabricated:** `provider_name`,
MySportsFeeds' own `lastUpdatedOn`, and the source game id are all real
fields taken directly from the captured payload, distinct from this
project's own `captured_at` (auto-set at write time). Neither timestamp
is conflated with the other.

**"Idempotent" does not mean "deduplicated" for this table, by
design** — `depth_chart_snapshots` is, and was already, an
append-only, "every real capture is a new row" table (same convention
as `odds_snapshots`/`injury_reports`/`weather_snapshots`, confirmed in
the original migration's own comment), unlike `roster_memberships`'
insert-on-change semantics. A test explicitly proves this: two calls
with identical input produce two rows with byte-identical `entries`
content, matching the pure/deterministic nature of the mapping — the
table's own design has no concept of "this exact capture already
exists, skip it." **What this pass's real 4-row outcome demonstrates is
that the mapping and resolution logic are fully deterministic** (both
duplicate pairs are content-identical), not that the persistence layer
failed to deduplicate something it was ever designed to deduplicate.

## 7. Phase 8 dimensions unlocked (reassessment, not implementation)

Per HQ's own framing, an analysis deliverable — Phase 8.1's
`unsupported.py`/`engine.py` remain untouched this pass.

| Dimension | Status after this activation |
|---|---|
| `depth_lineup` | **Real data now exists** for the first time — 34 real, name/position/rank-resolved lineup entries across 2 teams, one real game's worth of "expected lineup" evidence. Still not full-league, still only one game's snapshot, and the dimension's own comparable-pool/sample-size logic in Phase 8.1's engine is not built — the identity+data substrate this dimension needs now exists; the dimension itself does not yet. |
| `roster_role` | Unchanged from the prior pass — real `roster_memberships` data exists for the same 2 teams/34 players, dimension logic still unbuilt. |
| `player_performance` | Unchanged — real identity exists, no stats source activated. |
| `injuries` | Unchanged — still blocked by the BALLDONTLIE unpaid-invoice issue, unrelated to this activation. |
| `team_performance` | Unchanged — still blocked by missing team-stats persistence work. |
| `game_state_pbp` | Unchanged — still blocked by PBP/box-score validation, explicitly out of scope. |

## 8. Whether the 2,322-player capture is reusable

**No — not currently, without a new live call.** The full real
`players.json` payload (2,322 players, captured live by Phase 8.2
Diagnostic #2) was only ever observed two ways: (a) a 5-item capped
sample logged via Railway's `logger.warning` output, and (b) this
session's own tool-result cache files
(`/root/.claude/projects/.../tool-results/...`) — neither is durable,
committed, git-tracked, or part of any project-owned storage. Railway
deploy logs are not retained indefinitely, and this session's own
tool-result cache is ephemeral, scoped to this conversation, not a
project artifact. **Only the 34-player subset this project explicitly
needed was ever transcribed into durable, committed form** (this pass's
own `_REAL_LINEUP_BODY_JSON` and the prior pass's `_REAL_ACTIVATED_
PLAYERS`), now real rows in Supabase — the other ~2,288 players are
effectively gone unless a fresh `players.json` call is made.

**Recommended for a future pass, not done here:** when a full-payload
capture like this is obtained again, durably save it into the
repository itself (matching this project's own established "a durable
location inside the repository survives a lost session, a fresh
workspace, a future Claude session with no memory of this one"
principle, already applied to the Supabase recovery checkpoint in
Pass 2.2) rather than relying on Railway's ephemeral logs or a
session's own transient tool-result cache.

## 9. Remaining blockers

1. Only 2 of 32 NFL teams, only 1 game's "expected lineup" — not
   full-roster or full-league depth/lineup coverage.
2. The full 2,322-player payload isn't durably preserved (§8) — a
   fresh call would be needed to broaden coverage.
3. Phase 8.1's `depth_lineup`/`roster_role` dimension logic itself is
   still unbuilt — this pass proves the identity/data substrate works,
   not the contextual-intelligence consumer of it.
4. The overlapping-Railway-deployment execution risk (named debt from
   two prior passes) materialized again this pass, this time producing
   real duplicate rows rather than a duplicate live call — the
   recommended fix (a durable "already fired" marker) remains unbuilt,
   per guardrail ("do NOT build that infrastructure in this pass" —
   carried forward from the prior directive, still the right scope
   boundary).
5. No player/team performance statistics exist for any provider yet —
   the real next gap toward the contextual-intelligence goal HQ named.

## 10. Recommended next Phase 8 pass

**Real player/team performance statistics is the correct next data
priority**, per HQ's own stated goal (player performance × weather ×
lineup/role × teammates × opponent × game conditions) — everything
built across this Phase 8.2 arc (canonical identity, roster membership,
now lineup/depth role) has zero value for that goal without a real
stats source. Concretely, in order of smallest-to-largest lift:

1. **Audit whether MySportsFeeds' own `player_gamelogs`/
   `seasonal_player_stats`/`seasonal_team_stats` feeds (real feed keys
   already confirmed present in the vendored SDK's own feed table,
   never yet called) can serve this — same provenance-first,
   diagnostic-before-build discipline as every Phase 8.2 pass so far,
   not assumed working.**
2. Design the canonical `player_stats`/`team_stats` write path
   (`player_stats`/`team_stats_nfl` tables already exist per Volume 3,
   currently fixture-only — a real schema-compatibility audit, likely
   no migration needed, mirroring this pass's own §1 verdict pattern).
3. Only after real stats exist does building the actual
   weather×lineup×opponent contextual-intelligence engine become
   meaningful — not proposed or built in this pass, per guardrail.

---

**Guardrails held, with the one disclosed exception in §4/§6:** DEV
only; zero new live MySportsFeeds calls (the real, already-captured
`lineup.json` evidence was reused verbatim); zero BALLDONTLIE calls;
zero SportsDataIO calls; zero purchases; zero recurring polling
configured; zero Probability Modeling integration; zero Phase 8.1 logic
changes; zero Phase 4/Milestone 5.6/Phase 7.2-7.3 touched; zero
staging/prod; no invented depth/rank semantics anywhere (every rank
traces to a real digit in a real captured slot label, every unranked
slot stays `null`). 733/733 sports-intel-layer tests passing after the
temporary activation wiring was reverted (10 new permanent tests).
