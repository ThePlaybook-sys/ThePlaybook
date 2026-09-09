# Extensible Market & Player-Prop Taxonomy — Architecture Lock (2026-09-09)

**Status: DOCUMENTATION ONLY. No runtime code, schema, or migration was
implemented or authorized by this document.** This is Part B of the Phase
8.5 Pass 4 HQ directive, produced alongside Part A (real Top-N retrieval
code, `docs/ops/phase-8.5-pass4-top-n-retrieval-2026-09-09.md`) but
deliberately kept separate: Part B is a permanent architecture decision
record, not a build. Cross-referenced from `PROGRESS.md`'s Pass 4 entry.

Any future pass that wants to act on this document must obtain its own
explicit HQ authorization — this document authorizes nothing by itself, per
the same discipline already established for every prior audit-before-build
pass in Phase 8.5 (Pass 2's `ev_per_dollar` verification, Pass 3's
`market_type` audit).

---

## 1. Current fact (traced against live source and schema this pass, not assumed)

`recommendation_legs.market_type` — real, DB-enforced: `text not null check
(market_type in ('moneyline','spread','total','prop'))`
(`supabase/migrations/20260825120000_recommendation_products_schema.sql:137`).
The CHECK constraint **permits** `'prop'`. In practice, only
`'moneyline'`/`'spread'`/`'total'` are ever written — `'prop'` is a
schema-allowed value that no candidate-generation path produces (excluded
since Milestone 4.7, confirmed by grep of
`apps/ai-orchestrator/app/features/candidate_generation.py:77`, and reconfirmed
this pass).

**`'prop'` alone must NOT be treated as sufficient long-term player-prop
architecture.** A single flat string value carries no player identity, no
stat/metric, no line, no side — it cannot represent a real player prop even
if candidate generation were turned back on for it tomorrow. This is the
central fact this whole document exists to act on.

## 2. Long-term principle: no small permanently hard-coded bet-type/prop-name list

MANSA must not depend on a small, permanently hard-coded bet-type or
prop-name list (the way `_MARKET_TYPE_PHRASES`/`MarketType` in
`app/request_intent.py` today is a deliberately narrow, Pass-3-scoped
enum — appropriate for Phase 8.5's own narrow objective, **not** appropriate
as MANSA's permanent long-term market taxonomy). Provider market names
(The Odds API's `h2h`/`spreads`/`totals`, or any future provider's own
player-prop market keys) are **source data** that must be normalized into
canonical MANSA concepts, exactly as ingestion already does for the three
markets that exist today (`_BULK_MARKET_TYPE` in
`apps/sports-intel-layer/app/adapters/providers/the_odds_api.py`) — the
long-term direction is the same normalization discipline, extended to a
dimensional model that can actually represent a player prop, not a bigger
flat string enum.

**Conceptual dimensional model** (illustrative shape, not a schema):

```
SPORT -> LEAGUE -> EVENT/GAME -> MARKET FAMILY -> SUBJECT/ENTITY
      -> STAT/METRIC -> LINE -> SIDE/OUTCOME -> PRICE/ODDS
      -> PROVIDER/SOURCE -> OBSERVATION TIMESTAMP -> MARKET CONTEXT
```

**Exact schema design (tables, columns, types, migrations) is explicitly NOT
authorized in Pass 4.** This is a conceptual/dimensional shape for future
design work to start from, not a blueprint to implement.

## 3. Market families

Illustrative, not necessarily a complete semantic description of any one
family:

- **Moneyline** — who wins the event outright.
- **Spread** — margin-of-victory market (point spread / run line / puck line
  / etc., depending on sport — see §4).
- **Game total** — over/under on a whole-game aggregate stat.
- **Player prop** — a market on an individual player's statistical output.
- **Team prop** — a market on a team-level statistic other than the
  game total (e.g., team total points, first-team-to-score).
- **Game prop** — a market on a game-level event that isn't a
  moneyline/spread/total (e.g., will the game go to overtime).
- **Multi-leg/parlay products** — combinations of legs across one or more of
  the families above, **where separately authorized** — this document does
  not authorize building them; `multiple_singles` already exists in the
  schema as MANSA's honest current answer to "multiple picks," per the
  2026-09-09 end-to-end audit's own parlay-boundary finding.

These are families, grouping concepts — not a claim that every family above
is fully specified by this document. Any given family (player prop most of
all) needs its own further-detailed design before it could be built.

## 4. Sport-specific terminology maps into the canonical framework, never a separate architecture per sport

NFL/NBA "spread," MLB "run line," NHL "puck line" are all, conceptually, the
same market family (margin-of-victory against a line) expressed in each
sport's own vernacular — they must map into one canonical `spread`-family
concept, not spawn a parallel `run_line`/`puck_line` architecture duplicating
spread's own logic. The same discipline applies to any other sport-specific
naming that turns out to mean the same underlying market shape.

**Provenance is preserved, not destroyed, by normalization.** Exactly as
Pass 3's audit found already true for moneyline/spread/total today (the
provider's own vendor key survives in `odds_snapshots`, only the
canonicalized value is carried onto `recommendation_legs`), the original
provider/sport terminology (e.g., "MLB run line," the exact vendor market key
a provider used) must remain available for display/provenance/audit/
reconciliation purposes — normalizing into a canonical `spread` concept must
never mean the source truth of what the provider actually called it is lost.

