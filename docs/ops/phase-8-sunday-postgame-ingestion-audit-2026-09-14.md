# Sunday Postgame Ingestion Audit (2026-09-14)

MANSA HQ directive: "SUNDAY POSTGAME INGESTION AUDIT." Report-only audit of
all 13 real Sunday Sept 13 NFL games' MSF postgame ingestion status.
**Zero MySportsFeeds calls made in this pass. Zero repairs made.** Every
number below is a live read against the DEV Supabase project
(`nhwjtsdebgiwskshzqiq`), current as of 2026-09-14 12:03 UTC — roughly
15.5 hours after the earliest 1:00 PM ET kickoffs' own first-eligibility
time, and 8+ hours after the SNF game's.

## 0. Canonical Sunday universe cross-check (not assumed from ingestion state alone)

Re-derived the 13-game canonical universe directly from `games`/
`game_provider_ids` (the same ET-anchored window technique as every prior
pass), independent of `game_postgame_ingestion_state`. Result: **exactly
the same 13 games, same MSF ids (163543-163555), as the prior Sunday
enablement pass** — no canonical game added, removed, or renumbered since.
Cross-checked against `game_postgame_ingestion_state`: **13/13 canonical
Sunday games have exactly one ingestion-state row each, zero missing, zero
duplicated, zero extra Sunday rows.** The table's 14th row is the
pre-existing SF@LAR (Week 1, Thursday) state from the prior Live Proof
pass — unrelated to Sunday, untouched.

## 1. 13/13 coverage matrix

| # | Matchup | MSF ID | Kickoff (ET) | State | attempt_count | last_attempt_at | raw_capture_id | Outcome |
|---|---|---|---|---|---|---|---|---|
| 1 | CHI @ CAR | 163543 | Sun 1:00 PM | scheduled | 0 | null | none | **never attempted** |
| 2 | TB @ CIN | 163544 | Sun 1:00 PM | scheduled | 0 | null | none | **never attempted** |
| 3 | NO @ DET | 163545 | Sun 1:00 PM | scheduled | 0 | null | none | **never attempted** |
| 4 | BUF @ HOU | 163546 | Sun 1:00 PM | scheduled | 0 | null | none | **never attempted** |
| 5 | BAL @ IND | 163547 | Sun 1:00 PM | scheduled | 0 | null | none | **never attempted** |
| 6 | CLE @ JAX | 163548 | Sun 1:00 PM | scheduled | 0 | null | none | **never attempted** |
| 7 | ATL @ PIT | 163549 | Sun 1:00 PM | scheduled | 0 | null | none | **never attempted** |
| 8 | NYJ @ TEN | 163550 | Sun 1:00 PM | scheduled | 0 | null | none | **never attempted** |
| 9 | ARI @ LAC | 163551 | Sun 4:25 PM | scheduled | 0 | null | none | **never attempted** |
| 10 | MIA @ LV | 163552 | Sun 4:25 PM | scheduled | 0 | null | none | **never attempted** |
| 11 | GB @ MIN | 163553 | Sun 4:25 PM | scheduled | 0 | null | none | **never attempted** |
| 12 | WAS @ PHI | 163554 | Sun 4:25 PM | scheduled | 0 | null | none | **never attempted** |
| 13 | DAL @ NYG | 163555 | Sun 8:20 PM (SNF) | scheduled | 0 | null | none | **never attempted** |

**All 13 games: `state='scheduled'`, `attempt_count=0`, `last_attempt_at=
null`, `error_classification=null`, `quarantine_reason=null`.** None was
ever promoted past `scheduled` to `eligible_for_postgame_check` — the
`promote_due_scheduled_row` transition only happens when the worker
actually runs, which never happened for any of these 13.

## 2. Failures / gaps

**Not a single one of the 13 games has failed, quarantined, or partially
completed — every one is at the "never attempted" starting line, exactly
where the Sunday enablement pass left them on 2026-09-13.** This is the
central finding of this audit:

- **Zero `game_events` rows** exist anywhere in DEV for any of the 13 MSF
  game ids (163543-163555) — confirmed by direct query, not inferred from
  ingestion state.
- **Zero `player_stats` rows** for any of the 13 canonical game ids.
- **Zero `player_identity_quarantine` rows** for any of the 13 canonical
  game ids.
