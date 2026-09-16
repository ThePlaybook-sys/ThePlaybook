# Backend Sentry Coverage + Alerting Audit (2026-09-16)

**Directive:** MANSA HQ — "BACKEND SENTRY COVERAGE + ALERTING AUDIT." Audit first. No
intentional crash. No provider calls. No LLM calls.

**Compliance:** zero provider calls, zero LLM calls, nothing crashed on purpose, nothing
changed. All findings are from reading code, Railway config/variables/logs, and deployment
status. Read-only throughout. No secret value was read or displayed — Railway returns variable
**names only** to this session (`valuesRedacted: true`), which is exactly what a presence check
needs.

---

## Headline

**Every always-on HTTP service is covered. Every cron service has no Sentry at all — no SDK in
its code path and no `SENTRY_DSN` in its environment. That is 9 of 14 backend services, and it
includes every scheduled job in the schedule → odds → recommendation → grading pipeline.**

And this is not hypothetical. **Three cron services are CRASHED right now** and have been failing
silently:

| Service | State | Since | Cause |
|---|---|---|---|
| `cron-weather-worker` | **CRASHED** | failing **every 15 min** | `CRON_DISPATCH_BASE_URL` is missing its `https://` scheme |
| `cron-news-worker` | **CRASHED** | last failed 16:05 UTC | transport failure to `sports-intel-layer-dev` (empty error detail) |
| `cron-master-refresh` | **CRASHED** | ~12 h (known) | stale branch `claude/new-session-fqsad5` + invalid sentinel target |

`cron-weather-worker` runs `*/15 * * * *`, so it is producing roughly **96 crashed deployments a
day**, and **not one of them can reach Sentry**. If an alert rule exists and worked, this would
already have paged Mac today. That is the cheapest possible confirmation of the gap and it costs
nothing to check — see §Alerting.

---

## Per-service findings

Legend: **SDK** = is `sentry_sdk.init()` on the code path the service actually runs?
**DSN** = is `SENTRY_DSN` present in the deployed dev environment?

| Service | Runs | SDK | DSN | Coverage |
|---|---|---|---|---|
| `sports-intel-layer` | `app.main` (FastAPI) | **YES** | **YES** | HTTP unhandled only |
| `ai-orchestrator` | `app.main` (FastAPI) | **YES** | **YES** | HTTP unhandled only |
| `api-gateway` | `app.main` (FastAPI) | **YES** | **YES** | HTTP unhandled only |
| `worker-scheduled` | `apps/workers/app.main` (FastAPI) | **YES** | **YES** | HTTP unhandled only |
| `worker-market-monitor` | `apps/workers/app.main` (FastAPI) | **YES** | **YES** | HTTP unhandled only |
| `cron-schedule-refresh` | `python -m app.cron_dispatch` | **NO** | **NO** | **NONE** |
| `cron-odds-worker` | `python -m app.cron_dispatch` | **NO** | **NO** | **NONE** |
| `cron-postgame-grading` | `python -m app.cron_dispatch` | **NO** | **NO** | **NONE** |
| `cron-recommendation-worker` | `python -m app.cron_dispatch` | **NO** | **NO** | **NONE** |
| `cron-adaptive-weighting` | `python -m app.cron_dispatch` | **NO** | **NO** | **NONE** |
| `cron-msf-postgame` | `python -m app.cron_dispatch` | **NO** | **NO** | **NONE** |
| `cron-weather-worker` | `python -m app.cron_dispatch` | **NO** | **NO** | **NONE** — and CRASHED |
| `cron-news-worker` | `python -m app.cron_dispatch` | **NO** | **NO** | **NONE** — and CRASHED |
| `cron-master-refresh` | `python -m app.cron_dispatch` | **NO** | **NO** | **NONE** — and CRASHED |

**The root cause is one line of deployment topology.** `apps/workers/app/main.py` *does* call
`sentry_sdk.init()` — but the cron services do not run it. Their start command is
`python -m app.cron_dispatch`, a different entry point in the same image, and
`apps/workers/app/cron_dispatch.py` contains **zero** references to Sentry (verified by direct
grep: count = 0). The SDK is installed in the image (`sentry-sdk[fastapi]==2.19.2` in
`apps/workers/requirements.txt`) and simply never initialized.

