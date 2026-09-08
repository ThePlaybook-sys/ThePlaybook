# Phase 8.3B — Player Season-Stats Single-Call Diagnostic (2026-09-08)

MANSA HQ directive: "PHASE 8.3B PLAYER SEASON-STATS SINGLE-CALL
DIAGNOSTIC" (2026-09-08). Phase 8.3A is accepted; this pass is a narrow,
evidence-gathering diagnostic, not an activation rollout. Exactly ONE new
MySportsFeeds player-stats provider request was authorized.

**Result: the one authorized call was made and reached the provider, but
timed out with no HTTP response ever received. Zero usable player-level
evidence was obtained. Per HQ's explicit "no retries... no second request
to confirm the result," no second call was made.** A real code defect in
this pass's own diagnostic hook (an uncaught exception on that timeout)
crashed the container's startup and triggered an automatic Railway
redeploy — that redeploy's own attempt at the hook correctly hit the
`activation_run_markers` guard and skipped, so **only one live request
was ever sent to MySportsFeeds**, matching HQ's "exactly ONE" requirement
even though the outcome is inconclusive.

---

## 1. Files/code inspected

- `/tmp/.../scratchpad/msf_pkg/package/lib/API_v2_0.js` (vendored
  `mysportsfeeds-node` SDK, already extracted from this session's earlier
  work) — confirmed the exact feed definition: `seasonal_player_stats: {
  season: true, endpoint: 'player_stats_totals' }`, no `path` entry (no
  mandatory game/week/date segment), identical shape to
  `seasonal_team_stats` (already confirmed real in Phase 8.3A).
- `API_v1_0.js` — confirmed query params are passed through verbatim as
  the request's querystring (`this.options.qs = params`), no client-side
  validation of filter names beyond the feed-name/format checks.
- `API_v1_1.js`/`API_v2_1.js` — confirmed base URL
  (`https://api.mysportsfeeds.com/v2.1/pull`) and inheritance chain.
- `msf_pkg/package/README.md` — the SDK's own documented usage examples.
  Two relevant, and disclosed with their exact, different scope (see §2):
  a v1.x `cumulative_player_stats` example using `{team: 'dallas-
  cowboys'}`, and a v2.0 `seasonal_player_gamelogs` example using
  `{player: 'stephen-curry'}`. **No v2.x example exists for
  `seasonal_player_stats`/`player_stats_totals` specifically** — disclosed
  as a real gap in the documentation available, not glossed over.
- `docs/ops/phase-8.3-player-team-performance-data-audit-2026-09-08.md`
  §1/§2 — re-confirmed `seasonal_player_stats` had never been called by
  any pass in this project (SCHEMA/SDK ONLY verdict) before this one.
- `apps/sports-intel-layer/app/adapters/providers/mysportsfeeds.py` —
  confirmed the established base-URL/auth provenance and this project's
  own "no undocumented filter" precedent (that file's own `players.json`
  adapter explicitly declined to test an undocumented team filter).
- `apps/sports-intel-layer/app/master_refresh/production_clients.py` —
  read in full to match the existing credential-isolation pattern
  (`MissingCredentialError`/`os.environ.get`, API key read only inside a
  dedicated `build_*` function, never in `main.py`).
- `apps/sports-intel-layer/tests/test_environment_safety.py` — confirmed
  `main.py`'s forbidden-credential-names test does not need updating
  (the pattern of reading `MYSPORTSFEEDS_API_KEY` only inside
  `production_clients.py`, never in `main.py`, already satisfies that
  test's structural check without adding the name to its list, matching
  every prior MSF diagnostic pass).
- Prior Phase 8.2 diagnostic commits (`699b8fe`, `9a6d7d7`) via `git
  show` — confirmed the exact Basic-auth construction (`password =
  "MYSPORTSFEEDS"` literal) and the deploy/verify/revert shape to reuse.
