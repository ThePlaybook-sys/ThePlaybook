# MANSA User Question → Recommendation Flow: Audit + Implementation Plan (2026-09-09)

**Status: audit and implementation-readiness pass only. No code, schema, migration, worker activation, cron schedule, credential, or provider-call change was made. No implementation was begun.** Builds directly on `docs/ops/mansa-end-to-end-decision-flow-audit-2026-09-08.md` (accepted) to determine the minimum safe architecture and sequence for closing the confirmed first product disconnect: USER QUESTION → MANSA INTENT → APPROPRIATE RECOMMENDATION.

---

## 1. Question-Intake Entry Point

**No endpoint anywhere accepts a free-text question, or a sport/league/game/team/player/market/recommendation-preference parameter.** Confirmed by direct inspection of every route in `apps/api-gateway/app/recommendations.py`:

- `GET /v1/recommendations/today`, `GET /v1/recommendations` — accept only `since`/`until` (ISO dates) and `limit` (`recommendations.py:354-357`). No sport/team/player/market/risk param exists.
- `GET /v1/recommendations/{display_id}`, `.../reconstruction` — accept only an opaque, system-assigned `display_id` string.
- No other router in `apps/api-gateway` (`user`, `track_record`, `subscription`, `freshness`, demo) accepts anything question-shaped either.

**Auth/user-context, reusable as-is**: `apps/api-gateway/app/auth.py`'s `get_current_user` → `CurrentUser(id, email)` is the existing, working pattern (Supabase JWT → Supabase Auth verification → `user_profiles` existence check). A question-intake endpoint would reuse this identically — no new auth mechanism is needed.

**Existing request/response models that could be reused**: none of the current response builders (`_serialize_card`-style functions in `recommendations.py`) accept a filter/preference input today; they're pure read-and-join. The response *shape* (card structure: `displayId`, `marketType`, `selection`, odds, `finalAggregateConfidence`, explanation fields) is directly reusable as the answer format for a question-intake endpoint — no new response vocabulary is needed, only a new way of selecting *which* existing rows to return.

**Where question-intake should logically live**: a new route in `apps/api-gateway` (e.g. `POST /v1/recommendations/ask` or similar), sitting alongside the existing `recommendations` router, reusing `get_current_user`/`tier_permits` verbatim, and — per Stage 2 below — calling a new, small, deterministic intent-resolution function before querying the exact same Supabase tables `recommendations.py` already reads. **No new service, no new database, no new auth mechanism.**

**Is a new endpoint required? Yes.** Nothing today can be extended in place — every existing route's contract is a specific, narrow read (a date-windowed list, or one product by ID); none is shaped to accept a preference and choose among many possible already-computed answers.

**Smallest safe request contract** (design only, not built):

```jsonc
POST /v1/recommendations/ask
{
  "question": "what's the safest NFL pick today?",   // required, raw text, stored for audit/telemetry only
  "sport": "nfl" | null,                               // optional explicit override, bypasses inference
  "date": "2026-09-09" | null                          // optional, defaults to today
}
```