So the coverage boundary is not "which app" — it is **"FastAPI entry point vs. cron entry
point"**, and every scheduled job in the autonomous pipeline is on the wrong side of it.

---

## The seven questions

### 1. Is the Sentry SDK initialized in the code path?

**FastAPI services: yes.** Identical block in all four `main.py` files:

```python
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    send_default_pii=False,
    environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev"),
)
```

**Cron services: no.** `cron_dispatch.py` never imports or initializes `sentry_sdk`.

Note `dsn=os.environ.get("SENTRY_DSN")` — `.get`, not `[...]`. A missing DSN yields `None`,
which the SDK treats as **disabled, silently**. That is the right call for local development, but
it means a service with the SDK and no DSN looks healthy and reports nothing, with no startup
warning.

### 2. Is `SENTRY_DSN` present in the deployed environment?

Present on all 5 always-on services. **Absent on all 9 cron services.** (Value never read or
displayed — Railway returns names only to this session.)

For the crons this is belt *and* braces failing together: even if `cron_dispatch.py` were
instrumented tomorrow, it would still report nothing until the variable is added.

### 3. Are unhandled exceptions captured?

**In an HTTP request handler on a FastAPI service: yes.** `sentry-sdk[fastapi]` 2.19.2
auto-enables the FastAPI/Starlette integrations, so an exception escaping a route handler is
captured before the 500 is returned.

**Anywhere in a cron process: no.** Without `init()`, the SDK installs no `sys.excepthook`, so
even a bare traceback exits silently as far as Sentry is concerned.

### 4. Are explicit worker/cron failures captured?

**No — nowhere, on any service.** This is the finding I would rank second after the cron gap,
because it is invisible from the outside.

A direct grep across all four apps for `capture_exception`, `capture_message` and `set_tag`
returns **zero hits**. There is no explicit capture anywhere in the codebase.

That matters more than it sounds, because **this project's workers are deliberately designed not
to raise.** `run_odds_worker`'s own docstring: *"Always returns an `OddsWorkerResult`, never
raises — same finite-job shape as `run_master_refresh`."* A failure becomes
`status="failed"` / `failures=[...]` in a **200 OK** response body.

The consequence is precise: **a worker can fail completely, every cycle, and Sentry will never
see an event**, because nothing ever threw. The recent odds credit leak is a perfect example —
12 consecutive cycles returning `partial` with 20 unresolved events each, entirely invisible to
error monitoring. It was caught by reading a ledger, not by an alert.

`cron_dispatch` has the same shape by design: it catches `CronDispatchError`, logs
`_logger.error(...)`, and `return 1`. A non-zero exit makes Railway mark the deployment CRASHED —
but no exception ever propagates, and no Sentry client exists to capture it if one did.

### 5. Background-task exceptions, or only HTTP request failures?

**Only HTTP request failures — but there are no background tasks to miss.** A grep for
`BackgroundTasks`, `asyncio.create_task`, `ensure_future` and `threading.Thread` across all four
apps returns **zero hits**. Every unit of work is either synchronous inside a request, or a
finite cron process.

So there is no fire-and-forget blind spot today. The blind spot is the cron process *itself*,
which is the whole of §1–§4 above.

### 6. Useful environment / release / service tags?

**Partial. One of three.**

| Tag | Status |
|---|---|
| `environment` | **SET** — from `RAILWAY_ENVIRONMENT_NAME`, defaulting to `dev`. Correct, and deliberately so: the code comment notes that without it the SDK tags everything `production` regardless of origin. |
| `release` | **NOT SET** — no `release=` argument anywhere, no `SENTRY_RELEASE` variable on any service. So no event can be attributed to a commit or deploy. |
| service identity | **NOT SET** — no `server_name` override and no `set_tag("service", …)`. |

The service gap is the practical one. **All four backend services share a single Sentry project
and have no service tag**, so events from `api-gateway` and `sports-intel-layer` are
distinguishable only by transaction name or stack trace. Sentry's default `server_name` is the
container hostname, which on Railway is an opaque container id, not a service name. Filtering or
alerting *per service* is therefore not currently possible — which directly limits the "any
backend services not covered by that alert" question below.

No `traces_sample_rate` is set either, so performance monitoring is off. That is a reasonable
cost decision, not a defect, and is noted only for completeness.

### 7. Are Railway CRASHED / startup failures visible to Sentry?