## 5. Player prop principle: "prop"/"player_prop" alone is insufficient

Any future player-prop intelligence must be able to distinguish, at minimum:

- **Player identity** (which real, sport-scoped person — the schema's real,
  currently-unpopulated-for-this-purpose `sports`/`leagues`/`seasons`
  identity tables, per the 2026-09-09 architecture audit's own finding,
  already point at how this should resolve without inventing a second
  player-identity system).
- **Sport** and **league**.
- **Event/game** the prop belongs to.
- **Stat/metric** the prop is on (e.g., passing yards, rebounds — see
  illustrative examples below).
- **Offered line** (the numeric threshold, where applicable).
- **Side/outcome** (over/under, yes/no, or a named outcome).
- **Offered odds** (the actual priced number, exactly as spread/total/
  moneyline already carry `american_odds`/`decimal_odds`).
- **Provider/source** (which vendor offered this exact prop at this exact
  line/price).
- **Observation timestamp** (when this offer was actually seen — props move
  faster and more granularly than game lines).
- **Relevant context** (whatever downstream intelligence needs to reason
  about this specific prop honestly — e.g., injury status, matchup, recent
  form — not a fixed, exhaustive list).

**Illustrative (not exhaustive, not a fixed whitelist) NFL/NBA stat
examples** — given to make the dimensional shape concrete, not to define a
permanent enum: NFL — passing yards, passing touchdowns, rushing yards,
receptions, receiving yards, interceptions thrown. NBA — points, rebounds,
assists, three-pointers made, points+rebounds+assists combined. A real
implementation must be able to add a new stat/metric (a new NHL or MLB one,
for instance) as a **data value**, never as a new hard-coded field, column,
or code branch — this is the direct consequence of §2's "no small
permanently hard-coded list" principle applied to player props specifically.

## 6. Natural-language principle: LLM interprets language, never invents evidence

Future flow:

```
USER NL -> LLM/language understanding -> STRUCTURED REQUEST
        -> DETERMINISTIC MANSA INTELLIGENCE -> RESPONSE
```

An LLM may be used to interpret ambiguous or varied natural language into a
structured request (the same kind of structured request
`app.request_intent`'s own deterministic pipeline already produces via
pattern matching, today, with zero LLM involvement — the LLM's future role
would be widening what natural language MAPS INTO that same structured shape,
not replacing the shape itself). It must **never** become the authority that
invents betting evidence, modeled probabilities, expected value, confidence,
market semantics, qualification, or recommendation decisions — those remain
MANSA's deterministic responsibility, exactly the discipline
`app.features.market`/`grading`/`consensus`/`strategy` and this endpoint's
own `request_intent.py` already follow today with zero LLM calls anywhere in
this pass's diff or any prior Phase 8.5 pass's diff.

