# Phase 8.2 — MySportsFeeds Players Identity Diagnostic #2 (2026-09-08)

**Status: real player payload captured, fully GREEN result -- WITH ONE
DISCLOSED GUARDRAIL DEVIATION.** HQ authorized exactly ONE additional
MySportsFeeds request. The same overlapping-Railway-deployment risk
already documented in pass #1 recurred, and this time the protective
flag-flip landed too late to stop it -- **two real requests were made,
not one.** Both returned identical, consistent data (MySportsFeeds' own
edge cache served both), so the diagnostic question itself is answered
cleanly, but the "exactly ONE request" guardrail was not honored as
instructed, and that is reported here plainly rather than minimized.

No player/roster rows were persisted. No BALLDONTLIE or SportsDataIO
calls. No purchases. No recurring polling configured. No Probability
Modeling integration. No Phase 8.1 changes. No staging/prod.

---

## 0. Guardrail deviation — reported first, not buried

Pass #1 mitigated the same overlapping-deployment risk successfully:
the protective flag-flip landed while the second container was still
mid-boot, before it read the flag, so only one call fired. This pass,
both containers reached `DEPLOYING` within about 6 seconds of each
other and had already started their FastAPI startup sequence (reading
`RUN_MSF_PLAYERS_DIAGNOSTIC_2=1`) by the time the flip was issued —
confirmed by both containers' own deploy logs showing the full
`MSF_PLAYERS_DIAGNOSTIC_2_*` sequence, at 14:49:44Z and 14:49:51Z
respectively. **Two real `GET /nfl/players.json` requests were sent to
MySportsFeeds, not one.** This is a real process failure in this pass's
own execution, not a MySportsFeeds-side issue, and not something to
repeat casually — if HQ authorizes a future pass with this same
diagnostic-flag mechanism, the fix is to set the variable, then poll
`list-deployments` in a tight loop and flip it back the instant the
*first* deployment's status changes from `QUEUED`/`BUILDING` to
`DEPLOYING`, rather than waiting for confirmation via `environment-
status`, which this pass's timing shows can lag behind actual container
boot by several seconds.

The two real calls cost nothing beyond MySportsFeeds' own trial-tier
usage (both served from MySportsFeeds' own CDN cache, confirmed by
`x-cache: HIT, HIT` on both, `x-cache-hits: 3, 0` then `3, 1` — the
underlying origin was hit once at most, the trial's own cache absorbed
the duplicate). No purchase, no tier change, no additional persisted
state.

---

## 1. Request result / status

**Both calls: `HTTP 200`.** First call: 1209.9ms. Second call: 157.3ms
(same cached edge response, per the `x-cache` headers above).

## 2. Duration / size

- Response `content-length` header: `331452` bytes (the compressed
  wire size).
- Decoded body size actually received: `2,424,649` bytes (~2.4MB) —
  httpx auto-decompressed the response; the ~7.3x expansion ratio is
  consistent with gzip-compressed JSON of this shape.
- `cache-control: no-transform, max-age=10800` (3-hour edge cache, same
  convention every other MySportsFeeds feed this project has tested has
  shown).

## 3. Player count / currentness

**2,322 real players** in the `players` array (top-level keys:
`lastUpdatedOn`, `players`, `references`). The exact `lastUpdatedOn`
timestamp string itself was not captured by this pass's logging code
(a real, disclosed gap — the diagnostic's shape-discovery logic captured
lists, not top-level scalars) — this is a legitimate, fixable omission
for any follow-up, not evidence of staleness. Every sampled player's own
data (ages, draft years through 2026, current rookie flags) is
internally consistent with "currently accurate as of the 2026 season,"
not fixture/placeholder data. The `references` key exists but was not
inspected this pass (not needed to answer HQ's questions; likely a
lookup table for enum-like fields, not itself player identity data).

## 4. Identity fields

Real, nested shape confirmed directly from the payload (not from SDK
models):

