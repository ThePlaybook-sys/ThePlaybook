# Integrity Verification — 2026-09-07 DEV Recovery Checkpoint

Two independent checks. Both should be run together — a checksum match
alone only proves the files haven't changed since export; a live row-count
match proves the export was actually accurate at capture time.

## 1. File integrity (checksums)

From this directory:

```bash
sha256sum -c SHA256SUMS.txt
```

Every line should print `OK`. A `FAILED` line means that file has been
altered (accidentally or otherwise) since this checkpoint was committed —
treat the checkpoint as suspect and re-export from DEV rather than trusting
the changed file.

## 2. Row-count cross-check against live DEV (optional, requires Supabase access)

Run this against the DEV project (`nhwjtsdebgiwskshzqiq`) via the Supabase
MCP `execute_sql` tool, or the Supabase SQL editor directly:

```sql
select 'games' as t, count(*) from games where manual_seed = true
union all select 'game_provider_ids', count(*) from game_provider_ids
union all select 'team_provider_ids', count(*) from team_provider_ids
union all select 'venues', count(*) from venues
union all select 'odds_snapshots', count(*) from odds_snapshots
union all select 'news_article_history', count(*) from news_article_history
union all select 'odds_api_credit_ledger', count(*) from odds_api_credit_ledger
union all select 'injury_reports', count(*) from injury_reports;
```

Compare against `MANIFEST.md`'s row-count table. **A live count HIGHER than
this checkpoint's is expected and fine** (real data keeps accumulating —
this checkpoint is a point-in-time floor, not a ceiling). A live count
LOWER than this checkpoint's is the actual red flag — it means real data
has been lost or deleted since 2026-09-07, and this checkpoint is now the
best available recovery source for the missing rows (see `RESTORE.md`).

## 3. Local JSON structural check (no Supabase access needed)

From this directory:

```bash
python3 -c "
import json, glob
for f in sorted(glob.glob('*.json')):
    data = json.load(open(f))
    assert isinstance(data, list), f'{f}: expected a JSON array'
    print(f, len(data), 'rows, valid JSON')
"
```

Expected row counts per file are in `MANIFEST.md`'s table — this only
confirms the files are well-formed and lists their counts; cross-check
those counts against the manifest by eye.
