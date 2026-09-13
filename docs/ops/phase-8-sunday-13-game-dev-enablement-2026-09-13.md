# Sunday 13-Game DEV Enablement — Preparation (2026-09-13)

MANSA HQ directive: "SUNDAY 13-GAME DEV ENABLEMENT." Initializes durable
MSF ingestion state for all 13 real Sunday Sept 13 NFL games and proves
fleet-safety properties before any execution is authorized. **No
MySportsFeeds call was made anywhere in this pass** — every step here is
a read against already-persisted canonical data, or a single idempotent
SQL write to `game_postgame_ingestion_state` (data initialization, not a
schema change — no migration was needed or applied). **Execution itself
is NOT enabled by this pass** — no cron/dispatcher calls the permanent
worker automatically, and nothing in this pass invokes it.

## 1. The 13 canonical Sunday games, verified before initializing

Queried live: every canonical `games` row with `scheduled_start` inside
the real Sunday Sept 13 ET window (using the same ET-anchored technique
the Week 1 Canonical Schedule Recovery pass established, not a naive
UTC-calendar-day filter — the SNF game lands after midnight UTC and
would be missed by a naive filter):

| # | Matchup | Kickoff (UTC) | Kickoff (ET) | MSF game id |
|---|---|---|---|---|
| 1 | TB @ CIN | 2026-09-13 17:00 | 1:00 PM | 163544 |
| 2 | NO @ DET | 2026-09-13 17:00 | 1:00 PM | 163545 |
| 3 | BAL @ IND | 2026-09-13 17:00 | 1:00 PM | 163547 |
| 4 | NYJ @ TEN | 2026-09-13 17:00 | 1:00 PM | 163550 |
| 5 | ATL @ PIT | 2026-09-13 17:00 | 1:00 PM | 163549 |
| 6 | CLE @ JAX | 2026-09-13 17:00 | 1:00 PM | 163548 |
| 7 | BUF @ HOU | 2026-09-13 17:00 | 1:00 PM | 163546 |
| 8 | CHI @ CAR | 2026-09-13 17:00 | 1:00 PM | 163543 |
| 9 | MIA @ LV | 2026-09-13 20:25 | 4:25 PM | 163552 |
| 10 | GB @ MIN | 2026-09-13 20:25 | 4:25 PM | 163553 |
| 11 | WAS @ PHI | 2026-09-13 20:25 | 4:25 PM | 163554 |
| 12 | ARI @ LAC | 2026-09-13 20:25 | 4:25 PM | 163551 |
| 13 | DAL @ NYG | 2026-09-14 00:20 | 8:20 PM (SNF) | 163555 |