**If a concept cannot be safely normalized, the system must not guess.** It
leaves the concept unmapped, or fails honestly (an UNSUPPORTED response with
a real reason — exactly `request_intent.py`'s existing pattern for "prop"/
"props"/"player prop" today) rather than inventing a mapping that might be
wrong.

## 7. Performance/query principle

Future direction:

```
PROVIDER INGESTION -> NORMALIZATION -> PERSISTED/INDEXED CURRENT MARKET STATE
        -> CONTEXT/MODELING/RECOMMENDATION INTELLIGENCE
        -> USER FILTERING/RANKING -> RESPONSE
```

This mirrors the shape this endpoint already follows today for the three
existing markets: provider ingestion normalizes at write time
(`_BULK_MARKET_TYPE`), the normalized value is persisted
(`recommendation_legs.market_type`), and `/ask`'s own Pass 4 filter → rank →
limit logic (§Step 4 of the companion Part A document) is exactly "user
filtering/ranking" over already-persisted, already-indexed state — no
on-demand computation, no per-request provider call. A future player-prop
taxonomy should preserve this same shape: normalize and persist at ingestion,
filter/rank/limit at request time, never compute on demand inside a user's
request. **Freshness and refresh cadence for player-prop data specifically
are separate future decisions, not implemented or specified here** — props
may need faster/more granular refresh than game lines, but that is a Master
Refresh/ingestion-cadence question for a future pass, not this document.

## 8. Multi-sport extensibility principle

MLB/NBA/NHL/etc. should **extend** the canonical framework above (§2-§5),
each contributing its own sport-specific market-family terminology (§4) and
stat/metric vocabulary (§5) as data, not as a parallel architecture.
Sport-specific rules are expected and legitimate (a run line is genuinely not
computed identically to an NBA spread in every respect) — but duplicating
MANSA's core recommendation architecture (candidate generation, evaluation,
consensus, qualification, ranking) per sport is explicitly the outcome this
principle is meant to prevent. This is consistent with, and does not
contradict, the 2026-09-09 end-to-end audit's own finding that
`games.sport_id`/`league_id`/`season_id` already exist as real, populatable
FK columns capable of carrying sport/league identity through the existing
pipeline without new columns elsewhere.

## 9. Provider-source preservation (restated as its own item, per HQ's 10-item requirement)

Every normalization step in this framework — market family, stat/metric,
sport-specific terminology — must preserve the original provider/source
representation alongside the canonical one, not instead of it. This is not a
new principle invented for player props; it is the same discipline Pass 3's
audit already confirmed the existing moneyline/spread/total pipeline follows
(`odds_snapshots` carries the vendor's own market key; only the canonicalized
value is carried forward from there), generalized explicitly so it is not
lost when a genuinely more complex taxonomy (with many more source vocabularies
across many more providers and sports) gets built.

## 10. Explicit statement: no runtime or schema implementation was authorized here

This document is a decision record and a set of constraints for future
design work. **Nothing in this document should be read as authorization to
create a migration, a new table, a new column, a new enum value, a new
candidate-generation path, a new ingestion adapter, or any other runtime
change.** Every principle above (§2 dimensional model, §5 player-prop
dimensions, §6 NL-to-structured-request flow, §7 persisted/indexed
performance shape, §8 multi-sport extensibility) is conceptual guidance for
whichever future HQ-authorized pass takes on player-prop or multi-market
taxonomy work — that pass must obtain its own explicit authorization, propose
its own concrete schema, and will very likely need its own STOP-and-report
cycle for any migration, per this project's standing "no schema migration
without STOP + HQ authorization" rule.

## Contradiction check against current code

No contradiction was found between this document's direction and the current
Pass 1-4 implementation of `/ask`. One minor, pre-existing, out-of-scope
observation is recorded here rather than fixed (per HQ's "if existing code
materially contradicts this direction: REPORT the contradiction, do not
redesign it this pass" instruction): the Pass 4 directive's own illustrative
example phrase, "top 2 best-value totals" (hyphenated "best-value"), does not
literally match `_HIGHEST_VALUE_PHRASES` in `app/request_intent.py` — only
the space-separated `"best value"` is recognized. This is a Pass-2-era
phrase-list coverage gap, unrelated to the taxonomy direction in this
document, and is not fixed here.
