# Pre-Live Worker Hardening (2026-09-13)

MANSA HQ directive: "PRE-LIVE WORKER HARDENING." Two architectural
corrections to the permanent MSF postgame worker before authorizing the
first live SF@LAR execution: numeric-first team identity resolution
(replacing the abbreviation-scheme dependency entirely, not patching it
with two more rows), and cache/rate-aware call-control scheduling.
**No MySportsFeeds call was made anywhere in this pass.**

## 1. Team identity solved generically, not with a 2-row patch

**Audit finding, confirmed directly against the real Gate B fixture**:
a raw MSF `game_boxscore` player entry (`{"player": {"id",
"firstName", "lastName", "position", "jerseyNumber"}, "playerStats":
[...]}`) carries **no team field of any kind**. Team identity has
always been entirely derived from which side array
(`stats.away.players` vs `stats.home.players`) an entry sits in, with
both the abbreviation AND the real numeric team id available at that
same side level (`game.awayTeam.{abbreviation,id}` /
`game.homeTeam.{abbreviation,id}` -- e.g. NE: abbreviation `"NE"`,
numeric `50`). The numeric id was therefore always exactly as
available per-player as the abbreviation is -- nothing about the raw
payload required guessing or genuinely lacked player-level team
identity.

**Adapter change** (`app/adapters/providers/mysportsfeeds_game_boxscore.py`):
`_sided_players` now returns `(entry, team_abbreviation,
team_provider_id)` triples instead of pairs -- `team_provider_id` is
`game.{away,home}Team.id`, stringified, `None` only if genuinely absent.
`PlayerStatLine` (`app/adapters/models.py`) gains an additive
`provider_team_id: str | None = None` field, populated by
`parse_game_boxscore` alongside the existing `team` (abbreviation) field
-- both now travel through to every caller. 3 new regression tests
(numeric ids extracted correctly per side; a raw player entry confirmed
to have no team field of its own, proving the derivation is real, not
assumed; a missing numeric id stays `None`, never invented).

**Identity resolution hardened** (`app/persistence/player_identity_activation.py`,
`activate_msf_player`): `provider_team_id` now means MySportsFeeds' own
**numeric** team identifier and is the **primary, required** team-identity
path (32/32-team `team_provider_ids` coverage since the Sunday Ingestion
Foundation Build). A new parameter, `raw_team_abbreviation`, carries the
abbreviation as **supporting/consistency evidence only**:

- Numeric id missing or unmapped -> `team_unresolved`, exactly as
  before -- the abbreviation is never consulted as a substitute primary
  path (consulting it would silently reintroduce the same piecemeal
  12/32-coverage problem this hardening removes).
- Numeric id resolves, abbreviation absent or itself unmapped -> proceed
  on the numeric resolution alone. This is the real, current SF/LAR
  state and now resolves cleanly with **zero abbreviation-scheme rows
  required at all**.
- Numeric id resolves, abbreviation present and mapped, both agree ->
  proceed exactly as if the abbreviation had never been supplied.
- Numeric id resolves, abbreviation present and mapped, but resolves to
  a **different** canonical team -> a new quarantine classification,
  `team_identity_conflict` (migration `20260913180000_player_identity_quarantine_team_conflict.sql`,
  applied live and verified: an additive widening of the existing
  `conflict_type` check constraint, no column added, no existing value
  touched) -- never silently trusts either signal.

**11 new tests** across `test_player_identity_activation.py` (4:
numeric-alone resolves the real SF@LAR shape; an unmapped abbreviation
is not a conflict; a matching abbreviation changes nothing; a
conflicting abbreviation quarantines as `team_identity_conflict`) and
`test_msf_postgame_worker.py` (1, the critical end-to-end proof: a
genuinely unseen player whose team has **only** a numeric-scheme row --
the exact real SF/LAR state -- is safely **created**, not quarantined;
before this hardening, this exact scenario would have quarantined every
such player). `test_player_identity_activation_gate_b_replay.py` and
the worker's own call site (`_finish_processing_completed_game`) updated
to pass `provider_team_id=line.provider_team_id,
raw_team_abbreviation=line.team` -- the real, hardened argument shape.

## 2. Cache/rate-aware call control

**New pure helpers** (`app/workers/msf_call_control.py`):
`parse_cache_control_max_age` (tolerant of MSF's real observed header
shape, `"no-transform, max-age=10800"`), `parse_retry_after_seconds`
(both the common integer-seconds form and the RFC 7231 HTTP-date form),
`cache_aware_next_check_at` and `retry_after_aware_next_check_at` (each:
`next_check_at(now)`, **extended, never shortened**, when a real signal
says to wait longer). With no signal present, both are byte-identical
to the pre-hardening `next_check_at` -- a strict, backward-compatible
extension. 12 new pure-function tests.

**`app/workers/msf_postgame_worker.py`**:
- `BoxscoreFetchResult` gains `cache_max_age_seconds`/`retry_after_seconds`
  (both `None` unless a real header was actually observed and parsed).