- Live DEV `activation_run_markers` table (Supabase MCP) — confirmed
  empty of this pass's run_key before the call, and its state after.

## 2. Exact request design

| Field | Value | Provenance |
|---|---|---|
| SDK feed key | `seasonal_player_stats` | `API_v2_0.js` feed table |
| Endpoint/path | `/nfl/2025-2026-regular/player_stats_totals.json` | Same table (`endpoint: 'player_stats_totals'`), season format matches every real capture this project has made |
| Season | `2025-2026-regular` (completed prior season) | Chosen over the current `2026-2027-regular` season because Phase 8.3A's own real team-level data proved the current season is genuinely all-zero (not started) — prior season maximizes the chance of a meaningful (non-zero) result in this one call |
| Team/player filter | `team=NE` | SDK README's own documented usage example for the ancestor v1.x `cumulative_player_stats` feed (same "player-stats-totals" family) — **disclosed as inferred by family analogy, not a v2.x-confirmed example**; whether v2.1 honors, ignores, or rejects it was exactly the open question this call was meant to answer |
| Expected response shape (per SDK/schema) | Unknown/undocumented in the vendored SDK — inferred by analogy to the real, confirmed `seasonal_team_stats` shape (`{lastUpdatedOn, teamStatsTotals: [...], references}`) as `{lastUpdatedOn, playerStatsTotals: [...], references}` | Inference only, explicitly never confirmed — this is precisely what "do not treat SDK/schema presence as proof" warns against, and this call could not resolve it either way |
| Pagination possible? | Unknown — never observed | The call never returned a response |
| Provider-call cost/credit implications visible | None observed — no MySportsFeeds-specific quota/rate-limit headers were ever captured (no response was received to have headers) | N/A this pass |
| `activation_run_markers` run_key | `phase-8.3b-player-stats-diagnostic-2026-09-08` | New, dedicated to this pass, distinct from Phase 8.3A's `phase-8.3a-team-season-stats-activation-2026-09-08` |
| Target selection reasoning | NE chosen over SEA/BUF: of the three already-identity-resolved candidates, NE has the deepest existing real evidence to cross-check against (17 real `players`/`roster_memberships` rows and 17 real named `lineup` slots spanning QB/RB/WR/TE/OL/DL/LB/DB/K from Phase 8.2) | — |

## 3. Activation guard / run_key

Reused Phase 8.3A's `activation_run_markers` table verbatim — no second
idempotency mechanism was created, per HQ's explicit instruction. New
dedicated `run_key`: `phase-8.3b-player-stats-diagnostic-2026-09-08`.

**The guard worked exactly as designed, twice over in this one pass:**
1. The first container to boot with `RUN_MSF_PLAYER_STATS_DIAGNOSTIC=1`
   claimed the run_key at `2026-09-08 17:57:35 UTC` and proceeded to make
   the real call.
2. That container crashed (see §4) and Railway automatically redeployed
   a replacement. The replacement container's own copy of the hook also
   ran (same env var), attempted to claim the same run_key, got `409`,
   and correctly logged a clean skip with **zero** provider calls —
   confirmed directly from that container's own deploy log.

Verified directly against Supabase: exactly **one** row exists in
`activation_run_markers` for this run_key — the guard did not produce a
duplicate marker despite two containers racing for it.

## 4. Provider call count

**Exactly one real MySportsFeeds request was sent.** Confirmed two ways:
(a) `activation_run_markers` holds exactly one row for this run_key, and
the code path only reaches the live `client.get()` call after a
successful (non-409) marker claim; (b) the second (auto-redeployed)
container's own deploy log explicitly shows it never reached the
`client.get()` call at all — it returned immediately after the 409.

## 5. HTTP result

