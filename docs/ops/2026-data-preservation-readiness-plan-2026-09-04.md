# MANSA 2026 Regular-Season Data Preservation Readiness Plan

**STOP BEFORE IMPLEMENTATION — this document is a design/planning
deliverable only.** No migration has been applied, no worker has been
rewritten, no provider/subscription has been changed, and no Railway
service has been touched. This is not Phase 8 implementation and does
not reopen Phase 4 recommendation/probability wiring. It builds
directly on `docs/ops/2026-data-preservation-requirement.md` (the
2026-09-04 audit that first identified this risk) and the new
architecture reservations at Volume 3 §4.3 (Game Events / Play-by-Play)
and §4.4 (News History).

**Season opener: 2026-09-09** (Seahawks host Patriots, kickoff
2026-09-10T00:20:00Z). This document is dated five days before that.

---

## 1. Ephemeral data at risk

Restated precisely, from the prior audit, now with an explicit
"ephemeral vs. backfillable" split:

**Ephemeral — lost permanently, per game, the moment it's played and not
captured:**
- **In-game odds movement.** Odds/Player Props Workers stop at kickoff
  (`Window.STOPPED`) — no live/in-play line data captured today.
- **In-game injury/availability changes** (a player leaving a game, an
  in-game designation). Injury Worker's cadence tiers (`INFREQUENT`/
  `ACTIVE_WEEK`/`FINAL_RAMP`/`INACTIVE_LIST`) all resolve to `STOPPED`
  at kickoff.
- **In-game weather changes** (a storm arriving mid-game, a
  retractable-roof status change). Weather Worker stops at kickoff.
- **Play-by-play / game-event detail of any kind.** No table has ever
  existed for this. Final `team_stats`/`player_stats` capture the
  *outcome*, never the *sequence* that produced it — "game state/script"
  is unrecoverable at any depth, for any game, without this.
- **News timing.** `daily_game_intelligence.news` is overwritten every
  15-minute cycle — the precise moment a trade/suspension/inactive/
  lineup story first became true is already unrecoverable one cycle
  later, independent of the season opener specifically (this gap exists
  today, not only for future games).

**NOT ephemeral — can be backfilled later, lower urgency:**
- **Playing surface** (turf vs. grass). A stadium's surface is
  effectively static, publicly documented, and trivially look-up-able
  after the fact — unlike the categories above, missing this at
  kickoff does not permanently lose anything. Recorded as a real Phase
  8 data requirement (Volume 4 §8.6's own audit already named it), but
  explicitly NOT part of the pre-9/9 urgency this plan is organized
  around.

---

## 2. What is already safely preserved

Unchanged from the prior audit, restated for completeness — this is
real, existing strength, not something this plan needs to fix:

| Category | Table | Real history? |
|---|---|---|
| Injuries (pregame) | `injury_reports` | Yes — append-only, `game_id` + `captured_at` |
| Weather (pregame) | `weather_snapshots` | Yes — same pattern |
| Odds (pregame) | `odds_snapshots` | Yes — same pattern |
| Lineup / depth chart | `depth_chart_snapshots` | Yes — team-keyed, append-only |
| Roster / team membership | `roster_memberships` | Yes — insert-on-change, append-only |
| Referee assignments | `referee_assignments` | Yes — same pattern as odds |
| Venue (static) | `games.venue_lat`/`venue_long`/`venue_type` | Yes — static per game |

---

## 3. Minimum pre-9/9 implementation required

**Recommended for HQ authorization before 2026-09-09** (implementation
itself is not performed by this planning pass):

1. **Apply the Volume 3 §4.3/§4.4 schema reservations as real
   migrations** (`game_events`, `news_article_history`, both append-only,
   both DEV only) — the tables themselves are zero-risk to create early;
   an empty table costs nothing and blocks nothing else.
2. **Wire a raw-capture-only path for `game_events`** — a capture point
   that writes `game_id`/`provider_name`/`raw_payload`/`captured_at`
   unconditionally, with every typed/normalized column left `null`.
   This does not require knowing MySportsFeeds' real field shape, only
   a place to put whatever comes back. **This should be wired to
   consume the SAME already-planned 2026-09-09/10 MySportsFeeds
   live-game validation call** (`docs/ops/nfl-provider-decision-record.md`'s
   existing gate) — not a new, separate provider call.
3. **Wire `news_article_history`'s insert-once-per-article capture**
   into the existing News Worker cycle — a pure additive write
   alongside its current `daily_game_intelligence.news` upsert, no new
   provider calls, no change to News Worker's existing fetch logic.
4. **Extend Weather Worker past kickoff** — zero marginal cost (see
   §8 below), the single cheapest, safest, highest-confidence change
   in this entire plan.
5. **Extend Injury Worker's existing cadence through kickoff** (not a
   new call type — continuing its already-running bulk-fetch cadence
   rather than stopping it) — near-zero marginal cost.

**Deliberately NOT recommended before 9/9:**
- Any normalization logic for `game_events`' typed columns (`period`/
  `clock`/`event_type`/etc.) — must wait for the live MSF validation
  (§7 below).