- **Root cause, confirmed live**: no automatic dispatcher exists anywhere
  in the fleet that calls the permanent worker
  (`run_msf_postgame_capture` / `POST /v1/internal/msf-postgame/run`).
  Checked directly: `app/main.py` defines the endpoint but nothing in this
  codebase calls it on a schedule; Railway's `dev` environment has no
  `cron-msf-postgame`-style service (the full service list was checked --
  `cron-weather-worker`, `cron-news-worker`, `cron-odds-worker`,
  `cron-master-refresh`, `cron-adaptive-weighting`, `cron-postgame-grading`
  [SportsDataIO's separate pipeline, not this one],
  `cron-recommendation-worker`, `worker-scheduled` [a different app,
  `apps/workers`, grepped directly -- zero reference to MSF postgame
  anywhere in it], `worker-market-monitor`, `sports-intel-layer`,
  `ai-orchestrator`, plus the frontend/gateway/root services). **This
  matches exactly what the Sunday 13-Game DEV Enablement report already
  disclosed** ("no cron/dispatcher calls the permanent worker
  automatically for any game") -- nothing has changed since; this is not a
  new regression, it is the same known, disclosed gap, now aged past every
  one of the 13 games' own eligibility windows.
- **DAL@NYG specifically**: its own `next_eligible_attempt_at` (2026-09-14
  03:50 UTC, i.e. 11:50 PM ET) has also now passed (current time 2026-09-14
  12:03 UTC, ~8 hours later) with **zero attempts** -- it did **not**
  complete ingestion after its later eligibility window, for the identical
  reason as the other 12: nothing ever invoked the worker for it either.

**Every one of the 13 games "should have run" in the sense that its own
eligibility window has passed (by 8-19 hours depending on kickoff slot),
but none of them failed to run -- none was ever given the chance to run at
all.** No duplicate-row, idempotency, or stat-persistence issue exists to
report, because nothing has been persisted for any of these 13 games yet.

## 3. Provider-call consumption

**Total MSF calls attributable to Sunday ingestion: 0.** No provider
call was made for any of the 13 games in this pass or since the prior
enablement pass. The only MSF call anywhere in DEV remains the single,
already-reported SF@LAR Live Proof call (`attempt_count=1` on that one,
unrelated, pre-existing row). No cache, rate-limit, or 429 behavior was
observed or is observable, because no request was ever sent for any of the
13 Sunday games.

## 4. Player / stat totals

**0 players captured, 0 player-game rows persisted, 0 newly activated
players, 0 quarantined players, across all 13 games.** Confirmed via three
independent live queries (`game_events` by MSF id, `player_stats` by
canonical `game_id`, `player_identity_quarantine` by canonical `game_id`)
-- all zero, all 13 games, no exceptions.

## 5. Exact repairs required before Phase 8 continues

**No data repair is required or possible yet -- there is nothing to
repair.** No game failed, no row is corrupt, no identity is misresolved.
The one real blocker, and the only thing standing between "13 games ready"
and "13 games ingested," is unchanged from the enablement pass's own
disclosure and is now the critical-path item:

1. **An execution trigger must be authorized and wired** for
   `run_msf_postgame_capture` to actually be invoked per-game, on or after
   each game's own `next_eligible_attempt_at` -- e.g. a new
   `cron-msf-postgame` Railway service (dev) polling
   `game_postgame_ingestion_state` for due rows and calling the existing,
   already-tested `POST /v1/internal/msf-postgame/run` endpoint per game
   (mirroring `cron-odds-worker`'s existing shape), or an equivalent
   dispatcher. This is architecture/deployment work, not a data repair --
   explicitly not done in this pass per HQ's "do not call MSF to fill gaps
   yet" instruction, and not started here since it is real code + a real
   Railway service, not a report.
2. Once wired, all 13 games are individually already-eligible (every
   `next_eligible_attempt_at` has already passed) -- no additional
   preparation, backfill, or state reset is needed on the data side. The
   very first dispatcher run would immediately be able to attempt all 13.
3. No other repair is required: canonical games, MSF mappings, numeric
   team identity, and ingestion-state initialization all remain exactly as
   verified correct in the prior enablement pass, re-confirmed clean by
   this audit's own independent cross-check (Section 0).

## Out of scope, exactly as instructed

Zero MySportsFeeds calls made. Zero repairs made. Phase 7, Context
Intelligence, and recommendations untouched. No cron/dispatcher was built
or enabled in this pass -- the missing-dispatcher finding is reported, not
fixed.
