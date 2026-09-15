# Phase 8 Context → Probability Model Admission Decision (2026-09-15)

MANSA HQ directive: "PHASE 8 CONTEXT → PROBABILITY MODEL ADMISSION
DECISION." **AUDIT/DECISION ONLY -- no `build_evidence()` wiring, no
recommendation-logic change, no probability-calculation change, no
invented weights, no context-derived confidence, no provider calls, no
further prerequisite pass.** This is the gate: it decides which
`ContextPackage` dimensions are permitted to eventually enter
`app.agents.probability_modeling.ProbabilityModelingAgent.build_evidence`,
and under what exact restrictions, so the next authorized Phase 8 pass
can implement that wiring directly against this decision rather than
re-litigating it.

---

## 1. A/B/C admission matrix

| Dimension | Verdict | Historical correctness | Point-in-time safety | Provenance | Completeness semantics | Sample-size | Look-ahead risk | Belongs in probability modeling? |
|---|---|---|---|---|---|---|---|---|
| **venue** | **A -- ADMIT NOW** | Real, static, time-invariant facts (`venue_id`, coordinates, roof type) -- "historical" is structurally moot since nothing changes | Zero risk -- nothing about a venue's identity/location changes over time; no comparable-pool timing dependency for the facts that matter | Real `ProvenanceRef` (venues + games-sharing-venue) | Native derivation via `context_package.py`; `PARTIAL` only affects the comparable-pool similarity score, never the target facts | Comparable pool currently thin (0 for SEA@NE, live-confirmed) but irrelevant to the target facts' own validity | None | Yes -- home/away/venue/roof context is standard, directly relevant |
| **player_performance** | **B -- ADMIT WITH RESTRICTIONS** | Real `player_stats`, deduplicated to one observation per (player, game), real values proven (JSN: 11/8/122/1) | Real, explicit `target_event_timestamp` rule (strict `<` against the historical game's own kickoff); one disclosed, unclosed gap: no true observation timestamp on `player_stats`, so same-day/near-simultaneous precision isn't guaranteed | Full `ProvenanceRef` + `duplicate_raw_row_count` + `canonical_row_id`, always disclosed | Native `data_completeness` (joined/unavailable only, never partial from this dimension) | Always 1 today (no player has 2 real games yet) -- `INSUFFICIENT_SAMPLE_FLOOR` correctly keeps `confidence=None` | Low, but real: the same-day-precision gap (above) is a genuine, not-yet-closed structural limitation | Yes -- directly the evidence a player-prop probability model needs |
| **market** | **B -- ADMIT WITH RESTRICTIONS** | Real `odds_snapshots`, real line-movement math (reused, not duplicated, from Milestone 4.5/7.1) | Target-game's own facts (opening/latest/movement) are inherently chronological/safe. **The cross-game comparable pool has NO explicit point-in-time filter** -- `read_all_odds_snapshots` fetches the whole table with no time cutoff (confirmed by direct code read this pass) -- safe only because a LIVE `build_evidence()` call can never have "future" data in that pool; unsafe if ever reused for historical backtesting without adding an explicit filter | Real `ProvenanceRef` (target + comparable-pool row counts) | Derived (not native) via `context_package.py`'s generic rule | Real comparable pool crosses the floor for SEA@NE (5 other real games with odds, live-confirmed) -- `JOINED` in practice today | **Real, previously undisclosed until this pass's audit**: the comparable-pool gap above | Yes -- market/line context is core betting-relevant evidence |
| **weather** | **B -- ADMIT WITH RESTRICTIONS** | Real WeatherAPI observations since 2026-09-07 | Target-game's own single real reading is safe by construction. **Same undisclosed-until-now comparable-pool gap as market** -- the dome-bucket comparable pool (`all_weather_rows`) has no time filter either | Real `ProvenanceRef` | Derived (not native) | Real coverage is thin: 4 of 16 real completed games have a real weather row; SEA@NE's own comparable pool is 1 (< floor of 2) -> `PARTIAL` | Same comparable-pool gap as market | Yes -- weather is standard, real betting-relevant context |
| **news** | **C -- BLOCK** | Real `news_article_history` data exists for real teams, but **is not reachable for most real games** via the current engine path | N/A -- moot, since the dimension can't even locate its own evidence | N/A | N/A | N/A | N/A | Not admissible in its current, broken state |
| **injuries** | **C -- BLOCK** | Zero real rows for any real game | N/A | N/A | N/A | N/A | N/A | No |
| **roster_role** | **C -- BLOCK** | Real rows exist for only 2 of 32 teams; no active/inactive concept at all | N/A | N/A | N/A | N/A | N/A | No |
| **team_performance** | **C -- BLOCK** | Zero real rows, fixture-linked only | N/A | N/A | N/A | N/A | N/A | No |
| **depth_lineup** | **C -- BLOCK** | Real rows exist for only 2 of 32 teams; point-in-time resolver built but never wired | N/A | N/A | N/A | N/A | N/A | No |
| **game_state_pbp** | **C -- BLOCK** | Real raw captures exist (20 rows) but every typed column is `null` -- no usable evidence, only an opaque blob | N/A | N/A | N/A | N/A | N/A | No |

**Per HQ's explicit instruction, dimensions are not held back waiting for
the weakest one.** venue (A), player_performance/market/weather (B) are
admitted now, on their own merits; the six known-incomplete dimensions
are blocked outright rather than delaying the four that are ready.

---

## 2. Exact reason for every C

- **news**: **Real, confirmed, live bug** (Historical Context Assembly V1
  pass, 2026-09-15) -- `engine.py`'s news path resolves team identity via
  `resolve_team_ids_by_name`'s exact match against `games.home_team`/
  `away_team`, which are inconsistently formatted (short codes like
  `"SEA"`/`"NE"` for many real rows, not `teams.name`'s full names) --
  live-confirmed this dimension reports `UNAVAILABLE` for SEA@NE despite
  real news data existing for both teams. **Blocking, not fixing, per
  this pass's explicit instruction** ("News has a known team-identity
  bug. Classify it accordingly. Do not fix it in this pass.") -- the fix
  (reuse `resolve_team_identity_for_games`, already built for
  `player_performance`'s own opponent resolution) is small and already
  named as the smallest next step in the prior pass's own report, but
  doing it is explicitly out of scope here.
- **injuries**: no real per-game evidence exists anywhere in the
  database for any real game -- the one real row in `injury_reports`
  belongs to a fixture game. Nothing to admit.
- **roster_role**: real data covers 2 of 32 teams (Phase 8.2's own
  activation scope, never broadened), and the schema has no
  active/inactive concept at all -- even where real rows exist, they
  cannot answer the question a probability model would actually need
  ("was this player active for this game").
- **team_performance**: zero real rows; every row is fixture-linked.
- **depth_lineup**: same 2-of-32-team coverage limit as `roster_role`;
  its own point-in-time resolver (`resolve_lineup_point_in_time`,
  `point_in_time.py`) exists and is correct but has never been wired
  into any dimension compute function, so there is no real, tested path
  from "the data exists" to "a usable historical fact" today.
- **game_state_pbp**: real raw captures exist (the MSF postgame pipeline
  writes them), but every typed column (`period`/`clock`/`score_home`/
  `score_away`/`event_type`) is `null` on all 20 real rows -- there is
  no structured evidence to admit, only an unparsed blob.

---

## 3. Exact restriction for every B

### player_performance
1. **Minimum-sample / trend restriction**: a single real observation
   (`sample_size == 1`, true for every real player today) IS real,
   admissible evidence -- it must never be withheld merely for being
   one game. But `build_evidence()` must never treat it as a trend,
   average, or "typical performance" claim, and must never apply any
   smoothing/aggregation logic until `sample_size >= INSUFFICIENT_
   SAMPLE_FLOOR (2)` is genuinely true for that player. Enforcement:
   admit the observation list verbatim; never collapse it into a derived
   summary statistic.
2. **Completeness gate**: admit only when `data_completeness == "joined"`
   for that specific candidate's player/game. `"unavailable"` must never
   be admitted as empty-but-present evidence (see Section 5).
3. **Point-in-time requirement**: `target_event_timestamp` passed into
   `player_performance` must be the real candidate bet's own game
   context (kickoff, or "now" for a live call) -- never an arbitrary
   caller-supplied past timestamp reused without re-verifying
   eligibility. The existing strict `<` boundary must be preserved
   verbatim. The disclosed same-day-precision gap
   (`PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION`) must travel into the
   admitted evidence payload as a carried-forward caveat, never silently
   dropped.
4. **Provenance requirement**: every admitted observation carries its
   full `ProvenanceRef`, `duplicate_raw_row_count`, and `canonical_row_id`
   verbatim -- never summarized down to bare stat numbers.
5. **Opponent-identity handling**: when `opponent` is `None` (unresolved
   -- a real, expected outcome for some real games, not a bug signal;
   cross-player resolution was sanity-checked for only 3 of 16 real games
   so far), the REST of the observation (real stats/usage) must still be
   admitted -- never block an entire observation for one unresolved
   sub-field. The unresolved state itself must be visible in the
   payload, never silently blanked.
6. **No confidence conversion** (see Section 3's shared rule, restated
   here since this dimension's `confidence` is currently always `None`):
   `data_completeness="joined"` must never be read as, or converted
   into, a numeric confidence contribution.

### market
1. **Point-in-time scope restriction**: the target game's own real
   line-movement facts (opening/latest point/price, direction,
   `sample_count`) are admissible as-is. **The cross-game comparable
   pool's `similarity_score`/`confidence` is admissible ONLY for live,
   current-time `build_evidence()` calls** -- since `read_all_odds_
   snapshots` has no time filter, this half must not be reused by any
   future historical-backtest harness without first adding an explicit
   `target_event_timestamp` filter to the comparable-pool query. This
   restriction must be recorded in code (a comment/docstring) at the
   exact call site when the wiring pass happens, not merely in this
   document.
2. **Completeness gate**: on `PARTIAL` (comparable pool below the
   floor), admit the target game's own real facts; leave
   `similarity_score`/`confidence` unadmitted (`None`) rather than
   passing through a low-sample number.
3. **Scale-mixing prohibition**: moneyline price movement must never be
   blended into the point-based (spread/total) comparable-pool signal --
   already enforced inside `market.py`; this restriction travels forward
   into `build_evidence()`'s own documentation so a future maintainer
   doesn't "fix" it into a combined number.
4. **No confidence conversion**: identical shared rule (Section 4).

### weather
1. **Point-in-time scope restriction**: identical shape to market's --
   the target game's own single real reading is safe; the dome-bucket
   comparable pool (`all_weather_rows`, no time filter) is admissible
   for live calls only, with the same before-any-backtest-reuse caveat.
2. **Completeness gate**: `PARTIAL` (today's common real case -- 12 of
   16 real games have zero real weather) admits the target game's own
   real facts (temperature/wind/precipitation/dome status) while leaving
   `similarity_score`/`confidence` unadmitted.
3. **Missing-data prohibition**: a real game with no real weather row
   must enter as `UNAVAILABLE`/absent -- never defaulted to a "typical"
   or "clear/dry" placeholder condition.
4. **Fixture-exclusion requirement**: only rows carrying `weather_data.
   source == "weatherapi"` may ever be admitted (already enforced in
   `weather.py`) -- this must not be bypassed by any future refactor of
   the admission path.

---

## 4. Look-ahead safeguards

1. **The admission gate does not re-verify point-in-time correctness
   itself -- it relies on each dimension's own, already-audited rule**,
   and instead records, per dimension, whether that rule is complete
   (player_performance: yes, with one disclosed same-day gap; venue:
   trivially yes, static facts) or partial (market/weather: target facts
   yes, comparable pool no explicit filter).
2. **The market/weather comparable-pool gap is the single most important
   finding of this audit** -- previously undisclosed, found by direct
   code reading this pass (`read_all_odds_snapshots`/`read_all_weather_
   snapshots` are both whole-table, unfiltered-by-time reads). It is
   safe for `build_evidence()`'s actual, current use (live calls for
   real-time candidate bets, where no future data can exist), and is
   recorded here explicitly as a restriction rather than silently
   assumed safe, so a future historical-backtest reuse of the same
   functions does not inherit an undocumented leakage risk.
3. **Every admitted dimension's evidence must carry its own
   `target_event_timestamp` context forward** (already true for
   `player_performance`; the venue/market/weather target-game facts are
   implicitly scoped to the one real `game_id` being evaluated) so a
   future auditor can always answer "what was this evidence as of."

---

## 5. Missing-data safeguards

1. **`UNAVAILABLE` dimensions (whether C-blocked entirely, or a
   B/A dimension resolving unavailable for a specific real candidate)
   must never appear in `build_evidence()`'s payload as a zero, empty
   string, or any other default value.** Either the key is omitted
   entirely, or it is represented as an explicit `null`/`"insufficient_
   evidence": true` marker -- never silently coerced into something a
   downstream consumer could mistake for a real zero-valued observation
   (e.g., "0 targets" must never be admitted to mean "unavailable
   evidence," only a genuine real 0 from a real observation may ever
   read as 0).
2. **`PARTIAL` dimensions admit only the real sub-facts that exist**
   (venue's static identity, weather's target reading, market's target
   line-movement) and must never admit a `similarity_score`/`confidence`
   value that was itself computed from a below-floor sample -- those
   stay `None` in the admitted payload exactly as the underlying
   `ContextualDimensionResult` already reports them.
3. **A C-blocked dimension must never leak into the payload through
   another dimension's own facts.** (No cross-contamination risk was
   found this pass, but the allowlist design in Section 7 makes this
   structurally impossible regardless.)

---

## 6. Provenance requirements

Every admitted fact, from every admitted dimension, must carry forward
into `build_evidence()`'s payload:

- The full `ProvenanceRef` tuple (`table`, `source`, `row_count`,
  `earliest_at`, `latest_at`) -- never stripped to a bare value.
- For `player_performance` specifically: `duplicate_raw_row_count` and
  `canonical_row_id` on every observation (the anti-duplicate-inflation
  discipline built across three prior passes must not be lost at the
  admission boundary).
- The dimension's own `data_completeness` value (joined/partial --
  unavailable dimensions are excluded per Section 5, not merely marked)
  and, when set, its real `insufficient_evidence_reason` -- so a
  downstream reviewer never has to guess why a `PARTIAL` result is
  partial.
- `ContextPackage.known_limitations` (already deduplicated) should
  travel forward at the package level, not per-dimension, avoiding
  duplication.

---

## 7. Proposed `build_evidence()` interface/contract (design only, NOT built this pass)

```
ContextPackage
    |
    v
ADMITTED_CONTEXT_DIMENSIONS = ("venue", "player_performance", "market", "weather")
    -- the ONE explicit allowlist. A dimension absent from this tuple can
    -- NEVER reach build_evidence(), regardless of what engine.py's own
    -- SUPPORTED_DIMENSIONS or context_package.py later add. Adding a
    -- dimension to engine.py in the future does NOT automatically admit
    -- it here -- that requires a second, explicit admission decision,
    -- exactly like this one.
    |
    v
permitted evidence fields per admitted dimension, ONLY when
completeness != "unavailable" for that specific candidate:
    - dimension name
    - completeness ("joined" | "partial")
    - the real facts/observations the dimension itself computed
      (verbatim, never re-derived or summarized)
    - provenance (Section 6)
    - insufficient_evidence_reason, when set (PARTIAL dimensions)
    |
    v
build_evidence() -- ONE new, additive key, nothing else touched:

    def build_evidence(self, context: SequentialDecisionContext) -> dict:
        return {
            "candidate": {...unchanged...},
            "upstream_findings": [...unchanged...],
            "participation": {...unchanged...},
            "contextual_evidence": {
                "target_event_timestamp": context_package.target_event_timestamp,
                "dimensions": {
                    name: {
                        "completeness": dc.completeness,
                        "reason": dc.reason,
                        "facts": <the dimension's own real facts, verbatim>,
                        "provenance": [...],
                    }
                    for name, dc in context_package.dimension_completeness.items()
                    if name in ADMITTED_CONTEXT_DIMENSIONS and dc.completeness != "unavailable"
                },
                "known_limitations": context_package.known_limitations,
            },
        }
```

**Properties this contract guarantees:**

1. **Blocked dimensions cannot silently enter modeling.** The
   comprehension filters by `ADMITTED_CONTEXT_DIMENSIONS` first --
   `news`/`injuries`/`roster_role`/`team_performance`/`depth_lineup`/
   `game_state_pbp` can never appear in `contextual_evidence.dimensions`
   no matter what state they're in, structurally, not by convention.
2. **Unavailable admitted dimensions are excluded per-call**, never
   zero-filled (Section 5) -- a candidate where e.g. `player_performance`
   happens to be unavailable for that specific player simply omits the
   key.
3. **Purely additive.** No existing key (`candidate`/`upstream_findings`/
   `participation`) is touched, renamed, or reinterpreted -- the fan-out
   committee's own agents and every existing test of `build_evidence()`'s
   current shape remain valid unchanged.
4. **No confidence/probability is computed here.** `contextual_evidence`
   carries only completeness + real facts + provenance -- the existing
   `ProbabilityModelOutput`/response-model layer downstream of
   `build_evidence()` is where any eventual use of this evidence toward
   a probability would happen, and that layer is explicitly untouched by
   both this decision and its eventual implementation pass.
5. **`ADMITTED_CONTEXT_DIMENSIONS` is versioned by being a named,
   grep-able constant** (mirroring `engine.SUPPORTED_DIMENSIONS`'s own
   pattern) -- a future re-admission decision (e.g., promoting `news`
   once its bug is fixed) is a one-line, reviewable diff to this one
   tuple, not a scattered change.

---

## 8. Exact dimensions authorized for the next implementation pass

**`venue`, `player_performance`, `market`, `weather`** -- exactly the
A + B set from Section 1, wired via the `ADMITTED_CONTEXT_DIMENSIONS`
allowlist exactly as scoped in Section 7, carrying exactly the
restrictions named in Section 3 forward into that implementation's own
code comments/docstrings (not merely satisfied by this document existing).

**Not authorized for that pass**: `news` (blocked, bug not fixed),
`injuries`/`roster_role`/`team_performance`/`depth_lineup`/`game_state_pbp`
(blocked, no real evidence). Fixing `news`'s team-identity bug remains a
small, separate, independently-authorizable task -- explicitly not
bundled into the `build_evidence()` wiring pass this decision authorizes,
and not executed by this pass either.

This document makes no code change. No `build_evidence()` wiring, no
recommendation-logic change, no probability-calculation change, no
invented weight, no context-derived confidence, and no provider call
were made or attempted.
