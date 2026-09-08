# Phase 8.3A — Team Season Stats Schema + Idempotency Guard + Activation (2026-09-08)

MANSA HQ directive: "PHASE 8.3 NEXT PASS DIRECTION" (2026-09-08), accepting the
2026-09-08 Player/Team Performance Data Audit as the evidence baseline and
authorizing a narrow implementation/design pass (ORDER A–H). This report
covers that pass in full. The separately-authorized Phase 8.3B live
`player_stats_totals` provider call was **not** made — out of scope for
this pass by explicit instruction.

## 1. Files inspected (ORDER step A)

- `supabase/migrations/20260807211421_sports_data_tables.sql` — `games`,
  `seasons`, `team_stats`, `player_stats` original schemas.
- `supabase/migrations/20260818080000_team_stats_player_stats_append_only.sql`
  — **correction to this pass's own prior understanding**: `team_stats`/
  `player_stats` already carry a DB-level append-only trigger
  (`block_snapshot_updates()`, blocks UPDATE, INSERT unrestricted), applied
  2026-08-18. `team_stats.py`/`player_stats.py`'s own module docstrings are
  stale on this point (still say "neither a uniqueness constraint nor that
  trigger" / "not applied now") — flagged in §11, not fixed this pass
  (out of scope: touching those two files was not required by this
  directive and both are otherwise unmodified).
- `supabase/migrations/20260824231700_master_refresh_runs.sql`,
  `20260825000438_recommendations_correlation_id.sql`,
  `20260907120000_odds_api_credit_ledger.sql`, and the News quota/poll-state
  migration — the full existing idempotency/run-tracking landscape (see §5).
- `apps/sports-intel-layer/app/persistence/player_stats.py`,
  `apps/sports-intel-layer/app/persistence/team_stats.py` — full read.
  Confirmed the only real consumers of these two tables anywhere in the
  codebase (grepped), both `(game_id, team/player_id)`-keyed idempotent-
  correction writers, both hardcoded to `_PROVIDER_NAME = "sportsdataio"`
  (unrelated pre-existing gap, out of scope — not touched).
- `apps/sports-intel-layer/app/persistence/team_identity.py` — confirmed
  `resolve_team_ids`/`link_provider_team_id` are already `provider_name`-
  parameterized (Phase 3E-3), no generalization needed for this pass.
- `apps/workers/app/cron_dispatch.py` — full read. Pure infra adapter
  (start → POST one internal endpoint → log → exit); no per-execution
  idempotency of its own, confirms no existing scheduled-worker mechanism
  already covers "prevent a one-shot hook from firing twice." No
  `player_stats`/`team_stats`/season-stats target exists in its dispatch
  table yet — this stays a diagnostics-hook activation, not a cron target,
  this pass.
- `docs/ops/phase-8.2-lineup-depth-activation-2026-09-08.md` and its
  companion diagnostic reports — reviewed for the exact "temporary hook,
  real data persists" deployment/verification pattern this pass reuses,
  and for the disclosed overlapping-Railway-deployment race this pass's
  guard is built to close.
- Local scratchpad capture `msf_run2_parsed.json` (this session's own
  cache of the 2026-09-03 gap test's raw MySportsFeeds responses) —
  inspected directly to determine the honest scope of "already-captured
  real data" (see §6).
- Live DEV schema (`information_schema.columns`) for `games`, `seasons`,
  `team_stats`, `player_stats`, `teams`, and live rows in `teams`,
  `team_provider_ids`, `seasons` — queried directly via Supabase MCP
  before writing the migration and before writing the activation payload.

## 2. Existing architecture discovered

**Idempotency/run-tracking precedents, none of which duplicate the needed
mechanism** (see also the audit report's own survey):
- `master_refresh_runs` — tracks whether a slate-wide Master Refresh run
  completed; not a per-hook-execution guard.
- `recommendations.correlation_id text unique` — closest single-column
  precedent; nullable/backward-compatible, natural unique-conflict
  semantics.
- `odds_api_credit_ledger` — quota accounting, RLS enabled, no public
  policy ("internal accounting" convention).
- `news_provider_daily_quota` / `news_worker_poll_state` — per-entity
  due/not-due gating, both RLS enabled with a `public_read` policy.

None of these solve "prevent one temporary activation pass's one-shot
write from firing twice when two containers boot in an overlapping
window" — the exact, twice-disclosed failure mode from the two prior
Phase 8.2 activation passes. A new, minimal mechanism was justified.

**Team identity infrastructure was already provider-agnostic**
(`team_identity.py`), so no changes were needed there — only new
`team_provider_ids` *rows* (data, not code) for the additional teams this
pass needed.

## 3. Exact schema change

Migration `supabase/migrations/20260908160000_team_player_stats_season_scope.sql`,
applied live to DEV (`nhwjtsdebgiwskshzqiq`):

```sql
alter table team_stats
  alter column game_id drop not null,
  add column season_id uuid references seasons(id),
  add constraint team_stats_game_or_season_scope
    check (game_id is not null or season_id is not null);

alter table player_stats
  alter column game_id drop not null,
  add column season_id uuid references seasons(id),
  add constraint player_stats_game_or_season_scope
    check (game_id is not null or season_id is not null);

create index idx_team_stats_season_lookup
  on team_stats (team_id, season_id, created_at desc)
  where season_id is not null;

create index idx_player_stats_season_lookup
  on player_stats (player_id, season_id, created_at desc)
  where season_id is not null;

create table activation_run_markers (
  id uuid primary key default gen_random_uuid(),
  run_key text not null unique,
  completed_at timestamptz not null default now()
);

alter table activation_run_markers enable row level security;
```

`season_id` reuses the existing `seasons` entity exactly as HQ instructed
— no new season concept invented. `player_stats` was widened identically
to `team_stats` for schema symmetry and to be ready for the separately-
authorized Phase 8.3B pass, even though this pass does not write to
`player_stats` (no player-level data was activated this pass — see §6).

**Data seeded alongside the schema change (direct SQL, not a migration —
matches this session's existing precedent for provider-identity rows,
e.g. NE/SEA earlier this session):**
- `seasons`: one new row, `league_id` = the existing NFL league,
  `year = 2025` (id `69e16fee-8e52-4158-829e-786ebe9740e0`). The existing
  `year = 2026` row (id `a2000000-0000-0000-0000-000000000003`) was reused
  unchanged.
- `team_provider_ids`: 10 new `mysportsfeeds` rows (ARI, ATL, BAL, BUF,
  CAR, CHI, DAL, MIA, NYG, NYJ), each mapped to an already-existing
  internal `teams` row, using the same abbreviation-string
  `provider_team_id` format already established by the NE/SEA rows seeded
  earlier this session (confirmed by direct query before choosing this
  format, not assumed).

## 4. Backward-compatibility analysis

**Strictly widening, zero risk to existing data or code:**
- Every existing `team_stats`/`player_stats` row already has a non-null
  `game_id`, so the new `check` constraint is satisfied by 100% of
  existing rows with no backfill.
- The only real consumers anywhere in this codebase —
  `app.persistence.team_stats.persist_team_stats` /
  `_latest_team_stats_row`, and the identical pair in `player_stats.py`
  — always pass a real, non-null `game_id` at every existing call site
  (confirmed by reading both files in full). Their game_id-keyed lookups
  are unaffected by the new nullable column or the new index (indexes
  only add query plans, never remove one).
- Phase 8.1's `unsupported.py` only names `team_stats`/`player_stats` in a
  text string, not a live query — unaffected.
- No Phase 4, Milestone 5.6, Phase 7.2/7.3, or Probability Modeling code
  path touches either table — confirmed by grep, none touched this pass.
- The append-only trigger (`block_snapshot_updates()`, §1) applies to
  UPDATE only; the new columns don't change INSERT behavior, and the new
  `persist_team_season_stats()` function is INSERT-only, matching its
  game-scoped sibling.

## 5. Idempotency mechanism found/proposed → implemented

No existing mechanism covered this need (§2). Implemented
`activation_run_markers` (id, `run_key text not null unique`,
`completed_at`), RLS enabled, no public policy — same "internal
accounting" convention as `odds_api_credit_ledger`. A hook calls
`POST /rest/v1/activation_run_markers {run_key: "..."}` before any real
write; PostgREST's own unique-constraint enforcement returns `409` on a
duplicate `run_key` with **no explicit `ON CONFLICT` clause needed** —
simpler than the audit report's earlier draft (which had proposed an
explicit `INSERT ... ON CONFLICT DO NOTHING`). The caller catches 409 and
returns `{"skipped": true, ...}` without touching `team_stats`. Verified
directly (§8): a mocked 409 response causes zero `team_stats` calls.

## 6. Implementation performed

**Schema (permanent):** §3's migration, applied live to DEV.

**Code (permanent):**
- `apps/sports-intel-layer/app/persistence/team_season_stats.py` (new) —
  `TeamSeasonStatLine`, `TeamSeasonStatsPersistResult`,
  `persist_team_season_stats(lines, *, season_id, provider_name)`. Kept
  separate from `persist_team_stats` (own `(team_id, season_id)`-keyed
  "latest row" lookup) rather than overloading it, matching this arc's
  established `lineup_depth_ingestion.py`-vs-`roster_ingestion.py`
  pattern. INSERT-only (never PATCH/PUT), same idempotent
  insert-only-if-different behavior as its game-scoped sibling.
- `apps/sports-intel-layer/tests/test_team_season_stats_persistence.py`
  (new) — 7 tests: first-fetch-always-inserts, identical-check-inserts-
  nothing, genuine-correction-inserts-new-row, unresolved-team-reported,
  empty-input-no-calls, raises-on-insert-failure, never-issues-an-update.

**Temporary (built, run, then reverted — code only, not data):**
`apps/sports-intel-layer/app/diagnostics/msf_team_season_stats_activation.py`
and its `main.py` startup hook, gated behind
`RUN_MSF_TEAM_SEASON_STATS_ACTIVATION=1`. Claims the
`activation_run_markers` guard (run_key
`phase-8.3a-team-season-stats-activation-2026-09-08`) before any write,
then calls `persist_team_season_stats` twice against the real, already-
captured payloads described in §6a below — zero new MySportsFeeds calls.

### 6a. The honest scope of "already-captured real data" (surfaced this pass)

The local scratchpad capture of the 2026-09-03 gap test's
`team_stats_totals.json`/`standings.json` responses was itself already
capped to 6 teams each when logged
(`_teamStatsTotals_truncated_for_log: true` / `_teams_truncated_for_log:
true`, both `_total_count: 32` — the original live responses covered all
32 NFL teams, only 6 survived into this durable, reusable capture). This
was not known before this pass; discovered by direct inspection of the
cached file before writing the activation payload, per this project's
"no invented fields or capabilities" standing guardrail.

**The two 6-team captures are not the same 6 teams:**
- `team_stats_totals_current_season` (2026-2027, season not yet started —
  first game 2026-09-10): **BUF, MIA, NE, NYJ, DAL, NYG**, every value
  real and genuinely zero (`gamesPlayed: 0`) — an accurate reflection of
  "zero games played," not missing/placeholder data.
- `standings_prior_season` (2025-2026, completed season): **ARI, ATL,
  BAL, BUF, CAR, CHI**, real non-zero season totals (e.g. BUF:
  `gamesPlayed: 17`, `passTD: 29`).
- Only **BUF** appears in both. This pass activates exactly these 6+6
  real rows (11 unique teams, BUF twice — once per season) — not all 32
  teams, and this is disclosed rather than presented as full-league
  coverage.

## 7. Tests performed

- `pytest apps/sports-intel-layer/tests/test_team_season_stats_persistence.py`
  — 7/7 passed.
- Full `apps/sports-intel-layer` suite — **740/740 passed** (733 prior +
  7 new), zero regressions.
- Offline end-to-end smoke test (respx-mocked Supabase, run locally, not
  committed): full activation flow inserted 12/12 rows with 0 unresolved
  teams; a second run against a mocked 409 on `activation_run_markers`
  produced `{"skipped": true}` with **zero** calls to `team_stats` —
  confirming the guard actually blocks a duplicate run before this pass
  touched real DEV data.

## 8. Persisted-data verification

**Deployed and fired once, guard proven live, not just in tests.** Base
code was pushed to `dev` and confirmed `SUCCESS` (deployment `cc6c5c7e`)
before the activation variable was set, to avoid racing an in-flight
deploy. Setting `RUN_MSF_TEAM_SEASON_STATS_ACTIVATION=1` produced **two**
container boots in an overlapping window — the same disclosed Railway
race from both prior Phase 8.2 activation passes recurred here too. This
time the guard caught it: one container's deploy log shows
`MSF_TEAM_SEASON_STATS_ACTIVATION_RESULT {"skipped": true, "reason":
"run_key 'phase-8.3a-team-season-stats-activation-2026-09-08' already
claimed -- skipping duplicate activation"}`. Queried directly:
`activation_run_markers` holds exactly **one** row for this run_key.
`team_stats` holds exactly **12** season-scoped rows (6 teams × 2
seasons, §6a), each exactly once — no duplicates, unlike both prior Phase
8.2 activation incidents.

**Field-by-field verification against the source payload** (not assumed):
compared two full persisted `stats` jsonb values against the exact source
entries in the local capture —
- Buffalo Bills, 2026 season: **exact match**, all fields including
  `gamesPlayed: 0`.
- Baltimore Ravens, 2025 season: **exact match**, all fields including
  `gamesPlayed: 17`, `passing.passTD: 23`, `standings.wins: 8`.

Spot-checked 2 of 12 rows field-by-field (the two most structurally
distinct: an all-zero current-season row and a fully-populated
prior-season row); all 12 rows were inserted by the same code path from
the same embedded payload, so this is representative, not exhaustive
per-row verification.

Idempotency guard revert: `RUN_MSF_TEAM_SEASON_STATS_ACTIVATION` set back
to `"0"` (`skipDeploys: true` — no redeploy needed, the temporary hook
code itself is removed in the same commit as this report). The
`activation_run_markers` row, the 12 `team_stats` rows, the 10
`team_provider_ids` rows, and the 1 `seasons` row all remain — real,
durable DEV data, per this project's "temporary hook, but real data
persists" convention.

## 9. Migrations/files changed

- `supabase/migrations/20260908160000_team_player_stats_season_scope.sql` (new)
- `apps/sports-intel-layer/app/persistence/team_season_stats.py` (new)
- `apps/sports-intel-layer/tests/test_team_season_stats_persistence.py` (new)
- `apps/sports-intel-layer/app/diagnostics/__init__.py`,
  `msf_team_season_stats_activation.py` (new, temporary — to be reverted)
- `apps/sports-intel-layer/app/main.py` (temporary hook added — to be
  reverted)
- Direct SQL (not a migration file): 1 `seasons` row, 10 `team_provider_ids`
  rows.

## 10. Deployment/environment impact

DEV only (`sports-intel-layer` service, `nhwjtsdebgiwskshzqiq` Supabase
project). No staging/production/demo touched. Base code deployed via
`git push origin dev` (Railway autodeploy, deployment `cc6c5c7e`,
SUCCESS, verified before touching the activation env var — precisely to
avoid racing an in-flight deploy, the failure mode this pass's own guard
also now protects against at the DB level). Activation triggered via one
`RUN_MSF_TEAM_SEASON_STATS_ACTIVATION=1` variable set (deployment
`64c75f8b`).

## 11. Unresolved risks

1. **Stale docstrings in `team_stats.py`/`player_stats.py`** (§1): both
   still describe the append-only trigger as hypothetical future work,
   when it has been live since 2026-08-18. Not fixed this pass (out of
   scope — neither file was otherwise touched); flagged for a future
   pass's cleanup.
2. **Only 11 of 32 NFL teams have any season-scoped `team_stats` row
   after this pass**, and only for the specific seasons named in §6a —
   not full-league, full-season coverage. A fresh, un-capped live call
   would be needed to close this gap, and is out of scope for this pass.
3. **`player_stats` was widened but not used this pass** — ready for
   Phase 8.3B, but the schema change itself is unexercised by any real
   write yet.
4. Team-level `_PROVIDER_NAME = "sportsdataio"` hardcoding in
   `team_stats.py`/`player_stats.py` (pre-existing, same pattern
   `roster_ingestion.py` had before Phase 8.2) remains unfixed — out of
   scope for this pass, `team_season_stats.py` avoided repeating it by
   taking `provider_name` as a required parameter instead.

## 12. Recommendation for Phase 8.3B

The schema and idempotency guard built this pass are now real
prerequisites for a live `player_stats_totals` call: `player_stats`
already has the nullable `game_id`/`season_id` scope it will need if that
data also turns out to be season-aggregate, and `activation_run_markers`
is available to gate a single-shot Phase 8.3B hook the same way this
pass's hook was gated — recommend reusing it verbatim (new `run_key`)
rather than inventing a second mechanism. Recommend the Phase 8.3B call
be a single, narrow `player_stats_totals` request for the same NE/SEA (or
BUF, given its existing season-stat rows) teams already fully identity-
resolved from Phase 8.2, so any real player-performance data returned can
be persisted immediately without further identity-resolution work.
