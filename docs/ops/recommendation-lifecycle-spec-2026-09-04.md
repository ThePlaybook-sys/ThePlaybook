# MANSA Recommendation Lifecycle — Spec (2026-09-04)

**HQ DECISION LOCK (2026-09-04, same day as the original spec).** HQ reviewed the report below and issued a locked decision on all nine open items. The original spec (§1-9) is preserved below unedited for the record; this block is the authoritative resolution and takes precedence wherever the two differ.

1. **Vocabulary approved as proposed:** `STRENGTHENED`/`WEAKENED`/`NO_LONGER_QUALIFIES`/`REPLACED`. `recommendation_products.status` stays binary `active`/`withdrawn` — no new status value.
2. **`REPLACED` always creates a NEW `recommendation_products` row AND a NEW `recommendation_activation_snapshots` row.** Never mutates the original recommendation or its original snapshot.
3. **Grading policy ratified as mandatory:** once activated, a recommendation remains independently gradeable on its ORIGINAL frozen terms even if later weakened, withdrawn, no longer qualifies, or replaced. A replacement/reversal that is itself activated is a separate, independently gradeable MANSA decision. This is HQ's own named mandatory protection against survivorship bias — not merely a recommended policy.
4. **`user_recommendation_placements` approved.** Records USER-REPORTED placement/exposure, not sportsbook-verified execution. Placed status changes communication context only — never grading — and must never imply MANSA can cancel/cash-out/hedge the wager.
5. **Do not implement or extend `market_monitoring_events` solely for lifecycle now.** Phase 7 remains solely responsible for Market Integrity signals and that table. This lifecycle capability's own `trigger_type` column borrows the same value-strings but is a separate, own-table CHECK constraint — no dependency on Phase 7 code to exist before this schema can be built.
6. **Milestone 5.6 approved as a mandatory pre-Beta milestone — phased.** Basic lifecycle mechanics (schema, vocabulary, `user_recommendation_placements`) may be implemented earlier, ahead of Phase 7/Phase 8. Milestone 5.6 cannot be considered COMPLETE, however, until real Phase 7/Phase 8 signals can actually feed `trigger_type` — a build with no real signal behind anything but `model_refresh` does not satisfy this milestone's purpose.
7. **Dashboard behavior locked at the principle level:** a materially changed recommendation must never silently disappear or overwrite its previous state, on any surface. Exact visual treatment remains a future implementation/design decision, not decided here.

**Recorded into:** Volume 3 §5G (v4.28, "HQ Decision Lock" subsection), Volume 4 §9.7 (v5.13), Engineering Roadmap Milestone 5.6 (v4.9), `CHANGELOG.md`, `PROGRESS.md` — all same date. **No implementation, migration, or code change was made to record this lock** — every file touched is under `docs/`; grading logic, recommendation logic, UI, Telegram, workers, and staging/production remain untouched.

---


**PLANNING / SPEC ONLY. Nothing in this document is implemented.** No code, migration, grading logic, recommendation logic, UI, or Telegram integration was changed to produce this report. Staging and production were not touched. This document answers HQ's 2026-09-04 directive: formally define what happens when MANSA changes its view after a recommendation has already been activated and potentially acted on by a user.

Companion changes made alongside this report (docs only): `docs/blueprint/volume-3-database-architecture.md` new §5G (v4.27), `docs/blueprint/volume-4-ai-intelligence.md` new §9.7 (v5.12), `docs/blueprint/engineering-roadmap-build-order.md` new proposed Phase 5 Milestone 5.6 (v4.8), `CHANGELOG.md`, `PROGRESS.md`.

---

## 1. Files changed

| File | Change |
|---|---|
| `docs/blueprint/volume-3-database-architecture.md` | v4.26 → v4.27. New §5G: proposed `recommendation_product_lifecycle_events.event_type` extension, new `trigger_type`/`trigger_event_data`/`related_recommendation_product_id` columns, new `user_recommendation_placements` table, explicit status-blind grading policy. All ARCHITECTURE RESERVATION ONLY — no migration applied. |
| `docs/blueprint/volume-4-ai-intelligence.md` | v5.11 → v5.12. New §9.7 (Recommendation Lifecycle & Change Communication): purpose, lifecycle vocabulary, trigger vocabulary, user-facing behavior, grading policy, relationship to §9.5. FUTURE CAPABILITY, NOT YET IMPLEMENTED. |
| `docs/blueprint/engineering-roadmap-build-order.md` | v4.7 → v4.8. New proposed (not authorized) Phase 5 Milestone 5.6; Phase 12 (Beta) dependency list gains this milestone as an explicit mandatory prerequisite alongside the existing Phase 8 requirement. |
| `docs/ops/recommendation-lifecycle-spec-2026-09-04.md` | New — this report. |
| `CHANGELOG.md` | New dated entry (MINOR, Volume 3 + Volume 4 + Roadmap), four-field format. |
| `PROGRESS.md` | New dated entry. |