**No HTTP response was ever received.** The request reached the
provider's connection layer (a real TCP/TLS connection was established —
this is not a local pre-network failure) and then received no response
headers within the client's 30.0s timeout. `httpx.ReadTimeout` was raised
at the network layer, wrapped by `httpx` into the same, with a traceback
captured in the Railway deploy log at `2026-09-08T17:58:15.703Z` (roughly
30s after the request began around `17:57:45Z`, allowing for connection
setup time after the `17:57:35Z` container start).

**This is a code-level operational failure this pass introduced, disclosed
plainly:** `run_msf_player_stats_diagnostic()`'s call to `client.get(...)`
was not wrapped in a `try/except`, unlike every persistence function in
this codebase (`PersistenceError`, `TeamSeasonStatsPersistenceError`,
etc., all catch and convert exceptions before they can escape). The
uncaught `httpx.ReadTimeout` propagated out of the FastAPI `@app.
on_event("startup")` handler, which Starlette treats as a fatal lifespan
failure (`ERROR: Application startup failed. Exiting.`) — the entire
container failed its healthcheck three times (`Attempt #1/2/3 failed with
service unavailable`) before Railway automatically replaced it with a new
deployment. **No second outbound call to MySportsFeeds was made as a
result of this crash-and-redeploy cycle** — only the guard's own fast,
local 409 check ran in the replacement container, confirmed in §4.

Per HQ's own rule — "no retries unless the request fails solely because
of a clearly local coding/transport mistake before reaching the
provider" — this does **not** qualify for a retry: the coding mistake
(missing exception handling) occurred only in how the timeout was
*handled*, not in whether the request *reached* the provider. The request
itself was correctly formed and dispatched; the provider (or a
network intermediary) simply never responded within 30 seconds. No
second request was made.

## 6. Raw capture location

