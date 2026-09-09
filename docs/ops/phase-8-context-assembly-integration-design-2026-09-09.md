# Phase 8 Context Assembly & Integration Design (2026-09-09)

**Status: DESIGN AUDIT ONLY. No implementation, no schema, no provider
calls, no model wiring, no recommendation-logic change.** Defines exactly
how MANSA should assemble historical context once real per-game player
performance data exists (via a future, separately-authorized Gate A/B
success), building directly on `docs/ops/phase-8-context-intelligence-
readiness-audit-2026-09-09.md`'s findings — this document does not
re-derive that audit's evidence, it designs the architecture the audit's
own NOT READY verdict said was still needed.

---

## 1. Context Assembly Proof

**Required inputs, generically, per dimension:** a target entity id
(`game_id` and, where the dimension is player-scoped, `player_id`), a
target event timestamp (kickoff, or the specific in-game moment for
script/state dimensions), and the real source table(s) that timestamp
must be resolved against. This is not a new shape — it is exactly what
`app/context_intelligence/engine.py::build_contextual_intelligence`
already does for its four real dimensions; the design task is extending
the same discipline to the remaining nine.

**JOINED / PARTIAL / UNAVAILABLE — formalized as a real field, not just
audit vocabulary.** `ContextualDimensionResult.insufficient_evidence`
today is binary. Recommend adding a `data_completeness: "joined" |
"partial" | "unavailable"` field alongside it (design only, not built):
- **JOINED**: a real row exists for the exact target entity + timestamp
  (or the fact is static/time-invariant, e.g. venue coordinates),
  retrieval code exists, no adapter needed.
- **PARTIAL**: real data exists but with a named caveat — current-only
  when historical is needed, coverage begins only after some activation
  date, or the join resolves at a coarser granularity (team-level
  standing in for player-level).
- **UNAVAILABLE**: no real row, no code path, or schema-only.
`insufficient_evidence` stays the boolean a consumer branches on;
`data_completeness` is the honest *why*, useful for the audit trail and
for future debugging, never for the model to reason about differently.

**Provenance requirements**: `ProvenanceRef(table, source, row_count,
earliest_at, latest_at)` already exists and is the right shape. Recommend
two additions when this is actually built: `join_keys_used` (e.g.
`{"game_id": ..., "team_id": ...}`, so a reviewer can see exactly what
resolved the row without re-deriving it) and, critically, splitting
"when was this fact true" from "when did MANSA look it up" — see
Timestamps below.

**Timestamps — three concepts that must never be conflated**:
1. **Event timestamp** — the game's kickoff (or the specific play, for
   game-state/script). The thing context is *about*.
2. **Observation timestamp** — `captured_at` on the snapshot row itself:
   when a provider's fact was actually recorded.
3. **Retrieval timestamp** — "now," when MANSA is asking. For a live
   recommendation these three are close together; for a *historical*
   reconstruction (the whole point of this design), retrieval timestamp
   is far in the future of the other two, and every query must be
   anchored to the **event timestamp**, never to "now." This is the
   single most important discipline in this entire document — see
   Section 3.

**Sample size**: `sample_size`/`INSUFFICIENT_SAMPLE_FLOOR`/
`MIN_SAMPLE_FOR_FULL_CONFIDENCE` (`app/context_intelligence/scoring.py`)
already exist and should be reused verbatim, not reinvented, for the new
dimensions. Note the existing four real dimensions measure "how many
*other* comparable games/observations exist" (a contextual-similarity
sample); a future `player_performance` dimension needs an analogous but
distinct sample: "how many of THIS player's own prior real games exist."
Same floor/full-confidence constants, different population being counted
— document this distinction explicitly when building it, don't silently
reuse one sample-size number to mean two different things.

**Recency**: `recency_weight()`/`RECENCY_HALF_LIFE_DAYS=14.0` reused
as-is. Flag, don't resolve: 14 days was tuned for cross-game contextual
similarity (weather/venue/market); a player's own recent-form signal
plausibly wants a shorter half-life (form and role change week to week
in a way stadium roof type does not) — a parameter decision for whoever
builds `player_performance`, not a default to inherit blindly.