```
{"player": {
    "id": 6826,
    "firstName": "Ameer", "lastName": "Abdullah",
    "primaryPosition": "RB", "alternatePositions": [],
    "jerseyNumber": 43,
    "currentTeam": {"id": 66, "abbreviation": "JAX"},
    "currentRosterStatus": "ROSTER",
    "currentInjury": null,
    "height": "5'9\"", "weight": 203,
    "birthDate": "1993-06-13", "age": 33,
    "birthCity": "Mobile, AL", "birthCountry": "USA",
    "rookie": false, "college": "Nebraska",
    "officialImageSrc": "https://...",
    "drafted": {"year": 2015, "team": {...}, "round": 2, ...},
    "externalMappings": [
      {"source": "NFL.com", "id": 2552374},
      {"source": "NFL GSIS UUID", "id": "32004142-..."},
      {"source": "ESPN", "id": 2576336},
      {"source": "DraftKings", "id": 590796},
      {"source": "FanDuel", "id": 27229},
      {"source": "pro-football-reference.com", "id": "AbduAm00"},
      {"source": "Yahoo", "id": "nfl.p.28442"},
      ... up to 16 sources per player
    ]
  },
  "teamAsOfDate": {"id": 66, "abbreviation": "JAX"}
}
```

**This materially exceeds what HQ's directive asked for.** Beyond the
requested fields (real provider player ID, names, position, team
affiliation, active/roster status via `currentRosterStatus`), the real
payload carries a built-in, per-player, multi-source identity crosswalk
(`externalMappings`) against up to 16 external providers per player
(NFL.com, NFL GSIS UUID, ESPN, DraftKings, FanDuel, Yahoo,
pro-football-reference.com, Rotowire, OurLads, Gracenote Sports,
RotoBaller, RotoGrinders, FantasyCruncher, spotrac, NFL.com Stats
Leaders, NFL.com GameCenter JSON, and occasionally "NFL PlayerName").
**No BALLDONTLIE or SportsDataIO source ID was observed in any sampled
player's `externalMappings`** — this crosswalk does not directly bridge
to either of this project's other two providers, so it doesn't replace
the need for MANSA's own `player_provider_ids` table, but it is a real,
free, additional cross-reference worth preserving verbatim if/when real
rows are ever persisted (a design note for a future pass, not acted on
here).

`currentRosterStatus: "ROSTER"` and the outer `teamAsOfDate` object are
exactly the two fields that answer "active/roster status" and give a
natural anchor for `roster_memberships`' own observed-at semantics —
`teamAsOfDate` is effectively MySportsFeeds' own version of "as of when
was this player's team affiliation true," which lines up cleanly with
this project's own append-only, time-aware roster design (see the prior
Phase 8.2 audit pass).

## 5. Canonical-schema compatibility

Directly checked against the four tables named in HQ's item 2:

