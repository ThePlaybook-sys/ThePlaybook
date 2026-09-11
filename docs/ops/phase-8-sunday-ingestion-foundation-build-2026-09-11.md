# Sunday Ingestion Foundation Build (2026-09-11)

MANSA HQ directive: "SUNDAY INGESTION FOUNDATION BUILD." Authorized
implementation of two permanent schema foundations only -- zero
provider calls, zero worker code, zero player-activation code. Both
land in dev via real migrations, real data backfilled via direct SQL,
matching this project's own "schema via migration, real data via
execute_sql" convention.

## 1. Durable postgame ingestion state

**Migration**: `supabase/migrations/20260911200000_game_postgame_ingestion_state.sql`

New table `game_postgame_ingestion_state`, exactly the schema named
(not yet applied) in the accepted Sunday ingestion design, Section 2:

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `game_id` | uuid, not null, FK `games(id) on delete cascade` | |
| `provider_name` | text, not null, check in `('mysportsfeeds')` | room to extend later, same pattern as `game_provider_ids` |
| `state` | text, not null, default `'scheduled'`, check in the 10 named states | `scheduled`, `eligible_for_postgame_check`, `capture_in_progress`, `captured`, `validated`, `confirmed_complete`, `capture_failed_transient`, `capture_failed_permanent`, `validation_failed`, `partially_confirmed` |
| `attempt_count` | integer, not null, default 0 | |
| `last_attempt_at` | timestamptz, nullable | |
| `next_eligible_attempt_at` | timestamptz, nullable | |
| `last_http_status` | integer, nullable | |
| `last_error` | text, nullable | |
| `error_classification` | text, nullable, check in `('transient','permanent')` | deliberately separate from `state`/`last_error` -- keeps "not-ready-yet" (no classification, not a failure), "transient" (short local retry), and "permanent" (stop, escalate) as three distinct signals, exactly as the preflight correction pass specified |
| `raw_capture_id` | uuid, nullable, FK `game_events(id)` | |
| `captured_at` | timestamptz, nullable | |
| `quarantine_reason` | text, nullable | |
| `created_at` / `updated_at` | timestamptz, not null | `updated_at` auto-maintained by the existing, reused `set_updated_at()` trigger function (no new function written) |

**Uniqueness**: `unique(game_id, provider_name)` -- exactly one durable
row per canonical game + provider, enforced at the database level, not
just by application discipline.

**Atomic claim semantics**: no special mechanism beyond the unique
constraint plus the exact `UPDATE ... WHERE state =
'eligible_for_postgame_check' AND next_eligible_attempt_at <= now()`
shape the accepted design already specifies. Postgres's own row-level
locking on `UPDATE` makes this atomic across concurrent
workers/redeploys without any additional locking primitive -- proven
directly in the test suite (Proof 3 below), not just asserted.

**Restart/redeploy safety**: inherent, not a separate mechanism -- every
fact a future worker needs lives in this table, in Postgres, not in
worker memory. Same guarantee `activation_run_markers`/
`master_refresh_runs` already provide.

