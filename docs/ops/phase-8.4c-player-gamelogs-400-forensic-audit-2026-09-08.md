# Phase 8.4C — Player Gamelogs 400 Forensic Audit (2026-09-08)

MANSA HQ directive: "MANSA PHASE 8.4C — PLAYER GAMELOGS 400 FORENSIC
AUDIT" (2026-09-08). **ZERO provider calls made this pass.** Pure
code/git-history/SDK forensics to determine why Phase 8.4B's real
`player_gamelogs` request was rejected with HTTP 400, and to propose
(not execute) the single highest-confidence corrected request for a
future Phase 8.4D.

**HQ's external verification is treated as ground truth and changes
the interpretation of the 400**: MySportsFeeds' own public documentation
confirms Daily/Weekly/Seasonal Player Gamelogs exist in V2 STATS. The
400 is therefore evidence of a **wrong request contract**, not a
missing capability — this report reasons entirely on that basis.

---

## 1. Exact 8.4B request reconstructed

From the actual (now-reverted, git-history-preserved) diagnostic code,
commit `a35d19e`:

```
GET https://api.mysportsfeeds.com/v2.1/pull/nfl/2025-2026-regular/player_gamelogs.json?player=9999
Authorization: Basic base64("<api_key>:MYSPORTSFEEDS")
Accept: application/json
```

