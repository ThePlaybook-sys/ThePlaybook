# First Live Recommendation Proof — Cost-Bounded Activation (2026-09-18)

**Directive:** MANSA HQ — prove one genuine pre-kickoff recommendation end to end with bounded
spend. At most 1 eligible game, hard LLM ceiling 48, no silent truncation, deterministic selection
using the existing architecture's ordering rule.

**Status: ARMED AND VERIFIED. The run has NOT happened yet.** It fires on the next natural
`cron-recommendation-worker` tick, **2026-09-19 06:15 UTC**. No cycle was manually triggered.

---

## The ordering question — resolved, with one disclosed judgment

The directive said to stop and report if no authoritative ordering rule exists. **One exists**, so
this pass proceeded:

> **Volume 5 — "Neutral ordering (HQ Final Decision 1):** game-scoped cards order by
> `games.scheduled_start` … **Never EV or confidence.** No response field is named or implies
> "primary"/"top"/"best" — multiple same-day recommendations are an unordered-by-intelligence set
> with a neutral chronological display order."

`read_eligible_game_ids` already sorted `scheduled_start.asc`, so taking a prefix means "soonest
kickoff first" — the architecture's own rule, not a new one.

**But chronological alone turned out to be underdetermined against real data, and this only shows up
by looking:** **eight** Week 2 games share the same `2026-09-20 17:00:00 UTC` kickoff. PostgREST
leaves the order among ties unspecified, so "the first game" would not reproduce between calls.

**The judgment I made, stated plainly rather than buried:** the tiebreak is `id.asc`. A row id
carries no intelligence — it is not EV, not confidence, not any judgment about the game — so
breaking ties on it keeps the set "unordered-by-intelligence" exactly as Decision 1 requires, while
making a prefix deterministic. It is a determinism mechanism, not a second ranking rule. If HQ
prefers a different tiebreak, it is a one-line change and the selected game changes with it.

---

## Pre-activation verification — all 6 items

Measured against live dev at **2026-09-18 12:30 UTC**.

### Selected game

| | |
|---|---|
| Matchup | **TB @ CLE** |
| `game_id` | `0f659b0a-c6f7-4bec-afe2-43720f7618a0` |
| Kickoff | **2026-09-20 17:00:00 UTC** |
| Week | 2, `season_type=regular` |
| Status | `scheduled` |

| # | Required check | Result |
|---|---|---|
| 1 | genuinely pre-kickoff | ✅ **52.2 h** to kickoff; still ~34.75 h at the 06:15 tick |
| 2 | fresh odds exist | ✅ 3 V1 markets (moneyline, spread, total); age 1218 min vs a 1445 min FAR ceiling |
| 3 | DK or FD reference pricing resolves | ✅ **both** `draftkings` and `fanduel` present |
| 4 | all deterministic gates pass | ✅ canonical, scheduled, upcoming, in-horizon, fresh odds, `the_odds_api` identity resolved (1 mapping), no completed cycle |
| 5 | no other game can enter the LLM path | ✅ `RECOMMENDATION_MAX_GAMES_PER_CYCLE=1` — 15 of 16 deferred untouched |
| 6 | hard ceiling 48 at the adapter | ✅ `MAX_LLM_CALLS_PER_GAME=48`, enforced in `ModelAdapter.complete` |

**One timing dependency, named in advance.** At the 06:15 tick the odds will be ~30 h old unless the
odds worker refreshes first. It is due to: the last capture was 2026-09-18 00:01 UTC and the FAR
tier polls every 24 h, so a refresh lands around 2026-09-19 00:01, leaving the odds ~6 h old at
06:15 — comfortably inside the ceiling. **If that refresh does not happen, the game returns
`skipped_ineligible` at zero cost and retries next cycle.** That is the gate working, not a failure,
and it is the honest risk to this proof.

---

## The throttle — explicit, never silent

`RECOMMENDATION_MAX_GAMES_PER_CYCLE` is deliberately a **different mechanism** from
`RECOMMENDATION_MAX_GAMES_PER_RUN`, and conflating them would be a real error:

| | Safety ceiling (`_PER_RUN`) | Activation throttle (`_PER_CYCLE`) |
|---|---|---|
| Meaning | the eligibility contract is **wrong** | the slate is **right**, we are choosing a prefix |
| Behaviour | refuses entirely, dispatches **0** | processes N, defers the rest untouched |
| Status | `failed` | **`completed_limited`** |
| Default | 20 | **unset (no throttle)** |

`completed_limited` exists precisely so a partial pass can never be read as a full slate. The result
carries `games_selected=16`, `games_deferred=15`. Deferred games are **not failures and not
marked** — untouched, and the next cycle takes them normally. A malformed value yields *no* throttle
rather than an unintended one.

## Live armed state

| Service (dev) | Variable | Value | Deployment |
|---|---|---|---|
| `ai-orchestrator` | `REFERENCE_SPORTSBOOK_PREFERENCE` | `draftkings,fanduel` | **`d7ce2026` SUCCESS 12:42:56** |
| `ai-orchestrator` | `MAX_LLM_CALLS_PER_GAME` | `48` | same |
| `worker-scheduled` | `RECOMMENDATION_MAX_GAMES_PER_CYCLE` | `1` | **`677b53cb` SUCCESS 12:50:04** |
| `worker-scheduled` | `RECOMMENDATION_MAX_GAMES_PER_RUN` | `20` | same |

Both deployments were created **after** their variables were set, so the values are live because a
fresh deployment carrying them succeeded — not merely because the API accepted them.

## Worst-case spend for this proof

**≤ 48 model requests, refused at the adapter beyond that.** Realistically 6 game-level agents +
6 candidates × (3 chain + 1 Meta + 1 Elite) + 2 subscribers × 6 Bankroll = up to 48. No other game
can contribute: the throttle holds the slate to one.

## Tests

4 new in `apps/workers/tests/test_recommendation_worker_safety_gate.py`: exactly-one-game with
`completed_limited` and `games_deferred=15`; soonest-kickoff prefix with the ordering asserted on
the **query** (`scheduled_start.asc,id.asc`) rather than a Python re-sort; unset/malformed defaults
to no throttle; an unthrottled run is unchanged. Plus: a throttled-but-failed run is still loud.

**Regression: workers 89/89, ai-orchestrator 1000/1000** (sports-intel-layer untouched this pass).

## What happens next

The 06:15 UTC tick on 2026-09-19 runs, unattended. A self check-in at **06:45 UTC**
(`trig_01FqRmeKeNC2VDHaLUStdkFP`) collects the 16 required items from the cron log, the
`ai-orchestrator` log, and dev SQL — including the exact model-request count, the modeled
probabilities, whether a frozen prediction persisted, and whether `predicted_at < scheduled_start`.

**Nothing further will be triggered manually.**
