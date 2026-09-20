# CI repair, deployment-gate audit, and the fallback-model root cause

**Date:** 2026-09-20
**Agent lane:** `agent/backend-autonomy`
**Directive:** MANSA HQ — PAUSE → CI REPAIR → DEPLOYMENT-GATE HARDENING → SAFE INTEGRATION + FALLBACK MODEL AUDIT
**Outcome:** two parts completed, two parts stopped at their own stated conditionals, one root cause confirmed.

---

## PART 1 — Recommendation pause: STOPPED at the conditional

**Railway does not expose a suspend/pause mechanism for a cron service.** Verified two ways.

1. The MCP write surface for a service is `update-service`, whose only
   execution-related fields are `cronSchedule`, `sleepApplication`,
   `restartPolicyType`, `watchPatterns`, and build/start commands. There is no
   pause, suspend, disable, or enable field. `delete-service` is destructive
   and out of scope.
2. `describe-service` on `cron-recommendation-worker`
   (`244cbc60-7ded-485b-811a-c1f171777767`) returns no pause state — the
   service is `"state":"live"` with `"cronSchedule":"15 6 * * *"` and no
   staged changes.
3. Railway's own cron documentation (`docs.railway.com/cron-jobs`) describes
   exactly one control: the schedule field itself. Nothing else stops a cron
   service from firing.

Per the directive — *"IF Railway does not expose a genuine reversible
suspend/pause mechanism: STOP this part and report the exact supported
alternatives. Do not improvise."* — no action was taken. Alternatives are in
the report to HQ.

The next scheduled tick is **2026-09-21 06:15 UTC**.

---

## PART 2 — CI repair: COMPLETE

`apps/sports-intel-layer/tests/test_odds_cadence_persistence.py`, commit `990a422`.

**Root cause: wall-clock rot, not application behaviour.** Five of the seven
tests in the file drive the real HTTP endpoint
(`POST /v1/internal/odds-worker/run`). That endpoint deliberately has no
injectable clock — correct for production — so it calls
`datetime.now(timezone.utc)` for real. The fixtures pinned kickoff to
`2026-09-14T17:20Z`. Once that instant passed, `classify_window` correctly
returned `STOPPED` for every fixture game and `games_due` went to 0. The two
tests that already injected `now=` passed throughout, which is itself the
proof that the mechanism under test was never broken.

**Repair:** replaced the module-level `_T0` / `_KICKOFF` / `_GAME_ROW`
constants with per-test fixtures anchored relative to each test's own `now`,
keeping kickoff 50 minutes ahead so the game sits in `RAMP_60M` — the window
every assertion is written against. `RAMP_60M` spans `>15min` to `<=60min`
before kickoff, so a 50-minute anchor leaves 35 minutes of slack on one side
and 10 on the other. The file can no longer expire.

**Nothing was hidden, skipped, xfailed, deleted, or weakened.** Every
assertion is byte-identical; `git diff | grep '^[-+].*assert'` matches only
the new explanatory comment.

**Suites (local, this machine):**

| Suite | Before | After |
|---|---|---|
| sports-intel-layer | 1086 passed, **5 failed** | **1091 passed, 0 failed** |
| ai-orchestrator | 1006 passed | 1006 passed |
| workers | 110 passed | 110 passed |
| api-gateway | 187 passed | 187 passed |

---

## PART 3 — The real DEV deployment path

Reconstructed from Railway (`describe-environment` + per-service
`describe-service` on the dev environment `5c1e630f-…`) and from
`.github/workflows/ci-cd.yml`. **Documentation history was not used.**

The dev environment holds **16 services**. Their deployment triggers:

| Service | `source.branch` | cron | In GH Actions `deploy-dev` matrix |
|---|---|---|---|
| api-gateway | `dev` | — | yes |
| ai-orchestrator | `dev` | — | yes |
| sports-intel-layer | `dev` | — | yes |
| worker-scheduled | `dev` | — | yes |
| frontend | *(none)* | — | yes |
| worker-market-monitor | *(none)* | — | yes |
| cron-recommendation-worker | `dev` | `15 6 * * *` | **no** |
| cron-odds-worker | `dev` | `*/15 * * * *` | **no** |
| cron-weather-worker | `dev` | `*/15 * * * *` | **no** |
| cron-msf-postgame | `dev` | `*/15 * * * *` | **no** |
| cron-postgame-grading | `dev` | `*/30 * * * *` | **no** |
| cron-balldontlie-finalization | `dev` | `*/30 * * * *` | **no** |
| cron-news-worker | `dev` | `0 */4 * * *` | **no** |
| cron-adaptive-weighting | `dev` | `0 8 * * *` | **no** |
| cron-schedule-refresh | `dev` | `0 9 * * *` | **no** |
| cron-master-refresh | **`claude/new-session-fqsad5`** | — | **no** |

Three findings follow directly.

**1. The CI gate is real for nobody.** Every GitHub-sourced service carries
`"checkSuites": false` — Railway's native *Wait for CI* flag is **off**
everywhere. A push to `dev` starts a Railway build immediately, in parallel
with the GitHub Actions test jobs and independent of their result. The
`deploy-dev` job's `needs: [test-python-services, test-frontend]` gates only
the `railway up` calls inside that job; it has no authority over Railway's own
trigger. **A red test suite does not stop a dev deployment today.**

**2. Ten services deploy *only* via Railway autodeploy.** The GitHub Actions
`deploy-dev` matrix names six services, and two of those (`frontend`,
`worker-market-monitor`) have no branch binding at all — GH Actions is their
only path. Every one of the ten cron services is absent from the matrix.
**This makes PART 4 Option B non-viable:** disabling Railway autodeploy would
silently stop deploying the entire cron fleet, including odds, grading and
finalization.

**3. An agent branch is bound to a live dev service.** `cron-master-refresh`
deploys from `claude/new-session-fqsad5`. Its latest deployment is `CRASHED`
(2026-09-16) and it currently has no cron schedule, so it is inert — but the
binding is live, and a push to that agent branch would build and deploy into
dev. This directly contradicts the invariant PART 5 asks us to establish.
`agent/backend-autonomy` is **not** bound to any service, so pushing this
lane's work does not deploy.

---

## PART 4 — Making the gate real: STOPPED at the conditional

**The correct mechanism exists and is native.** Railway's *Wait for CI*
(`docs.railway.com/deployments/github-autodeploys#wait-for-ci`) holds a
deployment in `WAITING` until every GitHub Actions check suite on the commit
concludes, skips the deployment immediately on a failing workflow, and gives
up after two hours. It surfaces in the service config as `source.checkSuites`.

**Its documented requirement is already satisfied:** it needs a workflow with
an `on: push: branches:` directive, and `ci-cd.yml` has
`on: push: branches: [dev, main]`.

**But it cannot be set from here.** `checkSuites` is readable through
`describe-service` and is absent from every Railway MCP write tool —
`update-service` does not carry the field and `connect-service-source` does
not either. There is no Railway CLI or `RAILWAY_TOKEN` in this container.
It is a per-service toggle in the Railway dashboard.

Option A is unreachable from this session; Option B is non-viable per PART 3
finding 2. Per the directive — *"Do NOT create a new deployment architecture
if neither existing option is proven viable"* — no configuration was changed.

---

## PART 6 — Fallback model audit: **ROOT CAUSE CONFIRMED**

No registry row was added, no routing rule changed, no model call made.

### The mechanism

`ModelRouter.route()` resolves the **fallback** provider eagerly, at routing
time, before any model request is built:

```python
# apps/ai-orchestrator/app/models/router.py:102
fallback_provider=_resolve_provider(fallback_model, model_providers) if fallback_model else None,
```

and `_resolve_provider` raises when the lookup is supplied but the model is
missing from it:

```python
# router.py:64-75
if model_providers is not None:
    try:
        return model_providers[model_name]
    except KeyError:
        raise UnknownProviderError(...)
```

Production does supply the lookup. `app/main.py:150-151` builds it from
`list_active_models`, which filters `model_registry` on `status=eq.active`,
and passes it at line 169 into `run_game_recommendation`.

`fanout.py:104-126` then wraps the whole per-agent body — routing included —
in a blanket `except Exception` that returns
`AgentRunResult(status="failed", error=str(exc))`. The agent is isolated, and
**nothing is logged**.

So a routing rule whose *fallback* is unregistered does not degrade. It
**fails the agent outright, before the primary model is ever contacted.**

### The blast radius (live dev DB, `nhwjtsdebgiwskshzqiq`)

`model_registry` contains exactly two rows, both `active`:
`claude-opus-5` and `claude-sonnet-5`, both `provider = anthropic`. There is
no alias mechanism — the lookup is an exact dict key on `model_name` — and no
Haiku row under any name.

Of the 12 active `model_routing_rules`, **10 name
`claude-haiku-4-5-20251001` as fallback**. The two that do not are
`probability_modeling_analysis` and `consensus_reconciliation`, both
`claude-opus-5` → `claude-sonnet-5`.

Reproduced deterministically against the live registry contents, no provider
call:

```
RAISES      injury_analysis                  -> UnknownProviderError
ROUTES OK   probability_modeling_analysis    primary=claude-opus-5
ROUTES OK   consensus_reconciliation         primary=claude-opus-5
RAISES      expected_value_analysis          -> UnknownProviderError
```

### Why this is the observed signature

Ten of twelve task types cannot route. Their agents return `failed` before
any outbound request. The probability → EV → risk chain therefore produces no
EV, `strategy_input` is never built, the candidate list reaches the Strategy
Engine empty, and `if not qualifying:` returns `no_bet` — the false No Bet
that consumed CLE @ TB and CIN @ HOU.

Corroborating runtime evidence:

- **Railway logs**, ai-orchestrator dev, 2026-09-20: the only lines in the
  06:15–06:25 window are two uvicorn access lines, `run-game` and
  `finalize-strategy`, both `200 OK`, both stamped
  `06:19:07.961…` — **the same millisecond**. A real 22-agent fan-out cannot
  complete in the same millisecond as the finalize call. No application-level
  log line exists at all, in either window, because `run_agent` swallows the
  error without logging it.
- **`recommendation_agent_outputs` holds 3 rows, all seeded 2026-08-07**,
  attached to the seed recommendation `a9000000-…-0001`, with
  `model_name`/`provider`/`used_fallback` all NULL. A production writer does
  exist (`app/persistence/recommendations.py:255`). **No production cycle has
  ever persisted a single agent output.**
- **`recommendation_costs` holds 3 rows, all seeded 2026-08-07.** No real
  cost row has ever been written.

This is therefore not a regression. It has been the state since the routing
rules were seeded, and `used_fallback` has never once been true because the
fallback was never reachable.

### Answers to the ten questions

1. **Rules using the missing fallback (10):** `injury_analysis`,
   `vegas_line_analysis`, `closing_line_movement_analysis`,
   `rest_days_analysis`, `travel_fatigue_analysis`, `weather_analysis`,
   `expected_value_analysis`, `risk_manager_analysis`,
   `bankroll_coach_analysis`, `meta_agent_review`.
2. **Primary for each:** `claude-sonnet-5` for all ten. Both registered and
   active. The primaries are not the problem.
3. **What invokes the fallback:** nothing has to. The fallback's *provider* is
   resolved unconditionally at routing time. Invocation is irrelevant.
4. **`AdapterRegistry.get()` with an unregistered fallback:** never reached —
   `ModelRouter.route()` raises first. (For completeness, `get()` would also
   raise `UnknownProviderError` for an unregistered *provider*; here the
   provider string is never produced at all.)
