# Phase 8.4D — Unfiltered Player Gamelogs Diagnostic (2026-09-08)

MANSA HQ directive: "MANSA PHASE 8.4D — UNFILTERED PLAYER GAMELOGS
DIAGNOSTIC" (2026-09-08). Phase 8.4C is accepted. Exactly ONE
controlled DEV call was authorized: `GET /nfl/2025-2026-regular/
player_gamelogs.json`, no query parameters — isolating whether the
`seasonal_player_gamelogs` family fails regardless of filter, per
Phase 8.4C's own forensic recommendation.

## STOP AND REPORT

**1. Once-only guard result.** Clean. New dedicated run_key
(`phase-8.4d-player-gamelogs-unfiltered-diagnostic-2026-09-08`)
claimed exactly once in `activation_run_markers`
(`completed_at 2026-09-08 21:59:15.499843+00`, confirmed by direct
Supabase query). An overlapping Railway deployment
(`0ba43cdc-cdc3-4e71-b164-5f68071ae0b2`) booted ~59s later, attempted
the same claim, hit `409`, and its own deploy log shows a clean
`skipped: true, provider_call_made: false` result — zero additional
provider calls. Exactly one real MySportsFeeds request was made across
every container that ran this pass's code.

**2. HTTP status.** `400`.

**3. Latency/size.** `0.215s` elapsed. `response_size_bytes: 0` — an
empty body, no error text returned by the provider.

**4. Full-capture result.** N/A — there was no body to capture. The
chunked-logging path (`chunk_for_logging`) was never triggered because
`response_body_text` was empty/falsy; this is the expected, safe
behavior of that code path (matches Phase 8.4B's own 0-byte 400,
where the same thing happened), not a capture failure.

**5. Real payload shape if successful.** N/A — no payload was
returned.

**6. Player/game identity compatibility.** N/A — cannot be assessed;
no rows exist to inspect.

**7. Game-level stats/usage coverage.** N/A — cannot be assessed.

**8. Hunter Henry context preview.** N/A — the unfiltered payload
contained zero bytes, so player id 9999 (or any player) cannot be
located in it. No context preview is possible this pass. This is
disclosed honestly per HQ's own strict rule rather than fabricated or
inferred from Phase 8.3C's sibling `player_stats_totals` data.

**9. Canonical persistence compatibility.** N/A — cannot be assessed
without a real row shape. `PlayerStatLine`/`persist_player_stats`
remain unexercised against this feed; nothing about their sufficiency
changed this pass.

**10. Interpretation of the gamelogs family.** This confirms
**Outcome B** from HQ's own framing: the `seasonal_player_gamelogs`
feed rejects the request even with **zero query parameters and zero
filters of any kind**. Combined with the full evidence chain now
built across this arc —
`team_gamelogs` failed both unfiltered (original 2026-09-03 bake-off
Run 1) and with a documented-style slug filter (Run 2, `a14a116`);
`player_gamelogs` failed with a numeric player filter (Phase 8.4B,
`player=9999`) and now fails completely unfiltered (this pass) — the
`_gamelogs` endpoint family has failed **every one of four independent
real requests** across two endpoints and every parameter shape tried
(none, slug, numeric id). The near-instant `0.215s` response time
(consistent with Phase 8.4B's `0.354s` and both original
`team_gamelogs` 400s) further suggests this is a fast, contract-level
rejection — not a slow, filter-dependent processing path — reached
before any real query execution, i.e. a request-shape/contract or
account-tier gate, not a data-availability issue. This project now has
**zero confirmed successful calls to any `_gamelogs`-family endpoint**,
against one fully successful non-gamelog player feed
(`player_stats_totals`, Phase 8.3C).

**11. Remaining uncertainty.** The *specific* mechanism is still
unknown and cannot be resolved by further guessing, per HQ's own
instruction: whether this is (a) a request-contract detail this
project hasn't yet identified (e.g. a mandatory date/week/game
path segment or parameter not documented in the vendored SDK's own
feed table), (b) an account/plan-tier restriction on the `_gamelogs`
feed family specifically (this DEV credential's tier may not include
it while it includes `player_stats_totals`), or (c) something else
entirely. No live evidence collected so far distinguishes between
these.

**12. Recommendation for next Phase 8 step.** Per HQ's own explicit
instruction 8: **recommend ZERO additional live probing of the
`_gamelogs` family** until either (a) authoritative MySportsFeeds
documentation or support directly clarifies the real request contract
for `seasonal_player_gamelogs`/`seasonal_team_gamelogs`, or (b)
another already-authorized MSF feed can provide equivalent game-level
player data. Do not keep guessing request shapes — four independent
attempts across two endpoints and three parameter shapes have all
failed identically. If game-level (per-game, not season-total) player
data is still needed for Phase 8's roadmap, the productive next step
is external research (MSF docs/support, zero provider cost) or
evaluating whether an already-authorized feed can substitute, not a
fifth live guess.

## Execution safety (as designed and verified)

Reused `activation_run_markers` with a new dedicated run_key. 120.0s
timeout (unused — response returned in 0.215s). Every network call
(marker claim, live MSF request) wrapped exception-safe; the `main.py`
hook itself added one more outer guard. No automatic retry — none
occurred. Safe across the overlapping Railway deployment this pass
actually encountered (confirmed above). No credentials logged, in
whole or in part.

## Post-diagnostic actions

- Activation flag (`RUN_MSF_PLAYER_GAMELOGS_UNFILTERED_DIAGNOSTIC`)
  reverted to `"0"` on Railway `sports-intel-layer` (dev), `skipDeploys:
  true` — no redeploy triggered by the revert.
- Temporary diagnostic code fully reverted: `app/diagnostics/`
  (module + `__init__.py`) deleted, the `main.py` startup hook block
  removed, `build_msf_player_gamelogs_unfiltered_diagnostic_client`
  and `_MYSPORTSFEEDS_BASE_URL` removed from
  `app/master_refresh/production_clients.py`.
- Full test suite re-run post-revert: **758/758 passing**, zero
  regressions.
- No stats persisted to any canonical table this pass (explicit
  guardrail, and moot — no payload was returned).
- Exactly one live provider call made (the authorized one). No
  alternative filters, season formats, endpoint names, date/week
  parameters, or other gamelog variants attempted, per HQ's explicit
  stop condition. No BALLDONTLIE/SportsDataIO. No purchases. No
  canonical stats persistence. No recurring polling. No Probability
  Modeling integration. No Phase 8.1 logic changes. Staging/production
  untouched.