No application code, migration, test, or config file was touched. No table was created. No cron/worker/subscription/provider was touched.

---

## 2. Proposed lifecycle states

Two separate things were being asked for, and keeping them separate is the actual design decision:

**A. `recommendation_products.status` (unchanged) — the binary actionability gate.** Stays exactly `active` / `withdrawn`, as it is today (Volume 3 §5A, live since Milestone 5.1). This column is what RLS, the dashboard, and every existing consumer already key off. **No new status value is proposed** — adding shades of gray here (e.g. a `degraded` status) would ripple into every consumer that reads `status` today and blur the one binary question it needs to answer cleanly: is this currently presented as actionable?

**B. `recommendation_product_lifecycle_events.event_type` (extended) — the append-only narrative log.** This table already exists, is already append-only, and already allows multiple events per product (Milestone 5.3, live). It currently has `ACTIVATED` / `WITHDRAWN` / `SOFT_DELETED`. Proposed additions:

| Event | Meaning | Does it change `status`? |
|---|---|---|
| `STRENGTHENED` | New evidence increased confidence in the original call | No — stays `active` |
| `WEAKENED` | New evidence reduced confidence, not yet disqualifying | No — stays `active`. **This is HQ's own 11:30 AM moment** (WR1 ruled out, before a formal withdrawal decision) |
| `NO_LONGER_QUALIFIES` | Re-check against §9's frozen qualification rule (`confidence >= 0.55` AND `ev_per_dollar > 0`) failed under current information | No, by itself — this is the *reason*, fired alongside or just before `WITHDRAWN`, which is what actually flips `status` |
| `REPLACED` | Superseded by a separately-activated new `recommendation_products` row (a reversal) | Fires on the OLD product alongside its own `WITHDRAWN` — never a same-row mutation |

`ACTIVATED`/`WITHDRAWN`/`SOFT_DELETED` are unchanged. This is a **reuse of existing schema, not new terminology invented from scratch** — the table, its append-only trigger, and its per-product multi-event support already exist; only the CHECK constraint's allowed values grow.

**Why not adopt HQ's example wording ("degraded") literally:** "weakened" was chosen over "degraded" only because `market_monitoring_events` (below) already uses `action_taken='updated'` as its closest existing analog, and "weakened"/"strengthened" read as a clean opposite pair in a UI without needing a third neutral state. This is a naming call HQ should confirm, not a load-bearing decision — see §9 below.

---

## 3. Trigger rules

HQ named six trigger categories. `market_monitoring_events` (Volume 3 §7, live schema, **zero rows, zero code** — reconfirmed by direct inspection this pass) already has an `event_type` CHECK covering four of them almost exactly:

```sql
event_type check (event_type in
  ('line_movement','injury_update','weather_change','lineup_change','breaking_news'))
```

Mapped against HQ's list:

| HQ's trigger category | Existing vocabulary | Status |
|---|---|---|
| Injuries/inactives | `injury_update` | Reused verbatim |
| Lineup/depth-chart changes | `lineup_change` | Reused verbatim |
| Weather | `weather_change` | Reused verbatim |
| Market movement / odds-price deterioration | `line_movement` | Reused verbatim |
| New news | `breaking_news` | Reused verbatim |
| Contextual intelligence changes (Phase 8) | — none exists | **New: `contextual_intelligence_change`** |
| Model/recommendation refresh | — none exists | **New: `model_refresh`** (a routine Strategy/consensus recompute, e.g. an Elite second-pass, surfacing a different result on the same underlying evidence) |