- `_default_fetch_boxscore` now handles 429 **separately** from the
  5xx/network bounded local-retry policy (rule 3's explicit requirement)
  -- a 429 gives up for that tick immediately (retrying instantly into
  the same rate limit is pointless) and captures `Retry-After`; 5xx and
  transport errors are completely unaffected, still using the existing
  bounded local-retry loop. A `status="success"` response's real
  `Cache-Control` is parsed into `cache_max_age_seconds`.
- The not-COMPLETED branch now schedules via `cache_aware_next_check_at`;
  the transient-failure branch now schedules via
  `retry_after_aware_next_check_at`. **Neither `HARD_CAP_ATTEMPTS` nor
  `attempt_count` semantics changed in any way** -- these functions only
  ever affect *when* an already-budgeted check happens, never whether
  one happens or how many total checks a game gets. The existing
  "already captured/confirmed games never call again" and atomic-claim
  guarantees are untouched.

**6 new tests directly against `_default_fetch_boxscore` itself**
(`test_msf_postgame_worker_default_fetch.py`, respx-mocking httpx's
transport -- the same technique this codebase already uses to test every
other adapter's fetch function, zero real network egress): a real
`Cache-Control` header is captured correctly; no header leaves it
`None`; a 429 captures `Retry-After` and consumes **zero** local
retries (exactly one request); a 429 with no header leaves it `None`;
a 5xx still uses the full 3-attempt bounded local-retry loop, completely
unaffected; a 401 escalates permanent immediately, no Retry-After
parsing attempted. **4 new tests at the worker-orchestration level**
proving the scheduling itself: a 3h `Cache-Control` extends the next
not-ready check to 3h (not the default 1h); a 60s one still floors at
the default 1h; a 2h `Retry-After` extends the next transient-retry
check to 2h; a 30s one still floors at the default 1h.

## 3. Zero-cost replay, re-run against the hardened path

`tests/test_msf_postgame_worker_gate_b_replay.py` and
`tests/test_player_identity_activation_gate_b_replay.py` both re-run
unmodified in logic (only the call-site argument shape updated to the
new signature) against the real, already-preserved NE@SEA fixture:

- **69/69 real players still resolve.**
- **Team resolution now runs through the numeric-first path** (every
  one of these 69 players resolves via Rule B reuse before team
  resolution is ever reached -- proven structurally, since no route is
  registered for `team_provider_ids` at all in either replay; the
  numeric-first code path is separately, directly proven by the new
  synthetic worker-level test above, which exercises exactly the branch
  these 69 real players never need).
- **Zero duplicates, zero false quarantines, zero new players** -- same
  structural proof as before (no player/quarantine-creation route
  registered at all).
- **Zero provider calls** -- the injected `fetch_boxscore` returns the
  real fixture directly; `_default_fetch_boxscore` is never invoked.

## 4. Full suite

**858/858 passing** (828 baseline + 30 new: 3 adapter, 4 identity-
activation hardening + 1 worker-level numeric-team proof, 12 call-control
pure-function, 6 `_default_fetch_boxscore` header-parsing, 4 worker
scheduling-hint), zero regressions. Live security/performance advisors
re-checked post-migration: identical shape to before -- the migration
only widened an existing check constraint's IN-list, no new
column/index/table, no new finding of any kind.

## SF@LAR readiness -- NOW FULLY READY for exactly one live execution

Re-checked live against dev after this pass's changes:

| Requirement | Status |
|---|---|
| Canonical game + MSF game id (`163542`) | READY (unchanged from prior pass) |
| SF/LAR MSF **numeric** team identity | READY -- SF=`78`, LAR=`77`, confirmed live |
| SF/LAR MSF **abbreviation** team identity | **No longer required** -- the numeric-first hardening this pass built removes this dependency entirely, not by backfilling it |
| Season resolution for "today" | READY -- the 2026 `seasons` row (`2026-09-04`–`2027-02-14`) covers 2026-09-13, resolving `"2026-2027-regular"`, the confirmed real MSF season string |
| Permanent worker code, numeric-first hardened | READY -- built and proven this pass (zero-cost replay + dedicated numeric-team synthetic proof) |
| Cache/rate-aware scheduling | READY -- built and proven this pass |
| `game_postgame_ingestion_state` row for this game | Still does not exist yet -- not a blocker, the worker creates and promotes it automatically on its first invocation (kickoff was 2026-09-11 00:35 UTC, already well past `kickoff+3h30m`, so it will be immediately eligible) |

**No remaining blocker is known.** The one gap the prior pass disclosed
(missing abbreviation-scheme rows) is resolved architecturally, not
patched -- SF and LAR need no new data at all under the hardened design.
Authorization for the first live call is still Mac's explicit decision,
not made or assumed here.

## Out of scope, exactly as instructed

No MySportsFeeds call was made. No Sunday enablement. No staging or
production changes. No Context Intelligence. No recommendation changes.