Response reuses the existing card shape (`recommendations.py`'s `_serialize_card`-equivalent), plus a small new envelope: `{ "intent": <StructuredIntent>, "result": <card|null>, "insufficientEvidence": bool, "reason": string|null }` — the `reason`/`insufficientEvidence` fields are new, and are exactly where FACT/INFERENCE/INSUFFICIENT-EVIDENCE disclosure (§6) belongs at the presentation boundary.

---

## 2. Recommendation Retrieval Capabilities

**Real schema fields, confirmed directly from `supabase/migrations/20260825120000_recommendation_products_schema.sql`:**

- `recommendation_products`: `recommendation_type` (`single|player_prop|no_bet|same_game_parlay|multiple_singles|bankroll_preservation|multi_game_parlay` — schema allows parlay values, **nothing ever writes them**, confirmed both in this migration's own comment at line 29 and by the prior audit's grep of `app/features/candidate.py`/`explainability.py`), `scope` (`game|slate`), `game_id`, `status` (`active|withdrawn`). **No sport, league, team, player, or risk/confidence/EV field on the product itself.**
- `recommendation_legs`: `game_id`, `market_type`, `selection`, `sportsbook`, `american_odds`, `point`, `decimal_odds`, `ev_per_dollar`, `final_aggregate_confidence`. **Confidence and EV exist, but only on the leg, one level below the product.**
- `games` (joined in, `recommendations.py:75,90`): `home_team`, `away_team` (plain text, not FK'd to a canonical `teams` row for this read path), `scheduled_start`, `status`.

**What the system can currently filter/query by** (via direct Supabase queries, not exposed as an API parameter today):

| Requested filter | Currently queryable? | How |
|---|---|---|
| Sport | **No** | No column exists anywhere in the product/leg/candidate chain (confirmed by the prior audit's schema grep) |
| League | **No** | Same — doesn't exist as a concept below the unused `sports`/`leagues` tables |
| Game/event | **Yes** | `recommendation_products.game_id`, `recommendation_legs.game_id` — both real, indexed |
| Team | **Partially** | Only by joining `games.home_team`/`away_team` (plain text string match) — no canonical team ID linkage in this read path |
| Player | **No** | No player field anywhere in `recommendation_products`/`recommendation_legs`; player props are schema-allowed (`recommendation_type='player_prop'`) but nothing generates them (candidate generation explicitly defers props, per the prior audit) |
| Market | **Yes** | `recommendation_legs.market_type` — real, direct |
| Date | **Yes** | Via `games.scheduled_start` (game-scoped) or `recommendation_activation_snapshots.activated_at` (slate-scoped) — already the exact ordering logic `recommendations.py:34-41` documents |
| Risk | **Indirectly** | No explicit risk label; would need to be derived from `final_aggregate_confidence`/`ev_per_dollar` (see below) |
| Confidence | **Yes** | `recommendation_legs.final_aggregate_confidence` — real, direct |
| Expected value | **Yes** | `recommendation_legs.ev_per_dollar` — real, direct |
| Recommendation type | **Yes** | `recommendation_products.recommendation_type` — real, direct |

**Mapped against the 12 example questions HQ listed:**

| Question | Answerable today by query alone? |
|---|---|
| "What's the safest pick?" | **Yes** — order active legs by `final_aggregate_confidence` desc |
| "What's the best pick?" | **Ambiguous today** — "best" has no single defined column; needs a product decision (highest confidence? highest EV? a blended score?) before it can be a deterministic query — **not a data gap, a definition gap** |
| "What's the highest-value pick?" | **Yes** — order by `ev_per_dollar` desc |
| "Give me the top 3 picks." | **Yes**, mechanically (`limit=3` on any of the above orderings) — but "top" inherits the same "best" ambiguity above |
| "What's the best pick for this game?" | **Yes** — filter by `game_id`, then apply whichever "best" definition is chosen |
| "What's the best pick involving this team?" | **Partially** — needs a team-name string match against `games.home_team`/`away_team`, fragile without canonical team IDs in this read path |
| "Show me a specific market." | **Yes** — filter by `market_type` |
| "Give me conservative options." | **No defined threshold exists** — would need a product decision on what confidence/EV band counts as "conservative" (a UI/product definition, not a data gap) |
| "Give me aggressive options." | Same as above, inverse band |
| "Build me a parlay." | **No** — see §5, schema allows the type value, nothing computes or validates one |
| "Show me NFL picks." | **Trivially yes today** (everything is NFL) but **not as a real filter** — there's no sport column to filter by, it's just vacuously true |
| "Show me the best opportunities across sports." | **No** — no second sport exists in real data yet; the query pattern itself would work once sport data exists, but nothing to filter today |

**What actually exists vs. what would need to be added, summarized**: game/market/date/confidence/EV filtering **already works via direct query** — no new capability needed there, only a new endpoint exposing it. Sport/league/player filtering and any notion of "safest/best/conservative/aggressive" as a *named, stable band* **need new definitions and, for sport/league/player, new schema columns** — not invented here, flagged as decisions.

---

## 3. Deterministic Intent Resolution

**Proposed structured intent object** (design only):

```jsonc
{
  "requestType": "safest" | "best_overall" | "highest_value" | "top_n" |
                 "game_specific" | "team_specific" | "player_specific" |
                 "market_specific" | "conservative" | "aggressive" |
                 "parlay" | "informational" | "unresolved",
  "scope": {
    "sport": "nfl" | null,          // explicit only, never guessed beyond today's single-sport reality
    "league": null,                  // reserved, unused until multi-sport
    "gameId": "<uuid>" | null,
    "teamName": "<string>" | null,   // matched against games.home_team/away_team
    "playerName": null,              // reserved — no player data to match against yet
    "marketType": "moneyline"|"spread"|"total"|null,
    "date": "<ISO date>" | null,     // defaults to today if omitted
    "n": 3 | null                    // for top_n requests
  },
  "confidence": "high" | "low",      // the resolver's OWN confidence in this classification, not a betting confidence
  "unresolvedReason": "<string>" | null
}
```

**Resolution should be rule-based, not an LLM, for the first beta** — matching this project's own established discipline (deterministic `app.features.market`/`app.features.grading`/`app.features.consensus`, LLM reserved for genuinely qualitative judgment). A simple keyword/pattern layer is sufficient for the first beta's request-type vocabulary:

- `requestType`: keyword matching (`"safest"|"safe"` → `safest`; `"best"` alone → `best_overall`; `"value"|"highest value"` → `highest_value`; `"top \d+"|"three picks"` → `top_n`; a recognized team/game name present → `team_specific`/`game_specific`; `"parlay"` → `parlay`; `"conservative"` → `conservative`; `"aggressive"` → `aggressive`; no match → `informational` or `unresolved`).
- `scope.sport`: only set when a sport name is explicitly present in the text (see §4's explicit/ambiguous rule) — never inferred.
- `scope.gameId`/`teamName`: matched against the already-loaded slate of today's real `games` rows (string containment against `home_team`/`away_team`), never fuzzy-guessed past that.

**Why this doesn't need an LLM**: every request type above maps to a deterministic SQL ordering/filter already described in §2 — the "intelligence" this layer needs is pattern recognition over a small, known vocabulary, not judgment. This mirrors the project's own explicit "never delegate to an LLM what application code can compute" principle (Volume 2 §1.1, cited throughout Volume 4).

**Not built this pass**, per HQ's explicit instruction.

---

## 4. Multi-Sport Readiness

**Existing NFL-specific assumptions that would create problems when NBA (or any second sport) is added**, confirmed by direct citation:

1. **No sport column anywhere in the candidate/recommendation chain** (`MarketCandidate`, `recommendation_products`, `recommendation_legs`) — a cross-sport query has nothing to filter or group by today.
2. **`games.sport` is a hardcoded literal string `"nfl"`**, written at persistence time (`apps/sports-intel-layer/app/persistence/schedule.py:111`), not derived from any real sport-detection logic.
3. **Every provider adapter is instantiated with a single hardcoded sport constant** (`_SPORT_KEY = "americanfootball_nfl"`, `_SPORT_PATH = "nfl"`) — adding NBA means adding a second adapter instance per provider, not parameterizing the existing one; no code path currently accepts a runtime sport argument.
4. **Team matching in the read path is a plain-text string comparison** (`games.home_team`/`away_team`), not a canonical team-ID join — two sports with overlapping city names (e.g. "New York") would collide without a real `team_id`/`sport_id` join, which doesn't exist in this read path today.
5. **The real, unused `sports`/`leagues`/`seasons` tables already solve the identity problem structurally** — this is good news, not a new build: the schema exists, only the application layer never populates or queries it.

**Behavior rules, as specified by HQ, applied to the proposed intent object**:

- **Explicit single-sport request** ("Give me the best NFL picks") → `scope.sport = "nfl"` is set directly from the matched keyword; **no follow-up question is generated**, matching HQ's rule exactly. Today this is moot (everything already is NFL), but the rule is written into the intent-resolution design now so it doesn't need revisiting when a second sport exists.
- **Explicit cross-sport request** ("best picks across all sports") → `scope.sport = null` with an explicit `crossSportIntentional: true` flag (not shown above, a small addition once a second sport exists) — the system should not narrow to one sport on its own once cross-sport data exists.
- **Ambiguous request** ("what are the best picks tonight?") → **today, resolves trivially to NFL since nothing else exists.** Once a second sport is live, this case needs a real product decision this audit does not make: ask the user, default to a stored preference, or return across all eligible sports with each result clearly labeled. **Recorded as an open decision for HQ, not resolved here** — resolving it before real multi-sport data exists would be inventing behavior for a rule that has no way to be validated yet.

---

## 5. Parlay Capability Boundary

**Exact difference, confirmed against real code**:
- **A. Selecting multiple individually strong recommendations** — this MANSA already does today, honestly: `recommendation_type = 'multiple_singles'` is a real, written value (`Strategy Engine`, confirmed by the prior audit), and `explainability.py`'s own `build_why_not_other_shapes` states directly that legs are "presented as its own separate wager rather than combined, since parlay combination is not currently active."
- **B. Calculating the actual combined probability of a parlay** — **confirmed absent.** No `same_game_parlay`/`multi_game_parlay` code exists; `explainability.py:258` states directly: *"no correlation or combined-probability calculation exists in this system."* The schema *allows* the `same_game_parlay`/`multi_game_parlay` type values (they're in the `recommendation_type` CHECK constraint) — but they are never written, and writing them without the math behind them would silently misrepresent MANSA's own confidence.

**What MANSA can honestly support today**: presenting several independently-evaluated `multiple_singles` legs to a user who asks to "build a parlay" — clearly labeled as independent recommendations the user could choose to combine themselves, never as a MANSA-computed joint probability. This is not a new capability — it's the existing `multiple_singles` product, retrieved via the intent-resolution layer's `parlay` request type and presented honestly.

**Exact future capability required before MANSA can claim or estimate joint probability for correlated outcomes**: a real correlation model between legs (same-game legs are typically negatively or positively correlated depending on market type; cross-game legs are typically closer to independent, but not provably so without evidence) — **explicitly not designed, approximated, or multiplied together by this pass**, per HQ's direct instruction. This is named as a distinct, unresolved future requirement, on the same "reserve, don't invent" footing as Bet Timing & Execution Intelligence (Volume 4 §9.5).

---

## 6. Explanation Taxonomy (FACT / INFERENCE / MODEL OUTPUT / INSUFFICIENT EVIDENCE)

**Existing structures, confirmed**: `EvidenceClassification` (`apps/ai-orchestrator/app/agents/contract.py:84-89`) is a real, three-way, code-enforced enum — `data_backed | inference | assumption` — applied **per agent output**, feeding `apps/ai-orchestrator/app/features/consensus.py`'s own weighting (an `assumption`-classified output has its `effective_weight` halved). Context Intelligence's `ContextualDimensionResult` (`apps/ai-orchestrator/app/context_intelligence/models.py`) separately, already implements a real, working **insufficient-evidence** signal (`insufficient_evidence: bool` + `insufficient_evidence_reason: str`), never fabricating a confidence number when there's nothing to compute one from.

**Do existing structures already support the requested four-way taxonomy? Partially, but not as that exact vocabulary.** `data_backed`/`inference`/`assumption` (agent-output layer) and `insufficient_evidence` (Context Intelligence layer) together cover three of the four requested categories in spirit — `data_backed`≈FACT, `inference`≈INFERENCE, `insufficient_evidence`≈INSUFFICIENT EVIDENCE — but **MODEL OUTPUT (the LLM's own probability/confidence judgment, distinct from a fact or a disclosed inference) has no dedicated category today.** `modeled_probability`/`confidence_in_probability` (Probability Modeling's own output) is currently presented in explanations without being explicitly labeled as "this number came from a model, not a fact or a documented inference chain."

**Where classification should live — three real options, assessed, not decided here**:
1. **At the evidence layer** (extend `EvidenceClassification` or reuse it) — cheapest, reuses an already-real, already-tested mechanism; risk: conflates "how an agent classified its own input" with "how the final answer should be presented," which are related but not identical questions.
2. **At the recommendation layer** (a new field on `recommendation_product_explanations`) — matches where `why_selected`/`biggest_risks`/`data_limitations` already live (the real, existing explanation table) — the most natural home structurally, since this is precisely a presentation-facing explanation table already.
3. **Only at presentation time** (computed on the fly from existing fields, never persisted) — cheapest to build, but loses provenance/audit value and can't be reconstructed identically later the way this project's Time Machine principle requires for everything else.

**Recommendation for a future authorized pass (not decided or built here)**: option 2 (recommendation layer, alongside existing explanation fields) best matches this project's own precedent — Milestone 5.6's lifecycle events and the existing explanation table both already treat "how MANSA communicates itself" as a first-class, persisted concern, not a derived-at-read-time convenience. **The one non-negotiable design constraint, regardless of which option is chosen**: MANSA must never present an inference or a model output as a fact, and must never suppress or dress up an `insufficient_evidence` case as a lower-confidence answer — both principles are already locked, precisely worded, and enforced elsewhere in this codebase (Context Intelligence's `unsupported.py`, the Explainability Engine's own `data_limitations` discipline) and would simply need to be extended to this new taxonomy, not invented from scratch.

---

## 7. Existing Ingestion Workers — Actual Status

| Worker | Code exists? | Invocation endpoint? | `main.py` route? | API route available? | Currently invokable? | Currently scheduled? | Exact missing wiring |
|---|---|---|---|---|---|---|---|
| **Player Props Ingestion Worker** | **Yes** — `apps/sports-intel-layer/app/workers/player_props_worker.py`, real cadence logic, real `persist_player_props` | **No** | **No** | **No** | **No** | **No** | An internal route in `apps/sports-intel-layer/app/main.py` (mirroring the real `odds-worker`/`weather-worker`/`news-worker` routes already there) + a `cron_dispatch.py` target entry (`_TARGET_PATHS`) — that dict's own trailing comment names this exact gap: *"Remaining unwired specialized workers: Player Props/Pregame/Postgame Ingestion — see the Phase 3E specialized worker runtime invocation debt item recorded in PROGRESS.md."* |
| **Pregame Ingestion Worker** | **Yes** — coordinates Odds/Player Props/Injury/Weather at T-minus-5 | **No** | **No** | **No** | **No** | **No** | Same as above — no route, no cron target |
| **Postgame Ingestion Worker** | **Yes** — `apps/sports-intel-layer/app/workers/postgame_worker.py`, persists `team_stats`/`player_stats` from finalized games | **No** | **No** | **No** | **No** | **No** | Same as above — no route, no cron target |

**No dependencies or provider-side blockers exist for any of these three** — this is a pure, self-contained code-wiring gap (add a route + a dispatch-target mapping, both entirely within this repo's own control), independent of BALLDONTLIE/MySportsFeeds/any external gate. This is the same finding as the 2026-09-08 audit, re-confirmed here directly against the current `cron_dispatch.py` source rather than cited secondhand. **Not activated or scheduled by this pass**, per guardrails.

---

## 8. News and Venue Committee Readiness

**Real, confirmed state**: `news_article_history` (real, ~97+ rows, 4h cadence) and `venues` (real, 5 rows) both exist and are actively populated. Neither is read by any of the 6 real, built fan-out agents (`injury_intelligence_agent`, `weather_agent`, `travel_fatigue_agent`, `rest_days_agent`, `vegas_line_agent`, `closing_line_movement_agent` — the complete `BUILT_AGENTS` set, `apps/ai-orchestrator/app/agents/committee_context.py:55-64`). Both are already read, however, by the separate, unwired `context_intelligence` engine (news.py/venue.py dimensions).

**Which existing agents could consume News/Venue data immediately? None, as currently written.** No built fan-out agent's evidence-gathering function reads `news_article_history` or the `venues` table — each of the 6 real agents is scoped narrowly to its own single evidence source (weather → `weather_snapshots` via DGI, injuries → `injury_reports` via DGI, etc.). Extending one of them to also carry News or Venue evidence would blur that established one-agent-one-source pattern.

**Does the existing evidence interface support this data?** Yes, structurally — `ContextDataAgent.build_evidence(context: AgentContext) -> dict` (`apps/ai-orchestrator/app/agents/base_agent.py`) is a generic dict-returning contract; nothing about it is weather/injury-specific. A new agent implementing this same interface, reading `news_article_history`/`venues` instead, would fit the existing pattern exactly.

**Are new agents genuinely necessary, or could existing evidence be extended?** **New agents are the safer path**, matching this codebase's own established one-source-per-agent convention (confirmed across all 6 real fan-out agents) rather than overloading an existing agent's evidence dict with an unrelated second source, which the consensus-weighting logic (`EvidenceClassification` per output) isn't designed to disambiguate within a single agent's output.

**Smallest safe future integration path (not built)**: two new fan-out agent files — a `news_agent.py` and a `venue_agent.py` — each implementing `ContextDataAgent.build_evidence` against the already-real `news_article_history`/`venues` reads that `context_intelligence`'s own `news.py`/`venue.py` modules already demonstrate work correctly (this is genuinely the cheapest path in the whole system: **the queries are already written, tested, and running against real data — only the fan-out wrapper is missing**). Each would be added to `BUILT_AGENTS`, raising `committee_completeness` from 6/17 toward 8/17, with zero change to Consensus, Probability Modeling, or any Phase 4 file. **Phase 4 implementation remains completely untouched by this recommendation** — this is additive, new agent files only, matching how every prior agent (e.g. `closing_line_movement_agent`) was added without modifying the ones before it.

---

## 9. Minimum Honest Beta Vertical Slice

Determined from the real codebase, not assumed to match HQ's example:

**"What's the safest NFL pick today?" is, in fact, the single cheapest real question to answer honestly today** — because "safest" maps directly and unambiguously to an already-real, already-computed column (`final_aggregate_confidence`), unlike "best" (ambiguous, §2) or anything parlay-shaped (§5) or anything requiring real player/team-level substrate (blocked on Phase 8, per the Context Assembly Proof).

**Real trace of what such a slice would actually do, using only what exists today:**

1. `POST /v1/recommendations/ask` (new, §1) receives the question, authenticates via the existing `get_current_user`.
2. Deterministic intent resolution (§3, new, small) classifies `requestType="safest"`, `scope.sport="nfl"` (explicit or trivially true), `scope.date=today`.
3. Query already-computed `recommendation_products`/`recommendation_legs` for today, `status='active'`, ordered by `final_aggregate_confidence` desc, `limit=1` — **this exact query pattern already exists** in `recommendations.py`'s `/today` route, just without the ordering; no new data access code needed, only a new ordering clause and a narrower filter.
4. If a row exists, reuse the existing card-serialization logic (already real, already tested) to build the response.
5. If no active product qualifies today (a real, expected outcome — "No Bet Today"/bankroll preservation is already a first-class product type), return the existing honest "nothing qualified" signal rather than fabricating a pick — this behavior already exists in the current dashboard and needs no new design.
6. Attach the existing explanation fields (`why_selected`, `strongest_evidence`, `biggest_risks`, `data_limitations`) — already real, already persisted, already reachable via the same join `/{display_id}` already performs.
7. **Explicitly does NOT need**: Context Intelligence wiring, any new fan-out agent, any schema change, any new provider data, or the Context Assembly Proof to have cleared — this slice is entirely a *retrieval and presentation* problem over data and computation that already exists end-to-end.

**This is a real, buildable-today vertical slice** — smaller and cheaper than HQ's own example implies, precisely because "safest" (unlike "best," "value," or anything player/parlay-shaped) already has one unambiguous existing column behind it.

---

## 10. Implementation Sequence

Numbered, each item classified into exactly one category — no blurring, per HQ's instruction.

1. **Wire Player Props/Pregame/Postgame Ingestion Worker internal endpoints + cron targets** (§7) — **READY TO BUILD NOW.** Pure code wiring, zero data dependency, zero schema change.
2. **Build `news_agent.py`/`venue_agent.py` fan-out agents** reusing `context_intelligence`'s already-real queries (§8) — **READY TO BUILD NOW.** Additive new files, existing interface, existing real data, zero Phase 4 file modification.
3. **Build `POST /v1/recommendations/ask` endpoint + deterministic intent resolver** for the "safest" request type only (§1, §3, §9) — **READY TO BUILD NOW.** Reuses existing auth, existing query patterns, existing card serialization; the "safest" slice needs no new schema.
4. **Extend the `ask` endpoint to "highest_value" and "market_specific" request types** (§2) — **READY TO BUILD NOW**, same reasoning as #3 (both map to already-real columns: `ev_per_dollar`, `market_type`).
5. **Define "best_overall"/"conservative"/"aggressive" as concrete, named confidence/EV bands** — **NEEDS SCHEMA/DATA-MODEL CHANGE** (or at minimum a documented product decision, possibly no schema change if implemented as application-layer constants — but the *definition itself* doesn't exist yet and must be decided, not inferred, before #4's pattern can extend to these three request types).
6. **Add `team_specific`/`game_specific` request types to the intent resolver**, using string-match against `games.home_team`/`away_team` — **READY TO BUILD NOW** for the NFL-only case; fragile without canonical team IDs, so flagged as technical debt to close under #7 below rather than blocking this item.
7. **Add canonical `team_id`/`sport_id` linkage to the recommendation-retrieval read path** (joining through the already-real but unused `sports`/`leagues`/`teams` tables) — **NEEDS SCHEMA/DATA-MODEL CHANGE.** The tables already exist; this is wiring the read path to them, not creating new tables — smaller than a full migration, but still a real schema-usage change requiring its own authorization.
8. **Add a sport/league field to `MarketCandidate`/`recommendation_products`/`recommendation_legs`** — **NEEDS SCHEMA/DATA-MODEL CHANGE.** Required before real multi-sport filtering, cross-sport requests (§4), or any parlay work (§5) can be meaningfully built.
9. **Design and persist the FACT/INFERENCE/MODEL-OUTPUT/INSUFFICIENT-EVIDENCE taxonomy** at the recommendation-explanation layer (§6, option 2) — **NEEDS SCHEMA/DATA-MODEL CHANGE** (a new field/table extension), with the underlying classification logic itself largely READY TO BUILD NOW once the schema decision is made, since the three-way `EvidenceClassification`/`insufficient_evidence` mechanisms it would build on are already real.
10. **`player_specific` request type and player-prop candidate generation** — **BLOCKED ON PHASE 8 DATA.** No real player identity/stats substrate exists yet (per the Context Assembly Proof's own Context Readiness Matrix); nothing to query even if the intent resolver could recognize a player name.
11. **`best_overall`/general "best" resolution using a blended confidence+EV score, or any use of Context Intelligence's news/market/venue dimensions inside the intent-resolution or ranking logic** — **BLOCKED ON PHASE 4** in the sense that any change to how candidates are scored/ranked touches the frozen Phase 4/5 committee-and-strategy architecture and needs its own authorization, independent of data readiness.
12. **Context Intelligence → Probability Modeling wiring, and any Matchup & Form agent build-out** — **BLOCKED ON PHASE 8 DATA** (Context Assembly Proof, Gate A/Gate B, per the prior locked gate) **and BLOCKED ON PHASE 4** (any change to `ProbabilityModelingAgent.build_evidence` or the fan-out roster is explicitly out of this pass's and any near-term pass's authorized scope until that data exists).
13. **Real joint-probability/correlation modeling for parlays** (§5) — **BLOCKED ON PHASE 8 DATA** for the underlying evidence (same-game correlation needs real per-game player/team data this project doesn't have) **and is its own, larger, unscheduled future capability**, not sequenced further here.
14. **Ambiguous cross-sport request-resolution behavior** (§4's third case) — **BLOCKED ON HUMAN/PROVIDER ACTION** in the specific sense that it's a genuine, unresolved product decision for HQ (ask/default/return-all), not resolvable from code inspection, and moot until a second sport's real data exists anyway.
15. **A second sport's provider adapters/entitlement** — **BLOCKED ON HUMAN/PROVIDER ACTION** (a new subscription/credential decision entirely outside this audit's scope, same category as the already-tracked BALLDONTLIE/MySportsFeeds gates).

---

## Files Inspected

`apps/api-gateway/app/recommendations.py`, `app/auth.py`, `app/entitlement.py`; `apps/sports-intel-layer/app/main.py`, `app/persistence/schedule.py`, `app/workers/player_props_worker.py`, `app/workers/postgame_worker.py`; `apps/workers/app/cron_dispatch.py`; `apps/ai-orchestrator/app/agents/committee_context.py`, `app/agents/contract.py`, `app/agents/base_agent.py`, `app/agents/probability_modeling.py`, `app/context_intelligence/engine.py`, `app/context_intelligence/news.py`, `app/context_intelligence/venue.py`, `app/context_intelligence/unsupported.py`, `app/features/candidate.py`, `app/features/candidate_generation.py`, `app/features/consensus.py`, `app/features/explainability.py`; `apps/adapters/providers/the_odds_api.py`, `balldontlie.py`; `supabase/migrations/20260825120000_recommendation_products_schema.sql`, `20260807211306_sports_data_tables.sql`; plus this session's own prior audit (`docs/ops/mansa-end-to-end-decision-flow-audit-2026-09-08.md`) and Context Assembly Proof lock (Volume 4 §8.6 v5.15) as accepted, cited-not-re-derived background.

## Files Changed

One — this report (`docs/ops/mansa-user-question-to-recommendation-flow-audit-2026-09-09.md`). `PROGRESS.md` gains a dated Notes entry summarizing this pass (committed alongside this report). **No application code, schema, migration, worker configuration, cron target, or credential was touched.**

## Guardrail Confirmation

Zero provider calls. Zero purchases. Zero live-data diagnostics. Zero credential changes. Zero worker activation changes. Zero new cron schedules. Zero Phase 7 observation changes. Zero Phase 8 contextual-scoring changes. Zero Phase 8 → Probability Modeling wiring. Zero Phase 4 implementation changes. Zero Milestone 5.6 changes. Zero staging/production changes. No existing recommendation logic was modified. No broad implementation was begun — every proposal above is a design, not a diff.