Proposed: add a `trigger_type` column to `recommendation_product_lifecycle_events` using this exact seven-value vocabulary (Volume 3 §5G), plus a `trigger_event_data jsonb` column for the qualitative factual payload (e.g. `{"player": "...", "status": "OUT", "previously": "QUESTIONABLE"}`). **This column must never carry a fabricated new EV/confidence number** — no re-evaluation numeric engine exists (§6 below), and inventing one here would repeat exactly the kind of fabricated-intelligence mistake this Blueprint has refused everywhere else (`would_change_mind_if`, CLV, `narrative_summary`).

`market_monitoring_events` itself is not built — no worker writes it, no code reads it (Phase 7 Milestone 7.0's own audit already established this; re-confirmed here). This spec defines shared vocabulary two future consumers (Market Integrity/§8.5 and this lifecycle capability) will eventually need — it does not build the detection logic for either.

---

## 4. Dashboard/Telegram behavior

**Time Machine already gets most of this right — a real, positive finding, not a gap.** Volume 5 §5's `HistoryJourneyProps.whatChanged` stage already:
- Renders `lifecycleEvents: { eventType: 'ACTIVATED' | 'WITHDRAWN' | 'SOFT_DELETED'; timestamp; reason }[]`
- Defaults to **"No material changes recorded"** rather than disappearing when there's nothing to show
- Is structurally forbidden (Volume 5's own Milestone 4 "temporal integrity" rule) from letting Stage 1 (`whatWeRecommended`) render the product's *current* status/grade — those facts appear only in `whatChanged`/`whatHappened`, never overwriting the original card

This is precisely "preserve the original, surface the change separately, never silently disappear" — already built, for Time Machine's historical view. **The only gap here is vocabulary**: the TypeScript union needs the four new event types, plus a field to render `REPLACED`'s link to the new product.

**Live dashboard (`/today`) has no equivalent spec today — a genuine, disclosed gap.** Volume 5 documents no behavior for a product that transitions `active → withdrawn` (or gains a `WEAKENED`/`STRENGTHENED` event) while still on the live dashboard. Proposed minimum: the card is never simply removed; at minimum it updates in place to an honest changed-state ("Updated 11:30 AM — see what changed") linking into the same lifecycle-event detail. Exact visual treatment is a Phase 6-adjacent UX decision, not decided here.

**Telegram/future alerts — a channel-specific risk worth naming explicitly.** Telegram (and any future push/SMS channel) doesn't exist yet (confirmed: no `notifications` table, no Telegram Companion built — Volume 5 §7). But a chat bot *can* edit or delete its own prior message, which is exactly the "silently rewrite what MANSA already said" failure mode this whole task exists to prevent. Whenever that capability is built: a lifecycle-change event on a product a user was already alerted about must always be sent as a **new, threaded follow-up message** — never an edit or deletion of the original alert.

**"Placed" status — confirmed real gap, proposed fix.** `user_recommendation_selections` (Volume 3 §5A) has no boolean/timestamp for "the user told MANSA they placed this." Proposed: a new standalone table, `user_recommendation_placements` (product/leg/user, `placed_at`) — not an extension of `user_recommendation_selections`, whose materiality-suppression trigger has different semantics that a `placed` toggle would break. MANSA cannot infer placement from anything else it observes (no sportsbook integration exists or is proposed) — this table only ever reflects the user's own self-report.

**Effect of "placed" on subsequent communication, per HQ's explicit instruction not to assume any cancel/hedge/cash-out capability:** once a placement row exists, later lifecycle-change messaging shifts from actionable framing ("we no longer recommend this") to purely informational framing — e.g. *"This information is for your awareness only. MANSA cannot cancel, hedge, or cash out a sportsbook wager on your behalf."* Placement status affects **tone only** — it never changes grading, Track Record, or whether an event fires.

---

## 5. Grading / Track Record policy

**Direct code inspection performed this pass** (`apps/ai-orchestrator/app/persistence/postgame_grading.py`, `apps/ai-orchestrator/app/orchestration/postgame_grading.py`) — every grading read function was checked line by line:

- `read_recommendation_legs_by_game`, `read_recommendation_legs_by_product`, `read_no_bet_products_by_game`, the `bankroll_preservation` reader — filter only by `game_id` / `recommendation_product_id` / `recommendation_type`. **None filter by `recommendation_products.status`.**
- `grade_game`, `_maybe_rollup_product`, `grade_pending_bankroll_preservation_products` — read every leg for a game and grade it; `_is_grading_eligible` checks only `games.status`/`games.finalized_at` (a GAME-level check), never anything on `recommendation_products`.

**Finding: a withdrawn (or, in the future, replaced) product's legs are graded today exactly like an active product's, on their frozen activation-time terms — by omission, not by a written, tested policy.**

Answering HQ's four questions directly:

1. **Does an activated recommendation remain gradeable even if later withdrawn? Yes.** Confirmed by the code inspection above. Proposed: ratify this explicitly as **"grading is status-blind by design"** (Volume 3 §5G) — this is the exact mechanism that prevents MANSA from improving its record by withdrawing recommendations after activation. Withdrawal changes what a user is told to do *next*; it never changes what MANSA is scored on for what it already said. **A regression test proving this does not exist yet** — flagged as a missing piece (§7).
2. **How should replacement/reversal events be represented?** As two independent, separately-graded `recommendation_products` rows, linked by the proposed `related_recommendation_product_id` on the OLD product's `REPLACED` event. Track Record's `sampleSize`/`record` counts both, never collapsed into one observation.
3. **Which snapshot/price should grading use?** Always `recommendation_legs`' own frozen `american_odds`/`point`/`ev_per_dollar`/`final_aggregate_confidence` — unaffected by any `STRENGTHENED`/`WEAKENED`/`NO_LONGER_QUALIFIES` event, which never carry a re-evaluated number (§6). This is unchanged from today; legs are already 100% immutable with zero UPDATE path anywhere in the codebase.
4. **How do we distinguish MANSA's original decision from its later updated one?** The original is `recommendation_activation_snapshots` + `recommendation_legs` for the original product, untouched forever. The updated decision, if one is ever made, is always a **separate, new** `recommendation_products` row — never a mutation of the old one. `REPLACED` + `related_recommendation_product_id` is the linkage connecting the two without merging them.

**The existing 72-hour finality gate is preserved exactly as-is, and is fully orthogonal.** `RECONCILIATION_WINDOW_HOURS = 72` (Volume 4 §9.6) governs only when `games.final_score` becomes authoritative for grading; nothing about lifecycle/withdrawal events touches that timing.

---

## 6. What current schema already supports

- `recommendation_products.status`/`.withdrawn_at`/`.withdrawal_reason` — the binary actionability gate (live).
- `recommendation_product_lifecycle_events` — append-only event log, already supports multiple events per product, already has 3 of the ~7 event types this spec needs (live).
- `recommendation_activation_snapshots`/`_legs`/`_source_products` — the frozen, ever-immutable "what we knew" manifest Time Machine's Stage 2 already reads (live).
- `recommendation_legs` — 100% immutable, zero UPDATE path anywhere in the codebase (confirmed by inspection this pass) — the guarantee this entire spec is built on top of, not something it needs to add.
- `recommendation_leg_explanations.would_change_mind_if` — a pre-existing, narrower "invalidating condition" concept (a single frozen quote from the top supporting agent, captured at activation) — conceptually adjacent to, but not a substitute for, an ongoing change-tracking mechanism.
- `market_monitoring_events` — reserved trigger vocabulary (`event_type`/`action_taken`) extremely close to what this spec needs, though zero rows/zero code (Phase 7 Milestone 7.0's own finding, reconfirmed).
- Volume 4 §9.5 (Bet Timing, future) — already establishes the ANALYSIS/STRATEGY/EXECUTION three-question distinction and already requires (as a design constraint on Time Machine, not yet built) preserving "every subsequent price observed, every state transition and its reason" — the general shape of this spec's own requirement, previously scoped only to price/execution.
- Volume 5 §5 Time Machine — `whatChanged` stage and the Milestone 4 "temporal integrity" rule already implement "preserve original, surface change separately, never silently disappear" for the historical view, with the right event-type union just needing new values.
- The postgame grading pipeline — already status-blind by omission (this pass's own direct-inspection finding), which is the *correct* behavior, just not yet a documented, tested policy.

---

## 7. Missing schema/logic/UI pieces

- Four new `recommendation_product_lifecycle_events.event_type` values (`STRENGTHENED`/`WEAKENED`/`NO_LONGER_QUALIFIES`/`REPLACED`) — proposed, not built.
- `trigger_type`/`trigger_event_data`/`related_recommendation_product_id` columns on that same table — proposed, not built.
- A new `user_recommendation_placements` table — proposed, not built.
- A regression test proving grading is status-blind (a withdrawn product's legs still get a real grade event) — does not exist.
- Volume 5 vocabulary update: `whatChanged.lifecycleEvents[].eventType` union needs the four new values, plus a `trigger`/`relatedRecommendationProductId` field.
- Live-dashboard behavior spec for an active→withdrawn (or weakened/strengthened) transition intraday — genuinely undesigned today, Time Machine's spec covers only the historical view.
- Any Telegram/notification spec at all — `notifications` table and Telegram Companion remain fully unbuilt (confirmed again this pass); the "always a new threaded message, never an edit" principle above is new guidance with nothing yet to attach it to.
- The actual detection/trigger code for any of this — `market_monitoring_events`/`worker-market-monitor` remain zero rows/zero code; this spec defines vocabulary, not a working pipeline.
- A re-evaluation numeric engine (recomputing EV/confidence against new information) — explicitly out of scope here and for §9.5; genuinely does not exist anywhere in the codebase.

---

## 8. Dedicated future milestone needed before Beta?

**Yes.** Proposed as Phase 5 **Milestone 5.6 — Recommendation Lifecycle & Change Communication** (Engineering Roadmap v4.8, proposed, NOT authorized to build) — placed as a continuation of Phase 5's own product/leg/lifecycle-event layer (the tables it extends are 5A's and 5C's own), rather than folded into Phase 7 (Market Integrity — a different axis, execution/price vs. this milestone's analytical-validity/communication axis) or Phase 8 (Contextual Performance Intelligence — one of several trigger *inputs* to this milestone, not its owner). Phase 12 (Beta)'s dependency list now names Milestone 5.6 as an explicit mandatory prerequisite, alongside the existing Phase 8 requirement — HQ's own stated reason (real recommendations will change between morning analysis and kickoff during any live beta cohort) matches this roadmap's existing Beta acceptance criteria, which already depend on the Time Machine reproducibility claim holding under real-world scrutiny.

---

## 9. Decisions HQ still needs to make

1. **Approve or rename the proposed event-type vocabulary** (`STRENGTHENED`/`WEAKENED`/`NO_LONGER_QUALIFIES`/`REPLACED`) — these are a reasonable naming choice, not a load-bearing one; HQ may prefer different words.
2. **Approve extending `market_monitoring_events.event_type`** with `contextual_intelligence_change`/`model_refresh` now (as vocabulary, unbuilt) versus deferring that specific extension until Phase 7/8 are actually scheduled.
3. **Confirm `user_recommendation_placements` as a new standalone table** (this report's recommendation) versus extending `user_recommendation_selections` some other way.
4. **Decide the live-dashboard UX** for an intraday active→withdrawn/weakened/strengthened transition — genuinely open, no existing Volume 5 text to defer to.
5. **Confirm `REPLACED` always means a new activated product row, never a same-row state change** — this report's framing keeps `recommendation_products`' "one row = one immutable decision" invariant airtight; HQ should ratify or challenge that constraint before it's built.
6. **Confirm Milestone 5.6's placement** (proposed: reopens Phase 5, required before Phase 12/Beta) versus an alternative placement HQ prefers.
7. **Sequencing against Phase 7/Phase 8** — Milestone 5.6's trigger vocabulary references both `market_monitoring_events` (Phase 7's own eventual detection target) and Phase 8's contextual intelligence; HQ should decide whether Milestone 5.6 can ship its schema/communication layer independently of either being fully built (this report assumes yes, since it only reserves vocabulary and does not require the detection workers to exist), or whether it should wait.

---

## Guardrails observed while producing this report

No code changed. No migration applied. No grading logic changed. No recommendation logic changed. No UI changed. No Telegram integration touched (none exists). No cron/worker/subscription/provider changed. Staging and production not touched. Phase 7 gates (`cron-odds-worker` SKIPPED, Odds/Player Props Worker untouched) unaffected — no worker file was read or modified in producing this report. No numeric threshold was invented (no LINE LOST percentage, no re-evaluation formula) — every number-shaped question was either answered from an existing frozen value (`>= 0.55`, `> 0`, `72h`) or explicitly left open per this report's own §9.