- **Feed key used to derive this URL**: `seasonal_player_gamelogs` →
  `API_v2_0.js`'s feed table maps it to `{season: true, endpoint:
  'player_gamelogs'}` (no `path` array) → URL template
  `${baseUrl}/${league}/${season}/${endpoint}.${format}` →
  `/nfl/2025-2026-regular/player_gamelogs.json`. **CONFIRMED** correct
  mechanical derivation from the SDK's own feed table — verified by
  re-reading `__determineUrl` in `API_v2_0.js` line-by-line this pass.
- **Query params**: exactly `{"player": "9999"}` — nothing else. No
  `force` param was sent.
- **No `force=false` param** — a real, confirmed difference from what
  the SDK's own `getData()` does automatically (`API_v1_0.js`:
  `if (!Object.keys(params).includes("force")) { params['force'] =
  'false'; }`). **CONFIRMED not the cause of the 400**, however: Phase
  8.3C's real, successful `player_stats_totals` call (commit `e42f003`)
  also omitted `force` entirely (`request_params = {"team":
  _TARGET_TEAM}`, nothing else) and still returned a clean HTTP 200.
- **Season string, base URL, auth scheme**: byte-identical to Phase
  8.3C's successful request. **CONFIRMED not the cause.**

## 2. Vendored SDK / docs / examples inspection

Re-read in full this pass: `API_v1_0.js`, `API_v1_1.js`, `API_v1_2.js`,
`API_v2_0.js`, `API_v2_1.js`, `index.js`, `README.md`.

- **`seasonal_player_gamelogs` feed table entry**: `{season: true,
  endpoint: 'player_gamelogs'}` — no mandatory path segment declared.
  **CONFIRMED** (direct code read).
- **The SDK performs zero client-side validation of parameter VALUES**
  — `getData()` only validates the feed *name* (`__verifyFeedName`) and
  *format* (`__verifyFormat`); every param the caller supplies is
  passed straight through as the request querystring (`this.options.qs
  = params`) with no shape-checking. **CONFIRMED**: a 400 must
  originate from MySportsFeeds' own server, not from anything this
  library could catch first.
- **Only two documented usage examples exist for this feed key, both
  NBA, both identical apart from API version**:
  ```
  v1.x: msf.getData('nba', '2016-2017-regular', 'player_gamelogs', 'json', {player: 'stephen-curry'})
  v2.0: msf.getData('nba', '2016-2017-regular', 'seasonal_player_gamelogs', 'json', {player: 'stephen-curry'})
  ```
  **CONFIRMED**: the `player` parameter *name* is documented for this
  exact feed key. **UNKNOWN**: whether the value format
  (`'stephen-curry'`, a lowercase hyphenated name-slug) generalizes to
  NFL, or is NBA-specific/legacy convention.
- **No NFL-specific example of any `_gamelogs` feed exists anywhere in
  the README.** The only NFL example in the entire README is
  `{team: 'dallas-cowboys'}` for the unrelated (v1.x)
  `cumulative_player_stats` feed. **CONFIRMED absent** — not a gap in
  this pass's search, a real gap in the vendored documentation itself.
- **No local repo documentation beyond this project's own prior
  ops reports adds anything new** — re-checked `docs/ops/nfl-provider-
  gap-test-mysportsfeeds-2026-09-03.md` and every Phase 8.2/8.3 report;
  none captured a real `player_gamelogs` or `team_gamelogs` payload
  (both attempts on the family have only ever produced 400s).

## 3. Comparison against the successful 8.3C `player_stats_totals` request

| | 8.3C (succeeded, HTTP 200) | 8.4B (failed, HTTP 400) |
|---|---|---|
| Feed family | `seasonal_player_stats` → `player_stats_totals` | `seasonal_player_gamelogs` → `player_gamelogs` |
| URL shape | `/nfl/{season}/player_stats_totals.json` | `/nfl/{season}/player_gamelogs.json` — identical template, identical `__determineUrl` code path |
| Filter param | `team=NE` (abbreviation) | `player=9999` (numeric MSF id) |
| `force` param | absent | absent |
| Season string | `2025-2026-regular` | `2025-2026-regular` — identical |
| Auth | Basic, `MYSPORTSFEEDS` literal | Basic, `MYSPORTSFEEDS` literal — identical |

**CONFIRMED**: every mechanical aspect of request construction (base
URL, auth, season format, `__determineUrl` code path) is identical
between the two. The only two real differences are the *feed family*
and the *filter parameter used* — narrowing the 400's cause to one of
those two dimensions, not to any transport/auth/encoding issue.

## 4. Comparison against `team_gamelogs`'s prior 400s

Reconstructed from git history (`7c06f5f`, `a14a116` — the original
2026-09-03 gap test, not this session's own passes):

| Attempt | Params | Result |
|---|---|---|
| `team_gamelogs.json`, Run 1 | none | **400** |
| `team_gamelogs.json`, Run 2 | `{"team": "buffalo-bills"}` — a hyphenated full-name slug, matching the SDK README's own documented style for team-based filters | **400, still** |

**This is the single most important comparison in this audit.** It
establishes, from this project's own real history, that:

- **CONFIRMED**: a bare, unfiltered `_gamelogs`-family request fails
  (400) — matching this session's own unfiltered hypothesis being
  worth testing for `player_gamelogs` too.
- **CONFIRMED**: adding the README-documented-style slug filter to
  `team_gamelogs` did **not** fix it — the 400 persisted even with a
  filter that matches the "correct" documented pattern.
- **STRONGLY SUPPORTED**: this project has **zero confirmed instances,
  ever, of a hyphenated-slug-format filter succeeding against the real
  v2.1 NFL API** — every real slug attempt (`team_gamelogs` with
  `"buffalo-bills"`) has failed. The only filter that has ever
  succeeded against a real v2.1 NFL endpoint is `player_stats_totals`'s
  `team=NE` — an **abbreviation**, not a slug. This directly informs
  §6 below: Phase 8.4B's choice of the numeric `player=9999` (over a
  slug like `"hunter-henry"`) was the evidence-aligned choice, not a
  likely error.
- **STRONGLY SUPPORTED, not confirmed**: the `_gamelogs` family as a
  whole (both `team_` and `player_` variants) has a request-contract
  problem that is **not resolved by filter-parameter guessing alone** —
  two independent endpoints in the same family have now failed under
  three different parameter attempts (none, team-slug, player-numeric-id).

## 5. Findings, classified

**CONFIRMED:**
- The URL/endpoint path (`/nfl/{season}/player_gamelogs.json`) is
  mechanically correct per the vendored SDK's own feed table.
- The `player` parameter *name* is documented for this exact feed key.
- Every transport-level detail (base URL, auth, season format) matches
  the successful 8.3C request byte-for-byte.
- `team_gamelogs` (the sibling family member) has failed with 400
  under both no filter and a README-style slug filter.
- No slug-format filter has ever succeeded against any real v2.1 NFL
  endpoint in this project's history.

**STRONGLY SUPPORTED:**
- The `_gamelogs` family has a request-contract problem broader than
  any single parameter's value format — likely something both
  `team_gamelogs` and `player_gamelogs` share (a missing mandatory
  parameter neither the SDK table nor the README discloses, or a
  tier/plan restriction specific to this feed family, per the same
  pattern as the already-known prior-season game-listing 403).
- The numeric player id format (`9999`) was the right choice given
  available evidence, not a likely cause of the 400.

**PLAUSIBLE:**
- The `_gamelogs` family may require an explicit date/week scoping
  parameter in practice (unlike `_stats_totals`, which is genuinely
  season-wide) — inferred from the family's own `daily_`/`weekly_`
  variants existing at all, and from "gamelogs" semantically implying
  per-game/dated rows, but this is this report's own inference, not
  confirmed by any code, doc, or prior real result.
- This could be the same underlying restriction as the original
  bake-off's confirmed prior-season game-listing `403` (a genuine
  trial-tier/plan boundary), manifesting as `400` instead of `403` for
  a different reason — plausible pattern-matching, not confirmed.

**UNKNOWN:**
- Whether MySportsFeeds' real v2.1 NFL API expects a slug, a numeric
  id, or something else entirely for the `player` filter specifically
  (as opposed to team filters, where abbreviation is now confirmed to
  work) — no real v2.1 NFL *player*-filtered request of any kind has
  ever succeeded to compare against.
- Whether an entirely different, undocumented parameter name is
  required.
- Whether the feed is gated behind a plan/tier this trial doesn't
  carry, independent of parameters — HQ's external verification
  confirms the *capability* exists in V2 STATS generally, but not that
  every trial tier has access to it.

## 6. Is `player=9999` serialized correctly?

**Mechanically, yes — confirmed.** `httpx` serializes
`params={"player": "9999"}` as a standard URL-encoded querystring
(`?player=9999`), identical in form to 8.3C's successful `?team=NE`.
There is no encoding defect to find here.

**Whether `9999` is the *value format* MySportsFeeds expects: UNKNOWN,
but STRONGLY SUPPORTED as the better of the two known real
alternatives.** Per §4/§5, this project has no confirmed case of a slug
succeeding and one confirmed real case of a non-slug (abbreviation)
identifier succeeding elsewhere — the numeric id remains the
better-evidenced choice, not the likely defect, even though it remains
unconfirmed for this specific feed.

## 7. Is the endpoint path itself correct?

**Yes, confirmed as correctly derived from the vendored SDK — but
"correctly derived from the SDK" is not the same as "correct in
reality," and the `_gamelogs` family's own track record (§4) means this
distinction matters here specifically.** The SDK's static feed table
already proved unreliable once for this exact family: it declares
`seasonal_team_gamelogs` needs no path segment, and that declaration
did not prevent two real 400s. There is no positive evidence the path
itself is wrong, but the family's history means "matches the SDK
table" carries less assurance here than it did for `player_stats_totals`.

## 8. Single highest-confidence corrected request for Phase 8.4D (NOT executed)

**Primary recommendation: drop the filter entirely.**

```
GET /nfl/2025-2026-regular/player_gamelogs.json
(no query parameters)
```

**Rationale, in order of strength:**
1. This isolates the one variable no prior real attempt has isolated:
   whether `player_gamelogs` fails **regardless of any filter**,
   matching `team_gamelogs`'s own Run 1 (unfiltered, 400). If this also
   400s, that is strong, cheap, decisive evidence the `_gamelogs`
   family itself is contract-broken or tier-gated independent of
   parameters — closing off an entire branch of future guessing in one
   call.
2. It sidesteps the genuinely unresolved player-filter-value-format
   question (§6) entirely, rather than spending the one authorized call
   on a guess between `9999` and a slug when neither is confirmed.
3. It mirrors this project's own established "isolate one variable"
   diagnostic discipline (explicitly used this way in the original
   `team_gamelogs` Run 1→Run 2 sequence, and in Phase 8.4B's own §14
   recommendation).

**If HQ prefers to keep testing the filter itself instead**, the
next-best candidate, still not executed, would be
`{"player": "hunter-henry"}` (a slug, matching the only documented
example's format) — but this report does **not** recommend it as
primary, since §4/§5's evidence weighs against slug formats generally
succeeding against this API version's NFL surface, making it a weaker
bet than testing the family's own base availability first.

## 9. Hunter Henry context-preview requirement — preserved for the eventual successful call

Not built this pass (no real gamelog data exists to build it from).
Preserved verbatim from Phase 8.4B's own directive, for whichever
future pass first obtains a real, successful `player_gamelogs` payload:

For up to 3 selected real historical game rows, show — where MANSA
genuinely has matching historical evidence, joined by an explicit,
named key, never inferred or substituted from current/present-day data:

- Player, game date, opponent, home/away, canonical game match, venue
- Player stat line (passing/rushing/receiving/defense/special-teams as
  applicable) and participation/snap-count/usage fields
- Roster role and depth/lineup information *for that specific
  historical game* (not current depth chart)
- Weather *for that specific historical game* (not current conditions)
- News context *contemporaneous with that game* (not current news)
- Odds/market context *for that specific historical game* (not current
  lines)

**Any dimension without a genuine historical match must display exactly
`UNAVAILABLE — <reason>`** (e.g. `UNAVAILABLE — no historical weather
observation for this game`, `UNAVAILABLE — no game-specific lineup
snapshot`, `UNAVAILABLE — no matching historical odds snapshot`) — never
current data substituted, never inferred from season totals. The exact
join key used for every successful contextual join must be reported
alongside it. This remains a preview/report requirement only — no
contextual scoring or recommendation logic is to be implemented when
this is eventually built.

---

## Summary for HQ

**Root-cause confidence: STRONGLY SUPPORTED that the `_gamelogs`
family has a request-contract issue broader than the specific filter
parameter tried; the exact fix remains UNKNOWN.** Nothing here is
presented with more certainty than the evidence supports — the
`player=9999` choice was evidence-aligned, not a likely mistake; the
real, corroborated pattern is that this entire endpoint family
(`team_gamelogs` and `player_gamelogs` alike) has never once succeeded
against this project's real MySportsFeeds trial, under three different
parameter attempts across two endpoints.

**Recommend HQ authorize exactly one Phase 8.4D call**: the unfiltered
`GET /nfl/2025-2026-regular/player_gamelogs.json` proposed in §8 — the
single cheapest, most information-dense next test, isolating the family-
wide-failure hypothesis from the filter-format hypothesis in one call.
No call was made this pass. No schema, persistence, or Phase 8.1 code
was touched. DEV only, audit only.