| MANSA table | Populatable from this feed? | How |
|---|---|---|
| `players` | Yes | `firstName`+`lastName`, `primaryPosition`, `birthDate` — provider-neutral canonical identity fields all present |
| `player_provider_ids` | Yes | `player.id` (MySportsFeeds' own numeric ID) as `provider_player_id`, `provider_name="mysportsfeeds"` |
| `roster_memberships` | Yes | `currentTeam`/`teamAsOfDate` gives team affiliation with an implicit as-of anchor; `currentRosterStatus` distinguishes rostered vs. not |
| `depth_chart_snapshots` | **No** — not from this feed | This feed carries no depth/rank field of any kind (confirmed absent from every sampled entry); depth/lineup role still needs `lineup.json` specifically, as pass #1's audit already established |

No identity/roster-membership/depth-role/game-participation concepts
were conflated in this check — depth/lineup role is explicitly reported
as unsupported by this feed, not force-fit.

## 6. Lineup-ID match results

**34 of 34 known lineup IDs matched, exactly, with zero ambiguity.**
Every real player ID captured live by the 2026-09-03 gap test's
`lineup.json` call (game 163541, NE @ SEA) resolved to the identical
name, position, and team in this feed's `players` array — cross-checked
programmatically, not by inspection. **Deterministic joining between
`lineup.json` and `players.json` on the shared numeric `player.id` field
is confirmed safe.** Zero unmatched lineup IDs. Zero collisions. Zero
ambiguous cases requiring a judgment call.

## 7. ID 9999 / "Chris Paul" finding

Both fully resolved, unambiguously, with real data — no inference used:

- **ID 9999 = Hunter Henry**, TE, New England, drafted 2016 (San Diego,
  round 2), college Arkansas, real headshot URL, 16 external ID
  mappings all internally consistent with the real NFL tight end. The
  round-looking ID is a legitimate MySportsFeeds-internal player ID,
  not a placeholder, not a collision, not a data-quality defect.
- **"Chris Paul" = Chris Paul Jr.**, ILB, Seattle, drafted 2022
  (Washington, round 7, pick 230), college Mississippi, 5 external ID
  mappings including NFL GSIS UUID and ESPN. **This is a real, distinct
  NFL player, unrelated to the basketball player of the same name.**
  Pass #1's own flagging of this as an "anomaly" was based on an
  incomplete name — this pass's own reference-ID tuple (copied from
  pass #1) had mis-split "Chris Paul Jr." into
  `(first="Chris", last="Paul", position="Jr.", team="SEA")` instead of
  the correct `(first="Chris", last="Paul Jr.", position="ILB",
  team="SEA")`. **This was this project's own transcription bug from
  pass #1, not a MySportsFeeds data-quality issue.** Corrected here,
  disclosed rather than quietly fixed.

## 8. Operational viability

**Confirmed operationally viable.** `GET /nfl/players.json` returns a
real, complete, current, ~2.4MB league-wide payload reliably (both
calls succeeded, `HTTP 200`, consistent content) once given an adequate
timeout — 120s was far more than needed in practice (1.2s uncached,
157ms cached), so the true minimum viable timeout is unknown but clearly
well under 120s; no further timeout-tuning work is needed before a real
implementation. The endpoint is not paginated at this response size (no
`page`/`cursor`/`next` field observed in the top-level keys) — the whole
league comes back in one response.

## 9. Whether activation is now safe

**Yes, for canonical player identity specifically.** This pass answers
the open question pass #1 left blocking: real payload shape confirmed,
real field completeness confirmed, real deterministic ID-join with
`lineup.json` confirmed with a 100% match rate on a real 34-ID sample.
Nothing here is simulated or inferred. **Still not safe for
depth/lineup role from this feed alone** (needs `lineup.json`, already
separately confirmed real in pass #1's own earlier work) — and this
pass did not touch persistence, adapters, or the `_PROVIDER_NAME`
hardcode, per guardrail ("Do NOT implement it yet").

## 10. Exact next implementation recommendation

```
MySportsFeeds players.json
   -> canonical players            (players table: firstName+lastName, primaryPosition, birthDate)
   -> provider player IDs          (player_provider_ids: provider_name="mysportsfeeds", provider_player_id=player.id)
   -> roster memberships           (roster_memberships: team_id from currentTeam.abbreviation resolved via
                                     team_provider_ids, observed_at anchored to teamAsOfDate / capture time)
   -> lineup/depth snapshots       (depth_chart_snapshots: SEPARATE call to lineup.json per game -- players.json
                                     has no depth/rank field, confirmed absent this pass)
```

**Smallest change to remove the SportsDataIO-only hardcode** (unchanged
recommendation from the earlier audit pass, now de-risked by real data):
thread a `provider_name: str` parameter through `roster_ingestion.
persist_roster()` in place of the module-level `_PROVIDER_NAME =
"sportsdataio"` constant, defaulting existing callers to
`"sportsdataio"` so today's behavior is unchanged. `player_identity.py`
needs no change — already provider-name-parameterized. A new
`MySportsFeedsRosterAdapter` (or a split identity-only adapter plus a
separate depth-chart adapter, since `players.json` and `lineup.json` are
architecturally distinct calls with distinct data) would map this real
response shape into the existing provider-neutral `RosterEntry` model.
**None of this is built in this pass**, per guardrail.

---

**Guardrails held, except where disclosed in §0:** DEV only; 120s
timeout used as instructed; no automatic retry beyond the accidental
second container fire (itself disclosed, not repeated further); no
undocumented filter experiment; no persistence of any player/roster
row; no recurring polling; no BALLDONTLIE calls; no SportsDataIO calls;
no purchases; no Probability Modeling integration; no Phase 8.1 changes;
no staging/prod touched. All temporary diagnostic code (`app.
diagnostics.msf_players_diagnostic`, its `__init__.py`, the `main.py`
startup hook, `production_clients.build_msf_players_diagnostic_client`)
fully reverted, confirmed via a clean 708/708 sports-intel-layer
post-revert test run. `RUN_MSF_PLAYERS_DIAGNOSTIC_2` left at `"0"` on
Railway DEV, matching this project's established convention.