5. **Does it produce the observed signature:** yes — reproduced above.
6. **Historical logs:** no primary-model failure appears before fallback
   resolution, because no primary call is ever attempted. The two windows
   contain access logs only.
7. **`model_registry` schema:** `id`, `model_name` (NOT NULL), `strengths`,
   `weaknesses`, `cost_per_1k_tokens`, `avg_latency_ms`, `preferred_tasks`,
   `capabilities`, `status`, `updated_at`, `provider` (**NOT NULL**, no
   default). A new row must supply `model_name`, `provider`, and
   `status='active'` to be picked up by `list_active_models`.
8. **Alias elsewhere:** no. Exact-key lookup, two rows, neither is Haiku.
9. **Options.**
   **A — register Haiku.** Restores the intended design. Cheapest fallback
   tier. Requires confirming the model id is currently served before trusting
   it as a safety net.
   **B — point the ten rules at an already-registered model
   (`claude-sonnet-5`).** No registry mutation, no new provider surface. But
   primary and fallback become the same model for those ten rules, so a
   primary failure retries onto an identical model — the fallback stops being
   a real fallback.
   **C — set `fallback_model` to NULL on the ten rules.** `route()` already
   short-circuits on a falsy fallback (`if fallback_model else None`), so this
   makes all ten route immediately. Honest — there is no fallback — and it
   removes the eager-resolution failure entirely.
10. **Paid-call exposure.** All three options *increase* it from the current
    zero, because the committee currently makes no calls at all. Under any
    option, ten task types begin issuing `claude-sonnet-5` primary calls per
    candidate. That is the intended cost, but it is new spend relative to the
    last two weeks of (silently free) cycles. A, B, and C are identical on the
    happy path; they differ only in what happens after a primary failure —
    A adds cheap Haiku retries, B adds same-price Sonnet retries, C adds none.

**Classification: ROOT CAUSE CONFIRMED.**

A second, independent defect is worth naming: `fanout.py`'s blanket
`except Exception` discards a hard configuration error into an unlogged
per-agent `failed` status. The empty-No-Bet fix on this branch makes that
failure visible downstream, but the error text still never reaches a log or
Sentry. That is why this survived two weeks.

---

## PART 9 — Semantic verification (local, no paid call)

The four HQ cases are each held by a named test on this branch.

| Case | Held by |
|---|---|
| 1 — all chains produce nothing → `analysis_incomplete`, not No Bet | `test_no_strategy_input_and_no_ev_is_incomplete`; `test_analysis_incomplete_is_withheld_from_strategy` (never reaches the Strategy Engine, so it cannot become a No Bet) |
| 1 — no completion marker, retryable | `test_recommendation_worker.py:463` and `:508` — `patch_route.call_count == 0`, i.e. `cycle_completed_at` stays NULL and the game stays eligible |
| 2 — usable candidates, none qualify → valid No Bet + marker | `test_usable_strategy_input_is_never_incomplete`; `test_normal_computed_game_still_reaches_strategy`; `test_census_stays_silent_on_a_genuinely_healthy_run` |
| 3 — qualifying candidate → recommendation + marker | `test_recommendation_worker.py:202-213`, the positive path, untouched by the fix and still green |
| 4 — one fails, one survives | `test_partial_chain_with_surviving_strategy_input_is_not_incomplete`; `test_partial_candidate_failure_surfaces_without_hiding_the_survivor` |

The narrowness of the fix is held separately by
`test_ev_present_but_no_ev_per_dollar_is_not_incomplete`: a candidate with no
`american_odds` has no computable EV per dollar, the analysis genuinely ran,
and it must **not** be reported as a failure.

---

## Preserved without modification

`CLE @ TB` product `2026-00001` and `CIN @ HOU` product `2026-00003` were read
only. No recommendation row was created, altered, or deleted in any
environment during this pass.