**Uncertainty**: already well-disciplined — `confidence` is `None`, never
a fabricated `0.0`, below `INSUFFICIENT_SAMPLE_FLOOR`; `weighted_mean`
returns `None` rather than dividing by a zero total weight. Preserve
this unchanged for every new dimension. Additionally: uncertainty
introduced by a **PARTIAL** join (team-level data standing in for
player-level, e.g.) must be surfaced as an explicit confounder string,
never quietly folded into the confidence number as if it were the same
kind of uncertainty as a small sample.

**Confounders**: already a `tuple[str, ...]`, with a "standing
confounder" convention (every real dimension discloses "no real
completed-game outcome data exists yet, never a predictive or
outcome-linked claim"). New dimensions need their own, specific
confounders, e.g.:
- `player_performance`: "season-aggregate and per-game data are
  structurally distinct; this result never substitutes one for the
  other" (the exact conflation Section 3 names as a live architectural
  risk).
- `roster_role`/lineup: "reflects the most recent real snapshot at or
  before this game, not a confirmed inactive list; absence from a
  snapshot is not evidence a player did not play."
- teammate presence (Section 5): "reports real, timestamped co-presence
  on the same roster snapshot only — never a causal or predictive claim
  about one player's absence affecting another's performance."

**Insufficient-evidence behavior**: unchanged from today's discipline —
return the same `ContextualDimensionResult` shape with
`insufficient_evidence=True` and a real reason, never omit the dimension
or fabricate a plausible-looking value. `UNSUPPORTED_DIMENSIONS`' current
"fixed stub, no real query attempted" behavior should convert to a real
computed result **one dimension at a time** as each one's real data
arrives — not a single big-bang rewrite the moment any one thing becomes
real. This matches every prior pass's own incremental-authorization
discipline in this project.

---

## 2. `ProbabilityModelingAgent.build_evidence()` mapping

