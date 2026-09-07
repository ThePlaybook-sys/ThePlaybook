# DEV Recovery Checkpoint — 2026-09-07

**Purpose:** a durable, reproducible snapshot of the real, non-fixture DATA in
the DEV Supabase project that is NOT protected by git-tracked migrations —
see `docs/ops/phase-8.0.5-pass2.1-safety-check-2026-09-07.md` §3 for the full
audit this checkpoint answers. Schema is already fully git-protected via
`supabase/migrations/`; this checkpoint exists only for the real captured
DATA that schema replay alone cannot recreate.

This directory is committed to the repository (not left as an ephemeral
local/session working copy) specifically so it survives a fresh clone, a
fresh session, or this session ending — per HQ's Phase 8.0.5 Pass 2.2
instruction that the export "must not remain only as an ephemeral/local
working copy."

## Source

- **Environment:** DEV (the only ThePlaybook Supabase environment this
  checkpoint covers — staging/production/demo are untouched and out of
  scope for this checkpoint)
- **Supabase project ID:** `nhwjtsdebgiwskshzqiq` (an identifier, not a
  secret — no API key, service-role key, or connection string is included
  anywhere in this directory)
- **Export method:** read-only `SELECT` / PostgREST `execute_sql` calls
  only. Zero writes, zero schema changes, zero project/environment/billing
  mutations were made to produce this checkpoint.
- **Export timestamp:** 2026-09-07, approximately 20:45–20:50 UTC (row data
  captured), re-verified and copied into this durable location approximately
  22:20 UTC the same day — no data changed between capture and this commit.

## Tables and row counts

| File | Table | Rows | Real or fixture |
|---|---|---|---|
| `games.json` | `games` (`manual_seed = true` only) | 8 | Real |
| `game_provider_ids.json` | `game_provider_ids` | 17 | Real |
| `team_provider_ids.json` | `team_provider_ids` | 59 | Real |
| `venues.json` | `venues` | 5 | Real |
| `odds_snapshots.json` | `odds_snapshots` | 138 | Real |
| `news_article_history.json` | `news_article_history` | 97 | Real |
| `odds_api_credit_ledger.json` | `odds_api_credit_ledger` | 1 | Real |
| `injury_reports.json` | `injury_reports` | 1 | Fixture (not real — the one seeded test row, included for completeness) |

**Total: 326 rows across 8 tables.**

Every count above was independently re-verified against a live `execute_sql`
row-count query at export time — see
`docs/ops/phase-8.0.5-pass2.1-safety-check-2026-09-07.md` for the exact query
and the matching result.

## What this checkpoint does NOT cover

- **Schema** (tables, columns, constraints, triggers, RLS policies) — already
  fully covered by `supabase/migrations/` (40 migrations as of this date,
  confirmed matching the live DEV project exactly via `list_migrations`).
  Restoring schema means replaying those migrations, not this checkpoint.
- **`news_provider_daily_quota` / `news_worker_poll_state`** (Phase 8.0.5
  Pass 2.2, added after this checkpoint was originally captured) — these
  are operational/scheduling state, not data worth a point-in-time recovery
  checkpoint (they self-heal: an empty table just means "nothing used
  today" / "every team due," which is always a safe starting state, never
  a data-loss risk).
- **Supabase's own Backups/PITR mechanism**, if one exists — this session
  has no tool to inspect or configure that. This checkpoint is a
  manual, point-in-time supplement, not a replacement for checking the
  Supabase dashboard's own Database → Backups setting directly.

## Integrity verification

See `VERIFY.md` in this directory.

## Restore instructions

See `RESTORE.md` in this directory.

## Not restored

Per HQ's explicit instruction for the pass that produced this durable
copy (Phase 8.0.5 Pass 2.2, 2026-09-07): **export/verify only — this
checkpoint has NOT been restored anywhere.** The live DEV project already
contains this same real data (this is a checkpoint of currently-live data,
not a recovery-in-progress); restoring is a future action to take only if
DEV's real data is ever actually lost, following `RESTORE.md` at that time.