**No. A startup failure is structurally invisible, and this is by construction, not by accident.**

Three distinct pre-init windows exist:

1. **Import-time failures** — a bad import, a syntax error, a missing module. The process dies
   before `sentry_sdk.init()` is ever reached.
2. **`sports-intel-layer` specifically runs a guard *before* init, deliberately.**
   `assert_demo_isolation(...)` is called first, with the comment: *"Deliberately checked before
   `sentry_sdk.init` and app construction — a demo isolation violation must prevent the process
   from ever reaching a state where it could serve a request or emit telemetry."* That is the
   right security decision and I would not change it. It does mean the single most severe startup
   failure this service can have is the one Sentry can never report.
3. **Missing required env vars at module scope** — e.g. `cron_dispatch`'s
   `os.environ["CRON_DISPATCH_TARGET"]` raises `KeyError` immediately.

**Empirically confirmed today**, which is better than reasoning about it: `cron-weather-worker`
has produced a CRASHED deployment every 15 minutes, and the failure is a plain configuration
error — `CRON_DISPATCH_BASE_URL` set to `sports-intel-layer.railway.internal` with **no
`https://` scheme**, so every dispatch dies with *"Request URL is missing an 'http://' or
'https://' protocol."* It has been doing this unnoticed. Railway knows. Sentry does not.

---

## Alerting

### Can this session inspect Sentry alert rules?

**No, and I will not guess.** There is no Sentry MCP server, API token, or CLI available here —
confirmed by an explicit tool search for Sentry tooling, which returned no match. Available
tooling covers Railway, Supabase, GitHub and ClickUp only.

Therefore, stated plainly:

| Question | Answer |
|---|---|
| Alert rule present: YES/NO | **CANNOT DETERMINE FROM THIS SESSION** |
| Severity / event conditions | **CANNOT DETERMINE** |
| Notification channel | **CANNOT DETERMINE** |
| Delivery ever verified | **CANNOT DETERMINE** — no evidence of a verification exists anywhere in the repo, `PROGRESS.md`, or `docs/ops/` |
| Services not covered | **Determinable and answered below** |

### Services that no alert rule could possibly cover

This part does **not** depend on the dashboard, because it is a property of the senders:

**All 9 cron services are uncoverable by any alert rule, no matter how it is configured**, because
they emit no events at all. An alert rule can only fire on an event that arrives.

That is the entire scheduled pipeline: schedule refresh → odds → recommendation → grading, plus
msf-postgame, adaptive-weighting, weather and news.

Additionally, **even for the 5 covered services, a rule cannot be scoped per service** today,
because no service tag is emitted (§6).

### The smallest manual check — and a cheaper one first

**Cheapest check, costs nothing, no dashboard needed (do this first):**

> Mac — did you receive *any* Sentry notification today about `cron-weather-worker`,
> `cron-news-worker`, or `cron-master-refresh` failing?

Given those three have been crashing repeatedly for hours, the answer is almost certainly no —
and a "no" confirms the gap immediately, because it is a live natural experiment already running.
A surprising "yes" would mean an alerting path exists that this audit could not see, which is
worth knowing before anything is changed.

**Smallest dashboard check, four clicks, if you want the configuration itself:**

1. **sentry.io → Alerts** (project selector set to the backend project). Is there **any** rule
   listed? Note its type: *Issue Alert* (fires on errors) vs *Metric Alert* (fires on thresholds).
   Only an Issue Alert will fire on a backend exception.
2. **Open the rule → "When"** — is the condition `A new issue is created`, `The issue changes
   state`, or a frequency threshold? A rule that only fires on a *new* issue will stay silent for
   a recurring, already-seen error.
3. **Open the rule → "If" (filters)** — check for an **`environment` filter**. This is the most
   common silent failure: a rule scoped to `environment: production` will never fire for our
   events, because every backend service tags itself `dev` from `RAILWAY_ENVIRONMENT_NAME`. Worth
   checking before anything else.
4. **Open the rule → "Then" (actions)** — which channel? Email to a member, a team, Slack,
   PagerDuty? Then confirm your own **Settings → Notifications** does not have that category
   muted.

**Delivery history** (proves it has ever actually worked): open the rule and look for
*"Alert triggered"* entries, or check **Issues → any issue → Activity** for notification records.

---

