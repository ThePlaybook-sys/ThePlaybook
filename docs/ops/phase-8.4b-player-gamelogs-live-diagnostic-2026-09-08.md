# Phase 8.4B — Player Gamelogs Live Diagnostic (2026-09-08)

MANSA HQ directive: "MANSA PHASE 8.4B — PLAYER GAMELOGS LIVE
DIAGNOSTIC" (2026-09-08). Phase 8.4's audit is accepted. Exactly ONE
controlled DEV call was authorized against MySportsFeeds'
`player_gamelogs.json` for player=9999 (Hunter Henry),
season=2025-2026-regular.

**Result: HTTP 400. The endpoint rejected the request — zero bytes
returned, no error body to interpret. Per HQ's own explicit stop
condition ("IF 400/401/403/404: capture the exact safe response/status
and STOP. Do not probe alternative endpoint shapes"), this pass stops
here.** No payload was observed; no context preview can be produced
(that section of HQ's directive was conditioned on success). The risk
flagged in Phase 8.4's own audit — that `player_gamelogs` shares its
`_gamelogs` family shape with `team_gamelogs`, which has twice returned
400 and remains unresolved — is now corroborated by a second, real
400 in the same feed family, not merely a sibling-analogy concern.

---

## 1. Once-only guard result

Reused `activation_run_markers` verbatim with a new dedicated run_key:
`phase-8.4b-player-gamelogs-diagnostic-2026-09-08`. **Proven live
again, not just designed**: setting `RUN_MSF_PLAYER_GAMELOGS_
DIAGNOSTIC=1` produced two overlapping Railway deployments (the same
recurring race this whole arc has repeatedly disclosed), and the guard
held cleanly — the first container (`ea029bfe...`) claimed the marker
and made the one real call; the second, overlapping container
(`da74fbdd...`) hit `409` and logged a clean skip with zero additional
provider calls, confirmed directly in its own deploy log. Verified
directly against Supabase: exactly **one** row exists for this
run_key. All three prior Phase 8.3 marker rows remain untouched.

## 2. HTTP result / latency / size

| Field | Value |
|---|---|
| HTTP status | **400** |
| Elapsed | 0.354 seconds |
| Response size | **0 bytes** — no body was returned to interpret, not even an error-detail JSON |
| Request path | `/nfl/2025-2026-regular/player_gamelogs.json` |
| Request params | `{"player": "9999"}` — exactly the one documented filter, no invented parameters |
| Quota-relevant headers | none present |

## 3. Exact real response shape

**None observed.** The response body was empty (0 bytes) — there is no
shape to report, and none is invented. No `MSF_PLAYER_GAMELOGS_RAW_
CHUNK` log lines were produced (the chunking logic correctly emits zero
chunks for empty content, confirmed by the deploy log showing no such
lines after `MSF_PLAYER_GAMELOGS_DIAGNOSTIC_RESULT`).

## 4. Real game-row count

**Zero — not applicable.** No rows were returned.

## 5. Player identity compatibility

**Cannot be evaluated.** The request itself (player id `9999`, the
project's own established real numeric-id convention) may or may not
be the cause of the 400 — genuinely unknown, since MySportsFeeds
returned no error detail to distinguish "bad parameter value" from
"bad parameter name" from "feed unavailable for this league/season"
from any other rejection reason.

## 6. Game identity compatibility

**Cannot be evaluated** — same reason as §5, no payload to inspect.

## 7. Real stat-field matrix

**Not applicable — no payload.** Nothing here is inferred from Phase
8.3C's sibling `player_stats_totals` findings; that would be exactly
the "do not infer absent fields" HQ explicitly prohibited.

## 8. Participation/snap-count coverage

**Not applicable — no payload.**

## 9. `gamesStarted` reliability

**Not applicable — no payload.**

## 10. Canonical persistence compatibility

**Cannot be evaluated against real data this pass.** Phase 8.4's own
design work (§3-4 of that report) remains the best available reasoning
— `PlayerStatLine`/`persist_player_stats()` were assessed as already
sufficient by analogy to the existing game-scoped architecture — but
this remains unconfirmed against a real gamelog payload, and stays
unconfirmed after this pass.

## 11. Contextual dimensions now supported

**None — unchanged from before this pass.** No real game-level player
data was obtained, so none of Phase 8.4's own mapped dimensions
(weather/opponent/venue/teammate-conditioned performance, recency/
form, usage changes, lineup×role production) move from "would become
possible" to "actually possible." The capability boundary Phase 8.3D
already documented stands exactly as it was: season totals only.

## 12. Unresolved gaps

1. **The real `player_gamelogs` response shape remains completely
   unknown** — this was the entire point of this diagnostic, and it is
   still unanswered after a real, correctly-executed attempt.
2. **Why the request was rejected is unknown.** Candidate explanations,
   none confirmed, none preferred over another without more evidence:
   the `player` filter (confirmed only by a v2.0 NBA-example analogy,
   per Phase 8.4 §3) may not be valid for this NFL v2.1 feed as used;
   the numeric-id value format may be wrong (the only documented
   example uses a name-slug); the feed may require a mandatory
   parameter the SDK's own feed table doesn't declare (the exact
   failure mode already confirmed for sibling `team_gamelogs`, per the
   original 2026-09-03 bake-off); or the feed may simply be
   unavailable on this trial tier/plan for NFL. **None of these has
   been tested or ruled out — per HQ's explicit "do not probe
   alternative endpoint shapes" instruction, none was tested this
   pass.**
3. **The `_gamelogs` family risk flagged in Phase 8.4's own audit is
   now corroborated, not merely analogous** — both real MySportsFeeds
   `_gamelogs`-family endpoints this project has ever called
   (`team_gamelogs`, twice, and now `player_gamelogs`, once) have
   returned 400. This is a real, strengthening pattern worth carrying
   into any future decision about this endpoint family as a whole, not
   just this one player/season combination.

## 13. Service-health result

**No crash, no failed healthcheck, no unplanned incident.** Both
containers (the one that made the real call and the one that hit the
guard's 409) started cleanly and passed their healthchecks immediately
— this pass's exception-safe design handled the real 400 response
exactly as intended (a structured result, not an exception) with
nothing to even exercise the try/except paths beyond normal control
flow. Service confirmed healthy on the current deployment
(`da74fbdd...`, `SUCCESS`). `RUN_MSF_PLAYER_GAMELOGS_DIAGNOSTIC` set
back to `"0"` (`skipDeploys: true`) immediately after the marker claim
was confirmed.

## 14. Recommendation for Phase 8.4C

**Do not retry `player_gamelogs` with a variant parameter shape
without new evidence to justify a specific change** — HQ's own
"no repeated probing" discipline applies as much to a design-only
audit pass as to a live call. Recommend, in order of cheapest-first:

1. **Documentation/support research first, zero provider cost**: check
   MySportsFeeds' own public API documentation (outside this repo,
   requires external access this session may not have) or support
   channel for the exact real v2.1 `player_gamelogs` parameter
   contract, rather than continuing to infer from a v1.x/v2.0-mixed
   SDK feed table and a cross-sport (NBA) example. This is the
   single highest-leverage next step and costs zero provider calls.
2. **If HQ still wants a live retry**, the narrowest next test —
   authorized separately, not assumed — would isolate exactly one
   variable at a time rather than guessing at several simultaneously:
   e.g. a bare `GET /nfl/2025-2026-regular/player_gamelogs.json` with
   *no* filter at all (testing whether the endpoint works unfiltered,
   the same shape that worked for `player_stats_totals` before a team
   filter was added in Phase 8.3C) would isolate whether the `player`
   parameter itself is the problem, independent of its value format.
3. **Given the now-twice-confirmed `_gamelogs` family failure
   pattern**, HQ may reasonably choose to deprioritize this feed
   family entirely in favor of other Phase 8 data gaps (e.g. richer
   `player_stats_totals` coverage across more teams, or the injuries/
   PBP blockers named in Phase 8.4 §6) rather than continuing to spend
   diagnostic passes on an endpoint family with a consistent real
   failure signature.

No workaround was attempted. No alternative endpoint shape was probed.
No player stats were persisted. No staging/production touched.
