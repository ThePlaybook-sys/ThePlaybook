# Restore Instructions — 2026-09-07 DEV Recovery Checkpoint

**Do not run these steps unless real DEV data has actually been lost.**
This checkpoint was created as a precaution (Phase 8.0.5 Pass 2.2,
2026-09-07) while DEV was healthy — restoring it into a healthy DEV project
would be redundant at best and could overwrite newer real data at worst.

## 0. Prerequisites

1. Schema must already exist. If restoring into a fresh/empty Supabase
   project, first replay every migration in `supabase/migrations/` (via
   `supabase db push` or the Supabase MCP `apply_migration` tool, in
   filename order) — this checkpoint contains DATA only, no `CREATE TABLE`
   statements. `MANIFEST.md` lists the exact 40-migrations state this
   checkpoint's data shape assumes.
2. Confirm you are restoring into the intended DEV project
   (`nhwjtsdebgiwskshzqiq`) — never staging/production/demo. This
   checkpoint's data (team/game provider IDs, real captured odds/news) is
   DEV-specific and has no verified correctness for another environment.
3. Run `VERIFY.md`'s checksum check first — do not restore from a file that
   fails `sha256sum -c`.

## 1. Restore order (respect foreign keys)

Insert in this order — later tables reference earlier ones:

1. `games.json` → `games` table
2. `venues.json` → `venues` table
3. `game_provider_ids.json` → `game_provider_ids` table (references `games.id`)
4. `team_provider_ids.json` → `team_provider_ids` table (references `teams.id` —
   confirm the referenced `teams` rows already exist; this checkpoint does
   not include the `teams` table itself, which is expected to be seed/reference
   data already present from migrations)
5. `odds_snapshots.json` → `odds_snapshots` table (references `games.id`)
6. `news_article_history.json` → `news_article_history` table
7. `odds_api_credit_ledger.json` → `odds_api_credit_ledger` table
8. `injury_reports.json` → `injury_reports` table (fixture row — restore only
   if the fixture itself is wanted; skip for a real-data-only restore)

## 2. Restore method

Using the Supabase MCP `execute_sql` tool (or the SQL editor), per file:

```sql
-- Repeat per table, substituting the table name and the file's own JSON
-- array as the VALUES source. Example for games.json:
insert into games (id, external_provider_id, sport_id, league_id, season_id,
  sport, home_team, away_team, scheduled_start, stadium, status, final_score,
  created_at, updated_at, season_type, week, venue_lat, venue_long,
  venue_type, finalized_at, manual_seed, unresolved_poll_attempts, venue_id)
select * from json_populate_recordset(null::games, $1::json)
on conflict (id) do nothing;  -- never overwrite a row that already exists
```

`on conflict (id) do nothing` is deliberate: if some rows already survived
whatever caused the loss, this restore only fills gaps, never clobbers
anything real that's still there. If a full, clean re-seed is genuinely
intended (e.g. restoring into a truly empty project), `on conflict (id) do
update` is the alternative — but confirm that's actually wanted first, since
it can overwrite rows with this checkpoint's older values.

## 3. Post-restore verification

Re-run `VERIFY.md`'s row-count cross-check (§2) against the now-restored
project. Every count should be greater than or equal to this checkpoint's
manifest (equal if nothing existed before restore; greater if some rows
survived independently of this restore).

## 4. What this restore does NOT recreate

- Anything written to DEV after 2026-09-07 ~20:50 UTC (this checkpoint's
  export time) that isn't itself re-exported in a later checkpoint.
- `news_provider_daily_quota` / `news_worker_poll_state` rows (Phase 8.0.5
  Pass 2.2) — these are safe to leave empty; an empty quota/poll-state
  table is always a valid "nothing used yet" starting state, never
  something that needs restoring.