## Proposed end-to-end test — ONE test, not executed

**Not run. Awaiting authorization, per the directive.**

### The mechanism already exists

Every FastAPI service already ships a dev-only `/sentry-debug` route, mounted behind
`if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":`:

```python
@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0
```

Nothing needs to be written, deployed, or reverted. This route exists for exactly this purpose
and is already live on dev.

### The test

| | |
|---|---|
| **Target** | `sports-intel-layer`, **dev** — the service most central to the pipeline, currently SUCCESS/online on commit `0c7fb18` |
| **Action** | **one** HTTP GET to `https://sports-intel-layer-dev.up.railway.app/sentry-debug` |
| **Chain proven** | `ZeroDivisionError` → FastAPI integration captures → event reaches Sentry tagged `environment=dev` → alert rule evaluates → notification delivered to Mac |

**Success criteria, in order — each one isolates a different link:**

1. HTTP **500** returned → the exception really was raised and really was unhandled.
2. Event appears in **Sentry → Issues** within ~1 minute, as `ZeroDivisionError`, tagged
   `environment: dev` → **DSN is valid and ingestion works**.
3. **Mac receives a notification** → the alert rule exists, matches, and delivers.

If it stops at 2, the DSN and SDK are fine and the problem is purely alerting configuration —
which is precisely the thing this session cannot inspect, so the test is designed to localize
that.

**Why this is safe:**

- **No crash.** The exception is raised inside a request handler; uvicorn returns 500 for that one
  request and the process is unaffected. The service stays online. This is not "intentionally
  crashing a service" — the directive's prohibition is respected.
- **No state change.** The handler divides by zero before touching anything. No database write, no
  provider call, no LLM call, no credit spent.
- **No cost.** Zero provider credits.
- **Dev only.** The route is not mounted in staging, production, or demo.
- **Nothing to roll back.** The only artifact is one Sentry event, which can be resolved or
  ignored in the UI.

**What it proves, and what it deliberately does not:**

It proves the **HTTP-unhandled-exception path on one always-on service**, end to end through
notification. That is one of the seven areas audited.

It does **not** prove — and cannot, because the capability does not exist — cron coverage (§1–§2),
explicit worker-failure capture (§4), or startup-failure visibility (§7). Those need code changes
before any test could pass, so **a green result here must not be read as "backend monitoring is
covered."** It means the one path that is wired is genuinely wired.

---

## Recommended remediation (proposed, not applied)

In dependency order, smallest first. **None of this was done this pass.**

1. **Add `SENTRY_DSN` to the 9 cron services** — one Railway variable each. Necessary but not
   sufficient on its own, since `cron_dispatch.py` still never initializes the SDK.
2. **Initialize Sentry in `cron_dispatch.py`** and explicitly `capture_exception` /
   `capture_message` on the `CronDispatchError` path before `return 1`. Roughly ten lines. This is
   the single highest-value change in this report: it converts 9 blind services into reporting
   ones and would have surfaced the weather-worker misconfiguration on its first tick.
3. **Capture explicit worker failures.** Because workers deliberately never raise (§4), a
   `status="failed"` result needs an explicit `capture_message` with the failure list attached, or
   error monitoring will keep missing every real failure the pipeline has.
4. **Add a `service` tag and a `release`** (§6), so alerts can be scoped per service and events
   attributed to a commit.
5. **Fix `cron-weather-worker`'s `CRON_DISPATCH_BASE_URL`** — it is missing `https://`. A
   one-variable fix for a job that has failed ~96 times today. **Reported, not fixed** — out of
   scope for an audit directive, and it needs its own authorization.

---

## What was NOT done

- **Zero provider calls. Zero LLM calls.**
- **Nothing crashed intentionally.** The three CRASHED crons were already crashing; this session
  observed them, and did not trigger or touch them.
- **The `/sentry-debug` test was NOT executed.**
- **No configuration changed.** No Railway variable set, no cron altered, no code modified, no
  deploy triggered.
- **No secret value read or displayed.** Railway returns variable names only; presence was all
  that was checked and all that was reported.
- **No guesses about Sentry alert configuration.** Where this session cannot see, it says so.
- **No unrelated repairs**, including the weather-worker URL scheme, `cron-master-refresh`'s stale
  branch, and `cron-news-worker`'s transport failure — all reported, none fixed.