**RLS**: enabled, zero policies -- the exact "RLS enabled, no policy"
convention already established for `activation_run_markers`/
`odds_api_credit_ledger`/`display_id_counters` (internal accounting
tables, service-role access only via the service key's RLS bypass).
Confirmed via a live Supabase security advisor check after applying:
`game_postgame_ingestion_state` appears in the same INFO-level
"RLS Enabled No Policy" bucket as those tables, not as a new/different
finding.

**Supporting index**: `idx_game_postgame_ingestion_state_eligible` --
partial index on `next_eligible_attempt_at` where
`state = 'eligible_for_postgame_check'`, matching the exact query shape
a future worker's claim tick will run.

**No worker reads or writes this table yet.** This migration only
creates somewhere durable to put state -- wiring a live MSF worker
against it is explicitly out of this pass's scope.

## 2. MSF team identity support

**Migration**: `supabase/migrations/20260911201000_team_provider_ids_multi_identifier.sql`

Widened `team_provider_ids`'s constraint from `unique(team_id,
provider_name)` (`team_provider_ids_team_id_provider_name_key`) to
`unique(team_id, provider_name, provider_team_id)`
(`team_provider_ids_team_id_provider_name_provider_team_id_key`).
**Preserved exactly, untouched**: `unique(provider_name,
provider_team_id)` -- a given provider's own identifier still resolves
to exactly one team, confirmed live via `pg_get_constraintdef` before
and after.

### 32-team MSF numeric-id backfill

Real data, no schema change beyond the widening above -- one atomic,
idempotent `INSERT ... WHERE NOT EXISTS` statement (collision guard on
`(provider_name, provider_team_id)` + per-triple duplicate guard),
using the real numeric MSF team ids recovered and persisted as raw
evidence in the MSF Week 1 Identity Recovery pass. **32 rows inserted**
on first run. **Rerunning the identical statement inserted zero rows**
-- idempotency proven live, not asserted.

## Proofs (all run live against dev, not asserted)

| # | Claim | Result |
|---|---|---|
| 1 | 32/32 NFL teams have their real numeric MSF identity persisted | **32/32** distinct teams carry a `mysportsfeeds` numeric-id row |
| 2 | Existing abbreviation mappings remain intact | All 12 pre-existing `mysportsfeeds` abbreviation rows (ARI, ATL, BAL, BUF, CAR, CHI, DAL, MIA, NE, NYG, NYJ, SEA) re-queried **byte-identical**, untouched |
| 3 | SF numeric 78 resolves uniquely | `provider_team_id='78'` -> exactly 1 distinct `team_id` (San Francisco 49ers) |
| 4 | LAR numeric 77 resolves uniquely | `provider_team_id='77'` -> exactly 1 distinct `team_id` (Los Angeles Rams) |
| 5 | No provider-ID collisions | **0** `provider_team_id` values shared across more than one team (checked across all `mysportsfeeds` rows) |
| 6 | No canonical-team conflicts | 12 teams now correctly hold 2 rows each (abbreviation + numeric), 20 teams hold 1 (numeric only) -- 12x2 + 20x1 = 44 total rows, exactly accounted for |
| 7 | Rerun/backfill is idempotent | Identical statement re-run: **0 new rows** |

## Testing

**New**: `supabase/tests/database/game_postgame_ingestion_state_test.sql`
(pgTAP, 10 assertions) -- run live against dev inside a rolled-back
transaction (0 rows persisted afterward, confirmed):
1. one durable row per (game, provider) -- duplicate insert throws `23505`.
2. two named states (`captured`, `confirmed_complete`) accepted; an
   unrecognized state throws `23514`.
3. the exact claim `UPDATE` shape advances `state`/`attempt_count`; the
   identical claim re-run against the now-claimed row is a no-op
   (`attempt_count` unchanged) -- no double-claim.
4. `attempt_count` remains monotonically queryable across repeated
   eligible/claim cycles -- the foundation contract a future worker's
   own budget check (not built this pass) will read.
5. RLS default-deny holds for both `authenticated` and `anon`.

**Updated**: `supabase/tests/database/team_provider_ids_constraints_test.sql`
-- its own Proof 2b previously asserted the *opposite* of what this
pass's widening now intentionally allows ("a team cannot have two ids
from the same provider"). Rewritten, not just reworded: Proof 2b now
proves a team **can** hold two different ids from the same provider
(the real MSF case this migration exists for); a new Proof 2c confirms
the widened constraint is still real uniqueness enforcement -- the
exact same `(team, provider, identifier)` triple still cannot be
inserted twice. Proof 2a (a provider id cannot map to two different
teams) is unchanged. `plan(4)` -> `plan(5)`.

**All new/updated pgTAP assertions run live against dev inside rolled-back
transactions**: 10/10 pass (new file), 4/5 pass (updated file) -- see
"Blocker discovered" below for the one pre-existing, unrelated failure.

**Full application suite** (`apps/sports-intel-layer`): **783/783
passing**, zero regressions -- no application code was changed this
pass, this confirms the live schema changes didn't break anything any
existing code depends on.

**Security/performance advisors** (live, post-migration): no new
WARN-level findings. `game_postgame_ingestion_state` appears in the
existing INFO-level "RLS Enabled No Policy" bucket alongside
`activation_run_markers` et al. (expected, matches convention). One
INFO-level "unindexed foreign key" on `raw_capture_id` -- consistent
with ~38 other unindexed FKs already accepted across this schema where
the FK isn't itself a hot lookup path; the columns this table's own
query patterns actually filter on (`game_id`, `state`,
`next_eligible_attempt_at`) are covered by the unique constraint and
the new partial index.

## Blocker discovered for the next pass

**Pre-existing, unrelated test-environment mismatch, not caused by this
pass**: `team_provider_ids_constraints_test.sql`'s own **Proof 1b**
("no extra team was created by mapping two provider team ids to one
team") asserts the `teams` table contains only its own two test
fixture rows. This was presumably always run against a fresh, empty
database via `supabase test db`'s isolated migration replay -- run
here against the populated `dev` project (32 real NFL teams plus other
tests' fixtures), it fails because `teams` legitimately has far more
than 2 rows. **Not a regression from this pass** -- Proof 1b's own
assertion, untouched by this migration, is simply incompatible with a
non-empty `teams` table. Every assertion this pass actually added or
changed (2a, 2b, 2c) passes correctly. Flagging for whoever next runs
this suite against a real, populated database rather than a fresh one
-- the fix (scoping the "no extra team" check to the two fixture ids,
the same way Proof 1 itself already does) is small and unrelated to
Sunday ingestion, so it is named here rather than silently patched
outside this pass's authorized scope.

## Out of scope, exactly as instructed

No MSF boxscore worker. No automatic player activation. No
`player_identity_quarantine`. No boxscore provider calls. No
player-game persistence changes. No Context Intelligence wiring. No
recommendation changes. Staging and production untouched.