**No raw response body exists — there was nothing to capture.** The
`response` variable inside `run_msf_player_stats_diagnostic()` was never
assigned; the function's own structured-evidence return value was never
reached. The only real artifact from this call is the Railway deploy
log's own exception traceback (deployment `75344ed8-6be4-4902-8c1c-
819e3917c338`, `2026-09-08T17:58:15.7Z`, ending in `httpcore.ReadTimeout`
→ `httpx.ReadTimeout` → `ERROR: Application startup failed. Exiting.`),
quoted verbatim in §5. Request timestamp: the container started at
`2026-09-08T17:57:34.33Z`; the request would have been dispatched within
the following ~1 second (immediately after the fast Supabase marker
claim, confirmed at `17:57:35.127Z`).

## 7. Player scope returned

**None.** Zero players, zero rows, zero bytes of usable payload.

## 8. Confirmed-real player field matrix

Every row is **D. UNKNOWN** — the call produced no data to classify as A
(confirmed real), B (present but empty/zero), or C (schema/SDK only
beyond what was already known before this pass). Nothing here regresses
or advances past the 2026-09-08 audit's own SCHEMA/SDK ONLY verdict for
every player performance field.

| Category | Status |
|---|---|
| Identity (player id, name, team, position) | D. UNKNOWN this call — separately confirmed real via `players.json` (Phase 8.2), unaffected by this pass |
| Participation/usage (games played/started, snaps, offense/defense/special-teams snaps) | D. UNKNOWN |
| Passing (attempts, completions, pct, yards, TDs, INTs, sacks, rating) | D. UNKNOWN |
| Rushing (carries, yards, average, TDs, 1st downs) | D. UNKNOWN |
| Receiving (targets, receptions, yards, average, TDs, 1st downs) | D. UNKNOWN |
| Defense (tackles, assists, sacks, TFL, INTs, passes defended, forced fumbles, recoveries) | D. UNKNOWN |
| Special teams (kick/punt returns, kicking, punting) | D. UNKNOWN |
| Other/unanticipated fields | D. UNKNOWN |

## 9. Fields absent/empty/unknown

All of §8 is UNKNOWN, not absent and not confirmed empty — HQ's own
framework explicitly warns against converting "HTTP error"/no-response
into the same conclusion as a confirmed absence or a confirmed
empty/zero value. This pass makes no such conversion: nothing here is
classified C (schema/SDK only) or B (present but empty) — those would
both require having actually seen the payload, which never happened.

## 10. Role coverage observed

**None observed.** No claim of QB/RB/WR/TE/OL/DL/LB/DB/K/P/return-
specialist support can be made from this call. NE's real roster (Phase
8.2) spans all of these positions, so a successful response *would* have
been well-positioned to test broad role coverage in one shot — but no
response arrived to test it against.

## 11. Canonical schema compatibility

Cannot be evaluated against real data this pass — no payload exists to
compare against Phase 8.3A's `player_stats` schema. Reasoning that *can*
be stated without new evidence, carried forward from Phase 8.3A's own
design work: `player_stats.game_id` is already nullable, `season_id`
already exists and already FKs to `seasons`, and the `stats` column is
unconstrained `jsonb` (would preserve whatever real shape a future
successful call returns, exactly as `team_stats.stats` already does for
team-level data). Whether the *typed* extension columns question even
applies depends on a schema this project doesn't have (no typed player-
stat columns exist yet, only `jsonb`) — so item 4 of HQ's compatibility
checklist doesn't currently apply. No migration was performed or is
proposed this pass.

## 12. Whether any schema change is required

**Cannot be determined — no real player-stats payload has ever been
observed by this project, before or after this pass.** Phase 8.3A's
schema widening (nullable `game_id`, new `season_id`) was designed
generically enough to plausibly fit a season-aggregate player payload by
analogy to the team-level shape, but this remains an inference, not a
confirmed fit, until a real payload is seen.

## 13. MANSA dimensions legitimately unlocked

**None.** This pass confirmed zero new real fields, so the "MANSA
Intelligence Implication" analysis from the original directive is
unchanged from the 2026-09-08 audit's own conclusion: no player-level
comparison (season performance, usage, role, vs. opponent, vs.
teammates, vs. weather, vs. venue, vs. market, recency/form) is
technically supportable yet. Team-level season-aggregate comparisons
(Phase 8.3A's own real, persisted data) remain the only real intelligence
surface this arc has actually unlocked so far.

## 14. What remains impossible

Everything the original audit already named as impossible remains
impossible: all player-level performance comparisons, since zero
player-level performance fields have been confirmed real from any
MySportsFeeds endpoint at any point in this project's history — this
pass's timeout does not change that baseline, it only fails to improve
on it.

## 15. Quota/cost impact

**Unknown, and likely negligible.** No response headers were ever
received (nothing to inspect for `x-requests-remaining`-style headers,
and this project has already flagged elsewhere that trusting an
unverified vendor header name is fragile regardless). A single request
that timed out client-side may or may not have been fully processed
server-side by MySportsFeeds — this is unknowable from the client side.
No purchase, tier change, or recurring polling was initiated.

## 16. Files changed

**Permanent:** none. No schema, no persistence code, no canonical data.

**Temporary (built, run, then fully reverted — this pass persisted zero
real data, so unlike every prior activation pass there is nothing to
leave behind beyond the guard's own marker row):**
- `apps/sports-intel-layer/app/diagnostics/__init__.py`,
  `msf_player_stats_diagnostic.py` (added, then deleted)
- `apps/sports-intel-layer/app/main.py` (temporary startup hook added,
  then removed)
- `apps/sports-intel-layer/app/master_refresh/production_clients.py`
  (temporary `build_msf_player_stats_diagnostic_client()` and its base-
  URL constant added, then removed)

**Real, permanent database row created by this pass:** one
`activation_run_markers` row (`run_key =
phase-8.3b-player-stats-diagnostic-2026-09-08`), left in place per this
project's own "temporary code, but real data/records persist" and
"never delete real provenance" precedents — it is accurate, honest
provenance of this pass's one real attempted call, timeout included.

## 17. Tests performed

- Full `apps/sports-intel-layer` suite before the live call: 740/740
  passing (no new tests added or needed — this pass's temporary code
  followed the established "diagnostics don't get dedicated unit tests"
  precedent from every prior MSF diagnostic pass).
- Offline `respx`-mocked smoke tests (not committed) of the diagnostic
  module before deployment: verified both the happy-path (200 response,
  guard claimed, one call made) and the guard's 409-skip path (zero
  calls made) — both worked correctly in isolation. **Neither test
  exercised a network timeout**, which is exactly the gap that let the
  uncaught-exception bug through to a live deploy; flagged as a real
  process lesson in §19.
- Full suite again after reverting the temporary code: 740/740 passing,
  zero regressions.

## 18. Deployment/environment impact

DEV only (`sports-intel-layer` service). Two deployments were created by
this pass's one `set-variables` call: `75344ed8` (made the real call,
crashed on the unhandled timeout, 3 failed healthchecks) and its
automatic Railway replacement `3e8970b6` (SUCCESS, correctly skipped a
second call). The service is confirmed stable and healthy on `3e8970b6`
as of this report. `RUN_MSF_PLAYER_STATS_DIAGNOSTIC` set back to `"0"`
(`skipDeploys: true`). No staging/production touched.

## 19. Unresolved risks

1. **The core question this pass was meant to answer remains
   unanswered.** Does `player_stats_totals` return legitimate player-
   level data? Still unknown after two real attempts across this
   project's history (this pass's timeout, and the original 2026-09-08
   audit's own observation that the feed had never been called at all).
2. **A real defect in this pass's own diagnostic code**: the live
   provider call was not wrapped in exception handling, so a timeout
   crashed the whole container's startup instead of being caught and
   logged as a clean, informative result. Every other real persistence/
   fetch path in this codebase (`PersistenceError`,
   `TeamSeasonStatsPersistenceError`, `CronDispatchError`, etc.) catches
   and converts network failures into a structured, non-fatal outcome —
   this diagnostic should have followed that same convention and did
   not. Concretely fixable for a future authorized pass: wrap the
   `client.get()` call in `try/except (httpx.TimeoutException,
   httpx.HTTPError)` and return a structured `{"http_status": None,
   "error": "timeout"}`-style result instead of letting the exception
   propagate into the FastAPI lifespan.
3. **A 30.0s client timeout may simply be too short for this endpoint**,
   the same lesson Phase 8.2's own Players Identity Diagnostic #1→#2
   evolution already taught for the whole-league `/nfl/players.json`
   feed (30s → 120s fixed a genuine timeout there). This call was
   filtered to one team and expected to be small, but the real result
   suggests either the filter wasn't honored server-side (making this a
   whole-league-sized query in practice) or the endpoint is simply slow
   regardless of scope — genuinely unknown which, per §D of the
   classification framework.
4. Whether the `team=NE` filter is even a valid v2.1 parameter for this
   specific feed remains unresolved — the timeout gives no signal either
   way (a rejected/invalid filter would more likely have produced a fast
   4xx, which also didn't happen, weakly suggesting the request was at
   least accepted for processing, but this is not confirmed).

## 20. Recommendation for the next Phase 8.3 step

A follow-up single-call diagnostic, if HQ authorizes one, should change
exactly two things learned from this pass's real failure, and nothing
else about scope: (a) wrap the live call in proper exception handling so
a timeout produces a clean, informative diagnostic result instead of a
crashed container, and (b) raise the client timeout closer to the 120s
value Phase 8.2 already proved necessary for at least one other
MySportsFeeds v2.1 feed, rather than assuming a team-filtered request is
automatically fast. No change to target (NE), season
(2025-2026-regular), or the disclosed-uncertain `team` filter is
recommended without new evidence — those design choices were reasoned
and disclosed, not the cause of this pass's failure.

STOP after reporting, per HQ's instruction. No player-stat activation or
second provider request was made without authorization.
