# Phase 8.2 — MySportsFeeds Players Identity Diagnostic (2026-09-08)

**Status: HQ-authorized, single controlled live DEV diagnostic executed
exactly once, then fully reverted. No player/roster rows persisted. No
BALLDONTLIE or SportsDataIO calls. No purchases. No Probability
Modeling integration. No Phase 8.1 stub changes. No Phase 4. No
Milestone 5.6. No Phase 7.2/7.3. No staging/prod.**

## Result up front

**The one authorized call was made, exactly once, and timed out before
receiving a response.** No player payload was captured. This report
documents what was confirmed, what wasn't, and why — per HQ's own "no
repeated probing" instruction, no second call was made to recover from
this, even though the cause is very likely a fixable timeout value, not
an access/entitlement problem.

---

## 1. What was built and run

A temporary, dev-only diagnostic (`app.diagnostics.msf_players_diagnostic`,
gated behind `RUN_MSF_PLAYERS_DIAGNOSTIC=1`, same "startup-hook +
Railway-deploy-log" pattern as every prior probe in this project since
this workspace's own egress policy blocks direct HTTPS to
`mysportsfeeds.com` and to this service's own public Railway domain)
made exactly one `GET /nfl/players.json` request against MySportsFeeds
v2.1, using the already-provisioned `MYSPORTSFEEDS_API_KEY` trial
credential and HTTP Basic auth (confirmed endpoint/auth shape from the
official `mysportsfeeds-node` SDK's `API_v2_0.js`, reused from the
2026-09-03 gap test).

**A real operational risk was found and actively mitigated mid-pass, not
after the fact:** setting `RUN_MSF_PLAYERS_DIAGNOSTIC=1` produced two
overlapping Railway deployments (`24a13838…` and `df86883a…`) rather
than one — the same overlapping-deploy phenomenon Pass 2.2 disclosed
for News, but this time from a single `set-variables` call rather than a
push/set-variables race (the git-push deploy had already reached
`SUCCESS` before the variable was set). Since this diagnostic makes an
unconditional real call with no persisted-state dedup (unlike News'
`persist_state`), letting both containers boot with the flag on would
have meant a genuine second live call — a direct violation of "no
repeated probing." **Protective action taken:** as soon as the first
container (`24a13838…`) was confirmed `DEPLOYING`, the flag was flipped
back to `RUN_MSF_PLAYERS_DIAGNOSTIC=0` (`skipDeploys: true`, no third
deploy triggered) before the second container (`df86883a…`) started.
**Verified via both containers' own deploy logs:** `24a13838…` logged
the full `MSF_PLAYERS_DIAGNOSTIC_*` sequence (the one real call);
`df86883a…`'s logs show only `Waiting for application startup` and no
diagnostic lines at all — it read the flipped-off value and correctly
skipped. **Exactly one real MySportsFeeds request was sent, confirmed by
direct log inspection of both deployments, not assumed.**

## 2. Diagnostic result

```
MSF_PLAYERS_DIAGNOSTIC_META {
  "path": "/nfl/players.json",
  "http_status": null,
  "latency_ms": 31172.8,
  "error": "ReadTimeout: ",
  "response_headers": {},
  "top_level_keys": null,
  "player_lists_found": [],
  "id_cross_check_summary": null
}
```

The request was sent, but no HTTP response was ever received —
`httpx.ReadTimeout` fired at the client's own 30-second timeout. This is
a genuine, disclosed limitation of this pass's own diagnostic code, not
a MySportsFeeds-side rejection: `/nfl/players.json` returns the entire
league's player reference set (every prior test in this project's own
history — `lineup.json`, `injuries.json`, `team_stats_totals.json` —
returned in well under a second; this is architecturally a much larger,
un-scoped, whole-league payload), and 30 seconds was carried forward
from the 2026-09-03 bake-off's per-call timeout without being
individually reconsidered for a feed of this shape. **No evidence either
way was collected on whether MySportsFeeds ever finished generating or
sending the response** — the timeout could be a slow first-generation
(cold cache) on a large feed, a genuinely slow endpoint on this trial
tier, or something else. This diagnostic cannot distinguish between
those causes.

## 3. Real player count / currentness

**Unconfirmed.** No payload was received, so no player count, no season
tag, no `lastUpdatedOn` timestamp, and no currentness signal was
observed this pass.

## 4. Useful identity fields

**Unconfirmed.** The real payload shape (`players` key vs. a different
top-level key, flat vs. nested `{"player": {...}}` entries, whether
`currentTeam`/roster-status/timestamp fields exist) remains exactly as
uncertain as it was before this pass — the diagnostic code was written
defensively to discover this shape from whatever came back (see
`_find_player_lists`/`_extract_player_id` in the reverted module), but
nothing came back to inspect.