**All four required preconditions verified for all 13, before any
initialization**:
- **Canonical game exists**: all 13 are real `games` rows, `week=1`,
  `season_type='regular'`, `status='scheduled'` (a stale field — see
  the SF@LAR Live Proof pass's own disclosure of why `games.status`
  isn't authoritative for this pipeline; irrelevant to initialization).
- **MSF `game_provider_id` exists**: all 13 have a real
  `game_provider_ids` row (`provider_name='mysportsfeeds'`) — confirmed
  via the same `LEFT JOIN` that would have surfaced a `null` for any
  game missing one; none did.
- **Kickoff timestamp is valid**: all 13 have a real, non-null
  `scheduled_start`, ET-converted above for clarity (`AT TIME ZONE
  'America/New_York'`), not assumed.
- **Matchup/provider identity is internally consistent**: zero
  duplicate canonical games (checked by `home_team`/`away_team`/
  `scheduled_start` grouping) and zero duplicate MSF game ids (checked
  both within these 13 and against the entire `game_provider_ids`
  table) — see Section 3.

**No unrelated game was initialized.** The one pre-existing row (SF@LAR,
from the prior Live Proof pass) was left untouched; the idempotent
insert's own `WHERE NOT EXISTS` guard means it could not have been
touched even if included in the same statement.

## 2. Eligibility — proven individually, from real timestamps

`first_check_at(kickoff) = kickoff + 3h30m` (the already-approved policy,
`app.workers.msf_call_control`), computed from each game's own real
`scheduled_start`, never from a UTC-calendar-day assumption:

| Kickoff (ET) | Kickoff (UTC) | First eligible (UTC) | First eligible (ET) | Games |
|---|---|---|---|---|
| 1:00 PM | 17:00:00 | 20:30:00 | **4:30 PM** | 8 (all 1:00 PM slate) |
| 4:25 PM | 20:25:00 | 23:55:00 | **7:55 PM** | 4 (all 4:25 PM slate) |
| 8:20 PM | 2026-09-14 00:20:00 | 2026-09-14 03:50:00 | **11:50 PM** | 1 (DAL@NYG, SNF) |

All three match the directive's own stated approximations exactly.
Each of the 13 rows carries its own individually-computed
`next_eligible_attempt_at` (not a single shared value applied
blindly) — verified per-row in the table in Section 1's own
initialization result, not just per-tier.

**As of this pass** (current time 2026-09-13 18:13 UTC / 2:13 PM ET,
mid-1:00-PM-slate), no game has yet reached its own
`first_eligible_at` — every one of the 13 rows correctly starts in
`state='scheduled'`, `attempt_count=0`, not `'eligible_for_postgame_check'`.
This is expected and correct: the `scheduled -> eligible_for_postgame_check`
promotion (`promote_due_scheduled_row`) only happens automatically the
next time the worker actually runs at or after each game's own
eligibility time — which requires an execution trigger this pass
deliberately does not create.

## 3. Fleet safety — proven live

| Property | Result |
|---|---|
| Exactly 13 Sunday `game_postgame_ingestion_state` rows | **13** created this pass (table total: 14 = 13 Sunday + 1 pre-existing SF@LAR from the prior pass — no unrelated row) |
| Exactly 13 MSF game mappings | **13**, one per Sunday game, all distinct (`163543`-`163555` excluding `163542`, which is SF@LAR) |
| No duplicate canonical games | **0** rows sharing `(home_team, away_team, scheduled_start)` among the 13 |
| No duplicate provider IDs | **0** `provider_game_id` shared by more than one canonical game, checked against the ENTIRE `game_provider_ids` table, not just these 13 |
| Numeric MSF team identity for every participating team | **26/26** teams (all 13 games' home+away sides) resolve to a canonical `team_id` (via the existing SportsDataIO abbreviation mapping) and each holds **exactly 1** numeric-scheme `mysportsfeeds` `team_provider_ids` row — confirmed live, not assumed from the earlier 32-team backfill |
| Idempotent initialization | Rerunning the identical initialization statement inserted **0** additional rows (`RETURNING` produced an empty set) |
| Atomic claim prevents two workers claiming the same game | **Unchanged, already proven** — `claim_game_for_capture`'s single atomic `UPDATE ... WHERE state='eligible_for_postgame_check' AND next_eligible_attempt_at <= now()` shape, whose no-double-claim property was proven directly in the Sunday Ingestion Foundation Build's own pgTAP suite (Proof 3) and is untouched by anything since |
| Confirmed/partial/final states cannot refetch | **Unchanged, already proven** — `_ALREADY_FINALIZED_STATES` short-circuits `run_msf_postgame_capture` before any fetch attempt; proven directly (`test_already_finalized_game_never_calls_fetch_or_touches_anything_else`, the SF@LAR Live Proof's own live restart test) |
| Hard maximum 4 provider checks per game | **Unchanged, already proven** — `HARD_CAP_ATTEMPTS = 4` (`app.workers.msf_call_control`), enforced identically for every game regardless of outcome (transient failure or not-yet-COMPLETED) |
| Cache `max-age` can delay subsequent not-complete checks | **Unchanged, already proven** — `cache_aware_next_check_at` extends (never shortens) the default 1h follow-up when a real `Cache-Control` header says to wait longer (Pre-Live Worker Hardening pass) |
| 429 `Retry-After` is respected | **Unchanged, already proven** — `retry_after_aware_next_check_at`, same extend-never-shorten guarantee, exercised for real (`_default_fetch_boxscore`'s own 429 handling) |

The last five properties are **not re-derived in this pass** — they are
unchanged code, already proven directly by the existing test suite (and,
for atomic claim/already-finalized, by a real live run in the SF@LAR
Live Proof pass) — cited here, not re-asserted from nothing. Full
`apps/sports-intel-layer` suite re-run before writing this report:
**861/861 passing**, zero regressions (no code changed this pass — pure
live data initialization).

## Out of scope, exactly as instructed

Zero MySportsFeeds calls made. No game's worker execution was triggered
— `state='scheduled'`/`'eligible_for_postgame_check'` transitions beyond
initialization, and any real capture attempt, all remain gated behind a
separate, not-yet-made enablement decision (no cron/dispatcher currently
calls `/v1/internal/msf-postgame/run` automatically for any game). No
schema change. No staging/production. No Context Intelligence. No
recommendation changes.