- Extending Odds/Player Props capture past kickoff — see §5's
  cost-conscious staging; Odds is a "maybe, coarsely, after Weather/
  Injury prove out" item, Player Props is explicitly deferred.
- Any Phase 8 comparable-situation/contextual-impact logic — out of
  scope entirely, per this task's own explicit instruction.

---

## 4. Proposed provider-neutral PBP/event model

Full schema and reasoning: Volume 3 §4.3. Summary of the design
decision this plan is built on: **the raw provider payload (`raw_payload
jsonb not null`) is the actual preservation mechanism; every typed
column is a best-effort normalization that may legitimately be `null`
until a real payload validates it.** This is the only way to satisfy
"do not fabricate MSF fields or prematurely lock provider-specific
schema assumptions" while still capturing *something* before 9/9 — the
table can be created and written to today without knowing MySportsFeeds'
(or any provider's) exact field names, because the one column that
matters for preservation doesn't depend on knowing them.

Minimum fields for later reconstruction, as requested:
- **Quarter/time:** `period` + `clock` (both kept as unparsed text
  pre-validation).
- **Score/game state:** `score_home`/`score_away` (nullable, best-effort).
- **Player involvement:** `involved_player_ids` (nullable jsonb array,
  populated only once player-identity resolution is validated against
  a real payload).
- **Event type:** `event_type` (a conservative, non-fabricated bucket
  vocabulary — real detail stays in `raw_payload`).
- **Timestamps:** `captured_at` (MANSA's own ingestion clock, not null,
  always populated) is the one timestamp guaranteed from day one;
  in-game clock timing depends on `clock`/`period` once validated.
- **Provider provenance:** `provider_name` (not null) + `provider_event_id`
  (nullable, uniqueness deferred until validated).

---

## 5. Proposed in-game capture strategy (Priority 2)

**Explicitly not uniform across categories** — cost and volatility
differ genuinely by category, so the recommendation does too:

| Worker | Current behavior | Proposed in-game change | Cost posture |
|---|---|---|---|
| **Weather** | Stops at kickoff | **Remove the stop — continue the existing flat 15-min cadence through the game.** Weather changes slowly; a coarse continued cadence loses nothing meaningful. | **Free.** WeatherAPI/OpenWeatherMap already confirmed free-tier-sufficient at current volume (2026-08-10 procurement review) — continuing polling through a ~3-hour game window adds a small, bounded number of calls, comfortably inside existing free-tier headroom. |
| **Injuries** | Stops at kickoff (all tiers resolve to `STOPPED`) | **Continue the existing bulk-fetch cadence through kickoff into the game window**, rather than a new per-game call type — SportsDataIO's Injuries endpoint is already one bulk call covering every team, not a per-game fetch, so this is "don't stop the same call," not "add a new one." | **Near-zero marginal cost** — same call shape, more cycles of it. Does **not** touch the separately-reserved SportsDataIO diagnostic trial call (a distinct, guarded allowance for provider bake-off work) — this is the Injury Worker's own already-running, already-authorized production adapter path. |
| **Odds** | Stops at kickoff, adaptive ramp pregame | **A coarse, distinct in-game tier** (e.g., illustratively every 15-30 minutes for the game's duration) — deliberately coarser than the pregame `RAMP_5M` tier, since in-game odds volatility has a genuinely different shape once markets are live and event-driven rather than time-driven. **Exact interval not locked here** — a real number is implementation work, following this project's own "don't invent a threshold without evidence" discipline. | **Small, bounded, budget-visible.** The Odds API is credit-metered; a coarse in-game tier adds a small, predictable number of extra calls per game (illustratively, on the order of single digits per game) against the already-approved ~40,944-credit/month production projection (2026-08-10) — not free, but not remotely close to threatening that budget either. |
| **Player Props** | Stops at kickoff | **Deferred — no in-game extension proposed by this plan.** Props credits are the most expensive, most volatile line in the existing budget; extending them in-game without a specific, separately-justified need would be exactly the "unnecessary paid API usage" this task's guardrail warns against. | **$0 — explicitly not extended.** Revisit only if a specific Phase 8 (or earlier) need is identified that justifies the cost. |

**The alignment requirement** ("game events ↔ weather ↔ injuries/
availability ↔ market movement") is structurally supported by
`captured_at` already being a shared `timestamptz` convention across
every one of these tables (odds/injuries/weather already share this;
`game_events.captured_at` in §4.3 extends the same convention) — no new
alignment mechanism is needed beyond continuing to populate that column
consistently. Real analytical alignment (joining these tables
meaningfully) is Phase 8's own future work, not this plan's.

---

## 6. Proposed News history model (Priority 3)

Full schema and reasoning: Volume 3 §4.4. Summary: an append-only
`news_article_history` table, **insert-once-per-`(provider_name,
article_url)`** (not a new row every poll, since articles are typically
immutable once published — unlike odds), preserving:
- `ingested_at` — the fact this table exists to capture: when MANSA
  first learned of this article.
- `published_at` — the provider's own claimed publication time.
- `article_url` + `provider_article_id` — stable identity where available.
- `source_name`, `headline`, `summary` — permitted metadata.
- `related_team_ids`/`related_player_ids` — entity attribution,
  including **player-level attribution, which does not exist in the
  current `NewsArticle` model at all** — a real, new addition this plan
  recommends, since injury/inactive/trade news is fundamentally
  player-scoped.
- `provider_name` — provenance.

**Explicitly not a GNews provider-selection decision.** This table is
provider-neutral and would capture whichever provider(s) News Worker
actually calls — today that's NewsAPI Business. The GNews real-time-
entitlement/`expand=content` freshness blocker (`docs/ops/news-provider-decision-record.md`)
remains completely untouched and open; this plan does not select,
reject, or trial GNews, and does not rewrite News Worker's fetch logic
— only proposes where a first-seen timestamp would be written once one
exists.

**Licensing caution, explicitly unresolved:** default posture is
metadata-only (`headline`/`summary`/`source_name`), never full article
body text, until each provider's redistribution terms are independently
confirmed — flagged, not decided, in Volume 3 §4.4.

---

## 7. What must wait for the 2026-09-09 MySportsFeeds live-game test

- **Any `game_events` normalization** — `period`/`clock`/`event_type`/
  `score_home`/`score_away`/`involved_team_id`/`involved_player_ids`
  population logic. Building this ahead of a real payload is exactly
  the "fabricate MSF fields" risk this task's guardrail names.
- **Confirmation of whether MySportsFeeds' PBP/box-score data is usable
  at all** — this is the existing, still-open gate in
  `docs/ops/nfl-provider-decision-record.md`; this plan does not
  duplicate or shortcut that gate, it prepares a place for its output
  to land if the answer is yes.
- **Any `provider_event_id`-based uniqueness/idempotency constraint** on
  `game_events` — deferred until a real payload confirms such an id
  exists and is stable.
- **Whether MySportsFeeds' PBP data (if usable) needs a distinct capture
  path from box-score data**, or whether both fit the same `game_events`
  shape — an open question the live payload itself will answer, not
  guessable in advance.

---

## 8. Estimated API/cost impact

| Change | Provider | Incremental cost |
|---|---|---|
| `game_events`/`news_article_history` tables + raw-capture wiring | N/A (schema + persistence only) | $0 — no new provider calls |
| Weather in-game extension | WeatherAPI/OpenWeatherMap | $0 — already free-tier-sufficient at current volume |
| Injury in-game extension | SportsDataIO (Injury Worker's existing adapter path — distinct from the separately-reserved diagnostic trial call) | Near-$0 — same bulk-call shape, more cycles |
| Odds in-game extension (coarse tier, if authorized) | The Odds API | Small, bounded — illustratively single-digit extra calls/game against the existing ~40,944-credit/month approved projection; not zero, not threatening |
| Player Props in-game extension | The Odds API | **$0 — explicitly deferred, not proposed** |
| MySportsFeeds live-game validation | MySportsFeeds | **$0 incremental** — reuses the single call already planned under the existing live-game validation gate, not a new call |
| News history capture | NewsAPI (current) / GNews (still unselected) | $0 — persistence-layer addition on top of already-scheduled polls, no new fetches |

**Overall: near-zero to small incremental cost**, concentrated entirely
in the optional Odds in-game tier — every other recommended change is
either free or reuses a call that was already going to happen.

---

## 9. Recommended implementation sequence

**All items below require separate HQ authorization before any code is
written — this plan only proposes the order.**

1. **Apply Volume 3 §4.3/§4.4 as real DEV-only migrations** — empty
   tables, zero behavioral risk, unblocks everything else.
2. **Wire `news_article_history`'s insert-once capture into News
   Worker** — pure additive write, no fetch-logic change, $0 marginal
   cost. Lowest-risk, highest-value first implementation step.
3. **Extend Weather Worker past kickoff** — $0 marginal cost, second
   lowest-risk step.
4. **Extend Injury Worker's cadence through kickoff** — near-$0
   marginal cost.
5. **Wire the `game_events` raw-capture path**, targeting the
   2026-09-09/10 MySportsFeeds live-game validation call specifically —
   must be ready *before* that call fires, so step 5 has the nearest
   real deadline of anything in this sequence.
6. **Run the 2026-09-09/10 MySportsFeeds live-game validation** (the
   already-existing, separately-gated task) — produces the first real
   `game_events` rows (raw payload only) and the evidence needed for
   step 8.
7. **Decide on the Odds in-game coarse tier** — the one item with a
   real (if small) cost, deserving its own explicit go/no-go rather
   than bundling it with the free/near-free items above.
8. **Only after step 6**, design and authorize `game_events`'
   normalization logic (`period`/`clock`/`event_type`/player
   involvement) against the real, validated MySportsFeeds payload shape
   — never before it.

Steps 1-4 are the actual "minimum pre-9/9" set (§3 above); step 5 has
the hardest deadline (it must exist before the 9/9 game, or the
opportunity to capture that specific game's raw PBP is itself lost);
steps 6-8 are explicitly post-9/9 work.