`build_evidence()` (read again this pass, still unmodified) returns
exactly `{"candidate", "upstream_findings", "participation"}`. The named,
not-yet-taken integration point (`engine.py`'s own docstring) is one new
key: `"contextual_performance": contextual_intelligence.to_json()`. This
section maps every Phase 8 dimension onto that future key.

| Dimension | Plug in directly? | Notes |
|---|---|---|
| Player identity | N/A — a join-key resolution step *before* evidence assembly, never an evidence value itself | Resolves which `player_stats` rows to pull; see Section 4. |
| Game identity | N/A — same, a resolution step | |
| Player game-level performance | **Needs a new adapter.** No existing engine output covers this. | New `compute_player_performance_context` (mirrors `weather.py`'s shape: target fact = this game's real stat line if it exists; comparable pool = the *same player's own* prior real games, recency-weighted, not other players). |
| Lineup/depth/role | **Needs a new adapter.** | New `compute_roster_role_context`, reading `depth_chart_snapshots` (team-scoped) via the point-in-time pattern in Section 3 — the *current-read* code exists, the *historical* query does not. |
| Injuries | **Needs a new adapter.** | Real, historical-capable `injury_reports` table exists; no "as of a past timestamp" reader exists yet — same point-in-time gap as lineup. |
| Teammate dependency | **Needs a new adapter**, minimal (Section 5) | Not a standalone dimension — a small addition to `roster_role`'s own facts. |
| Weather | **Plugs in directly.** Already real (`compute_weather_context`). | Zero adapter work; wiring itself is the only remaining step, explicitly not authorized this pass. |
| Venue | **Plugs in directly.** Already real (`compute_venue_context`). | Same as weather. |
| Rest | **Needs a new adapter.** | No real dimension exists in either system; the raw fields (`games.scheduled_start` per team) already exist and are already fetched by the adjacent travel path (per the prior audit) — a code-only gap. |
| Travel | **Already flowing, via a different path.** | `travel_fatigue_agent` is one of the 6 real `BUILT_AGENTS` (`app/agents/committee_context.py`) and already reaches `build_evidence()` today via `upstream_findings` — it doesn't need Context-Intelligence-engine wiring at all, it needs nothing further for this design. |
| Opponent/matchup ratings | **Must remain unavailable.** | Schema-only (`matchup_scores`/`offensive_matchup_scores`/`defensive_matchup_scores`), zero real data or code either side. Real dependency ordering: this dimension's own inputs (team/player performance) must be real first — it cannot be built before Dimension C. 8 of the 11 not-yet-built fan-out agents (`offensive_matchup_agent`, `defensive_matchup_agent`, `historical_trends_agent`, `team_form_agent`, `coaching_tendencies_agent`, `motivation_agent`, `playoff_importance_agent`, `referee_tendencies_agent`) are exactly this family. |
| Game state/script | **Must remain unavailable.** | Gated on real completed-game validation and a worker that doesn't exist yet (per prior audit) — a future, separate pass. |
| Odds/market | **Already flowing AND already real+richer, via two separate paths.** | `vegas_line_agent`/`closing_line_movement_agent` (BUILT_AGENTS) already reach the model; `context_intelligence/market.py` is real, richer (cross-game comparative), and unwired. Consolidating the two is a future decision, not this pass's. |
| News | **Already real, not wired anywhere.** | `compute_news_context` exists; would need a new fan-out agent (or ride the same `contextual_performance` key) to reach the model. Team-scoped only — no player identity column exists on `news_article_history` at all, so a *player-specific* news claim is not achievable even with wiring; state this honestly if ever asked for. |

**Which must remain unavailable for now, explicitly**: opponent/matchup
ratings, game state/script, and (as a standalone claim) player-specific
news. Everything else is either already flowing, already real and only
needing wiring (not this pass), or needs a scoped adapter this document
specifies but does not build.

---

## 3. Historical correctness

**Current-only tables/paths that must never be read as historical
truth** (re-confirmed against current source this pass, not assumed):

- **`daily_game_intelligence`** — its own migration comment says it
  outright: "continuously overwritten by the Master Refresh worker, not a
  source of historical truth." Feeds weather/injuries/rest/stadium to the
  *old* fan-out `AgentContext` path today. Any future historical
  reconstruction must bypass this table for those fields entirely — it
  cannot answer "what was true as of game X," only "what is true right
  now."
- **`players.team_id`** — a current fast-pointer, not a historical
  record. Must never be read as "the team this player was on during a
  past game"; `roster_memberships` (append-only) is the correct source —
  with the caveat, disclosed not solved, that it has no explicit
  end-date (insert-on-change only), so "still on this team" and "we
  simply haven't captured a newer row" are not distinguishable today.
- **Any "most recent" injury/lineup reader** — a reader built to answer
  "what is true now" must never be reused unmodified to answer "what was
  true then." These are different queries even when they share a table.

**The proper point-in-time retrieval requirement, defined once,
generically, for any snapshot table shaped `(entity_id, captured_at,
payload)`:**

```
SELECT * FROM <snapshot_table>
WHERE entity_id = :target_entity_id
  AND captured_at <= :target_event_timestamp
ORDER BY captured_at DESC
LIMIT 1
```

"The most recent real observation that existed at or before the moment
being reconstructed" — never the globally-latest row for that entity.
Applied per dimension:

- **Weather** (`weather_snapshots`, `game_id` + `captured_at`): target
  timestamp = kickoff (weather is conventionally observed pregame, not
  mid-game) — already the shape `compute_weather_context` uses for the
  *current* case; needs no change to become historically correct, since
  it already filters by `game_id` and there is normally at most one real
  row per game today. The discipline matters once multiple observations
  per game exist.
- **Injuries** (`injury_reports`, `game_id` + `captured_at`): target
  timestamp = kickoff, ideally with a disclosed lead time (final
  injury reports are conventionally locked ~90 minutes before kickoff
  industry-wide) — a policy constant for whoever builds this, not
  decided here.
- **Lineup/role** (`depth_chart_snapshots`, `team_id` + `captured_at`):
  target timestamp = kickoff. Coarser than the others (insert-on-change,
  not a dense timeline) — the "nearest at-or-before" pattern still
  applies, but see the `roster_memberships` caveat above.
- **Market/odds** (`odds_snapshots`, `game_id` + `captured_at`): already
  historically correct today — both the target game's own history and
  cross-game comparisons already key off `captured_at`. The one remaining
  named gap (self-disclosed in `closing_line_movement.py`) is a genuine
  "closing line" marker, which does not exist anywhere in this
  architecture — not a point-in-time bug, a real missing concept.
- **Venue**: no point-in-time need — venue identity/coordinates are
  static facts, always JOINED once resolved. One disclosed limitation
  worth naming, not solving: a venue could theoretically be renovated or
  a team could relocate across a long enough history; this design treats
  venue facts as time-invariant, which is correct for the timescales
  MANSA operates at today.

---

## 4. Player identity joins

**Canonical**: `players.id` (a stable MANSA-internal UUID, assumed
career-stable — a player's identity doesn't change when traded, only
their team membership does). **Provider mapping**: `player_provider_ids`
(`player_id`, `provider_name`, `provider_player_id`), unique per
`(provider_name, provider_player_id)` and per `(player_id,
provider_name)`.

**Current real coverage**: MySportsFeeds only — 34 real rows (2 teams,
Phase 8.2 activation). **BALLDONTLIE is explicitly excluded from this
table's own CHECK constraint** (re-confirmed live against the dev
database this pass: `player_provider_ids_provider_name_check` permits
`'the_odds_api'`/`'sportsdataio'`/`'mysportsfeeds'` only — no
`'balldontlie'`) — the exact same class of gap the recent MSF
game-provider-ID work already fixed for `game_provider_ids`, **not yet
fixed here**. If Gate A (BALLDONTLIE `/nfl/v1/stats`) is ever authorized
and succeeds, there is currently no schema-legal way to persist a BDL
player-identity mapping at all. Flagged, not fixed — schema changes are
out of scope for this pass.

**Unresolved join risks before historical player-game data arrives:**

1. **BALLDONTLIE player identity unpersistable** (above) — a concrete,
   narrow, known fix (one CHECK-constraint value, same shape as the
   game-ID fix already done) whenever it's authorized.
2. **Name-based matching risk.** If any future ingestion path ever
   resorts to matching players by name+team instead of a verified
   provider ID, two real players sharing a common name could collide
   under one canonical identity. Every identity-resolution path built
   from here forward must resolve by verified provider ID only, never a
   name/team heuristic — already the discipline `player_identity.py`'s
   real functions follow; must not regress when a new provider's
   ingestion path is added.
3. **Team-change/trade timing.** `players.team_id` is current-only; a
   historical game where a player was on a *different* team must resolve
   team identity from `roster_memberships` as-of that game's date. Any
   future per-game ingestion code that naively joins `players.team_id`
   instead of doing the point-in-time roster lookup would misattribute
   team context for any player ever traded.
4. **Coverage gap.** Only 34 players (2 teams) have any real identity
   mapping today. Historical reconstruction for a player outside that
   set requires identity resolution to run for them for the first time —
   untested at any real scale as of this audit.
5. **Provider ID stability — an open question, not an assumption.** No
   evidence has been gathered (in this session or the prior audit) that
   MySportsFeeds' own player IDs are guaranteed stable across seasons.
   Provider-side ID churn is a known industry risk generally; flagged as
   unresolved rather than assumed safe.

---

## 5. Teammate dependency / matchup — minimum useful V1

Explicitly **not** a correlation/joint-probability model, not a
dependency graph, not a new agent. The smallest useful representation:

- Extend the (future, real) `roster_role`/lineup dimension's own `facts`
  with a flat **teammates list**: for the target player's team, *as of
  the same point-in-time roster snapshot already resolved for the
  player's own role*, list the other players present in that snapshot —
  `{player_id, position, depth_chart_rank (if the slot label carries
  one), "listed"}`. Never "confirmed active" or "confirmed inactive" —
  the current data model cannot represent true active/inactive status at
  all (per the prior audit), so this is deliberately just "who appears
  in this same real snapshot," honestly labeled.
- **The one derived fact worth computing, still zero modeling**: is a
  configurably "key" position (e.g. the team's top-depth QB) present in
  this same snapshot. A single presence boolean, not a dependency score,
  not an impact estimate — this answers exactly the "is the starting QB
  playing" question named in the original audit, using data that already
  exists once `roster_role` itself is real.
- **Explicitly deferred**: any predictive claim about one teammate's
  absence changing another's expected performance (e.g. "WR2 typically
  gains target share when WR1 is out"). That is a real modeling
  question — precisely the "large new modeling system" this section is
  told not to build.
- **Standing confounder, always attached**: "Reflects real, timestamped
  co-presence on the same roster snapshot only — never a causal or
  predictive claim about how one player's presence or absence affects
  another's performance."

---

## 6. Phase 8 completion criteria (Beta-quality Contextual Performance
   Intelligence)

Building on the prior audit's NOT READY verdict and its ranked blockers,
the minimum conditions to declare this ready for Beta-quality use:

1. **Real per-game player performance data exists for a meaningful
   sample** — via a successful Gate A or Gate B outcome, persisted
   through the existing `player_stats` schema (no schema change needed,
   confirmed by the prior audit). This remains the single central
   blocker every other criterion depends on.
2. **Point-in-time retrieval code exists and is tested** for weather,
   injuries, and lineup/role — the "nearest observation at or before
   kickoff" pattern (Section 3), currently implemented for none of these
   as historical-safe code, only as current-only reads.
3. **Player identity coverage extends meaningfully beyond the current
   34-player/2-team activation batch** — not a fixed target number, but
   "more than one pre-selected activation batch," so a historical proof
   isn't limited to the same handful of players every time.
4. **The BALLDONTLIE player-identity schema gap is resolved** *if* Gate A
   is the path actually taken (not a blocker if Gate B alone suffices).
5. **At least the `player_performance` dimension, plus one of
   {`roster_role`, `injuries`}, is real** — carrying the same provenance/
   sample-size/confidence/confounder/insufficient-evidence discipline the
   four existing real dimensions already follow. Beta-quality does not
   require every dimension simultaneously; it requires enough of them,
   real and honest, to produce a genuinely useful "why this
   recommendation" story for at least one player-scoped claim.
6. **A real Context Assembly Proof is actually run** — 2-3 real
   historical games (the original Hunter Henry proof target or
   equivalent) — and its output is manually reviewed for honesty (no
   fabricated evidence, every insufficient-evidence case correctly
   flagged, no current-data-as-historical leakage) before Beta-quality is
   declared. This is a process gate, not only a code gate.
7. **`build_evidence()` wiring is named as the explicit next milestone,
   not a Beta-quality prerequisite.** Context *assembly* can be proven
   real and honest without yet reaching the model — wiring it in is a
   separate, later, Phase-4-reopening decision, per this project's own
   phase-gating discipline. Beta-quality Contextual Performance
   Intelligence means the context can be honestly assembled and shown;
   it does not yet mean it has changed a single recommendation.

---

## What was and wasn't done

Design only. No file outside `docs/`/`PROGRESS.md` was touched, no
provider was called, no schema was created, no `build_evidence()` call
site was modified, no recommendation logic was changed, and Gate B was
not touched. Every concrete recommendation above (the point-in-time
query shape, the `data_completeness` field, the teammate-presence
minimum, the BALLDONTLIE identity gap) is a specification for a future,
separately-authorized pass — none of it was implemented here.