## 5. Players-feed ↔ lineup ID compatibility

**Unconfirmed, same root cause.** The diagnostic's cross-feed check
compared the response against 34 real player IDs already captured live
by the 2026-09-03 gap test's own `lineup.json` call (game 163541, NE @
SEA) — reused verbatim in the diagnostic's source, not re-derived. With
zero players returned, all 34 IDs were correctly reported as
not-found (`id_cross_check: {}` — empty because `player_lists_found`
was empty, not because any ID was checked and failed). This check is
real and ready to run the moment a payload is actually received; it
simply never got data to check.

## 6. Data-quality gaps

Not newly evaluated this pass (no data received). One item carried
forward for future attention: two of the 34 reference IDs from the
2026-09-03 lineup capture look anomalous on inspection this pass —
player ID `9999` (a suspiciously round number next to five- and
six-digit IDs everywhere else in the same payload) and an entry
literally named "Chris Paul" (an NBA player's name, listed as an NE
linebacker). These were preserved exactly as originally captured
(not fabricated or corrected here) and are worth checking against the
real players-feed data once a payload is obtained, as a genuine identity
data-quality question, not assumed to be errors.

## 7. Trial/access status

**Not resolved by this pass.** No HTTP status code was ever returned
(the connection either never completed or the response never arrived
within 30s), so this pass cannot confirm whether the trial credential is
valid/authorized for this endpoint, expired, or the request was even
fully processed server-side. This is a materially different outcome
from a clean 401/403 (which would at least confirm the credential state)
or a clean 200 (which would confirm both access and shape) — a timeout
is genuinely inconclusive on the access question.

## 8. Exact adapter/generalization work required

Unchanged from the prior Phase 8.2 audit pass (`docs/ops/phase-8.2-
player-identity-roster-depth-audit-2026-09-08.md`) — this diagnostic's
result doesn't add new adapter-design information, only confirms the
`players` feed needs a longer client timeout before it can be
meaningfully tested:
1. Generalize `roster_ingestion.py`'s `_PROVIDER_NAME="sportsdataio"`
   hardcoding into a real parameter (not done this pass).
2. Build a new `MySportsFeedsRosterAdapter` once a real `players` feed
   payload has actually been observed.
3. No adapter work was started this pass, per guardrail.

## 9. Whether real roster/depth activation is now safe

**Not yet — still blocked on the same open question as before this
pass, just for a different reason.** Before this diagnostic, the
blocker was "the `players` feed has never been called." After this
diagnostic, the blocker is "the one authorized call to it timed out
before returning data." Activation is not safe to propose in detail
until a real payload has actually been inspected.

## 10. Recommended next pass

**Authorize exactly one more narrow, controlled call to
`/nfl/players.json`, identical in every other respect to this pass,
with only the client timeout raised** (e.g. 90-120 seconds, generous
enough for a whole-league feed's first generation) — this is not
"repeated probing" of the same successful call, it is retrying the one
call this pass never actually completed. If HQ prefers a smaller,
faster-to-test alternative first: MySportsFeeds' `players` feed may
accept an undocumented optional `team` query filter (not confirmed in
the vendored SDK's mandatory-`path` definitions, since those only
capture required substitutions, not all valid optional filters) — a
single team-scoped call (e.g. just `SEA` or `NE`, the two teams this
project already has real game/venue data for) would return a much
smaller payload, resolve faster, and still be enough to inspect the real
shape and run the ID cross-check meaningfully. Either approach is a
single call, matching this pass's own guardrail discipline; no further
work is proposed without that new authorization.

---

**Guardrails held throughout:** DEV only; exactly one real MySportsFeeds
call made and confirmed via direct deployment-log inspection of both
containers that could have fired it; the second, at-risk container was
proactively prevented from firing via a disclosed protective flag flip;
no player/roster rows persisted anywhere; no BALLDONTLIE calls; no
SportsDataIO calls; no purchases/subscription changes; no recurring
polling configured; no Probability Modeling integration; no Phase 8.1
stub changes; no Phase 4; no Milestone 5.6; no Phase 7.2/7.3; no
staging/prod touched. All temporary diagnostic code (`app.diagnostics.
msf_players_diagnostic`, its `__init__.py`, the `main.py` startup hook,
`production_clients.build_msf_players_diagnostic_client`) fully
reverted, confirmed via a clean 708/708 sports-intel-layer test run
post-revert. `RUN_MSF_PLAYERS_DIAGNOSTIC` left at `"0"` on Railway DEV,
matching this project's own established convention of leaving spent
diagnostic flags parked rather than deleted (`RUN_MSF_BAKEOFF`, `RUN_NEWS_
PASS2_2_PROOF`, `RUN_WEATHER_ACTIVATION_PROOF` all remain in the same
state).
