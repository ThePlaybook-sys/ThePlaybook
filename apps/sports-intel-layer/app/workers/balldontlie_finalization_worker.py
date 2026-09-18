"""BALLDONTLIE canonical finalization (2026-09-18, HQ-authorized
"CONDITIONAL FINALIZATION", classification A).

**The gap this closes.** With MySportsFeeds paused there is no active path
from a completed game to `games.final_score`/`finalized_at`, and therefore
none to grading or the calibration ledger. The daily SportsDataIO Schedule
refresh supplies terminal *status* at no new cost and cannot supply numbers:
its live-captured row schema carries no score field at all. This worker is
the numbers.

**Why BALLDONTLIE and not SportsDataIO.** The SportsDataIO postgame audit
(2026-09-18) classified that provider's quota/billing state as UNKNOWN and
stopped. BALLDONTLIE's `nfl/v1/games` is a free-tier endpoint that has
answered 200 with the current key twice, and one of those responses is
persisted in `game_events` and contains a real, completed 2026 game with a
real final score. That capture is the evidence base for everything below.

**One call per week, not one per game.** `fetch_week_final_scores` is bulk:
a 16-game NFL Sunday resolves in a single request. This worker groups its
eligible games by (season, week) and issues one fetch per distinct week,
then fans the result out across every game in that week. Converting a bulk
capability into per-game calls is explicitly forbidden by the directive, and
the provider's 5 requests/minute limit would punish it anyway.

**Cost contract, and how each zero is actually achieved:**

- *Pre-kickoff game*: 0 calls. Never enters the candidate set -- the read
  filters on `scheduled_start <= now`.
- *Finalized game*: 0 calls. Filtered out by `finalized_at is null` in the
  same read, so it is never a candidate and never contributes a week.
- *Missing provider mapping*: 0 calls. Identity is resolved AFTER the fetch,
  from the response itself, so a missing mapping costs nothing; and a game
  that cannot be resolved is skipped, never guessed.
- *No eligible game at all*: 0 calls. The fetch loop runs over weeks derived
  from candidates, so an empty candidate set issues no request whatsoever --
  this is what makes a Tuesday tick free.
- *Transient provider failure*: bounded. The per-game state row records
  `error_classification='transient'` and a backed-off
  `next_eligible_attempt_at`, both durable, so the next process honours them.
- *Permanent provider failure*: stops. The row goes to
  `capture_failed_permanent`, which the claim's WHERE clause can never match
  again.
- *Duplicate/concurrent ticks*: cannot double-spend. Each game is claimed
  atomically before any work, and `finalize_game` carries its own
  `finalized_at=is.null` server-side filter, so the write is idempotent even
  if two processes somehow both reached it.

**Identity is exact, never fuzzy.** A provider row is matched to a canonical
game on (kickoff timestamp, home-team abbreviation). That is not a guess: the
persisted Week 1 capture matches all 16 canonical games on exactly this key
with zero timestamp tolerance -- the same 0.00-minute agreement the
SportsDataIO reconciliation measured independently. `_HOME_TEAM_ALIASES`
handles the one abbreviation divergence the Week 1 recovery documented rather
than leaving it to luck.

**The score is copied.** `home_score`/`away_score` are the provider's own
whole-game fields, written into `games.final_score` unchanged. Nothing is
summed, inferred, or reconstructed, and a game is only written at all when
the provider's own machine-readable `status_state` says `final`.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from app.adapters.errors import ProviderError, ProviderRateLimitError, ProviderUnavailableError
from app.adapters.models import FinalScoreLine
from app.adapters.providers.balldontlie import BallDontLieFinalScoreAdapter
from app.persistence.game_events import write_raw_game_events
from app.persistence.game_postgame_ingestion_state import (
    IngestionStateError,
    claim_game_for_capture,
    ensure_scheduled_row,
    promote_due_scheduled_row,
    update_ingestion_state,
)
from app.persistence.games import GamesQueryError, finalize_game

_logger = logging.getLogger("sports-intel-layer.workers.balldontlie_finalization")

PROVIDER_NAME = "balldontlie"

#: How far back to look for unfinalized completed games. Matches
#: `app.workers.postgame_worker._RECONCILIATION_LOOKBACK_DAYS` exactly, and
#: for the same reason -- a game finalized just past the 72h reconciliation
#: horizon must still be reachable, without scanning the season's history
#: forever. Deliberately the same number rather than a new one: two postgame
#: paths disagreeing about how far back "recent" reaches is a bug waiting for
#: a quiet week to happen in.
LOOKBACK_DAYS = 4

#: How long after kickoff before the first finalization check. An NFL game
#: runs about three hours; checking at kickoff + 0 would spend a call to be
#: told `in_progress`, every tick, for three hours, for every game.
FIRST_CHECK_AFTER_KICKOFF_HOURS = 3

#: Backoff after a transient failure or a still-in-progress reading. Chosen to
#: sit comfortably inside the provider's 5-requests-per-minute limit even if
#: every game in a Sunday slate backs off onto the same instant, since the
#: fetch is per-week rather than per-game.
RETRY_BACKOFF_MINUTES = 20

#: Bounded retry. After this many attempts a game stops costing calls and is
#: left for a human, rather than retrying until the lookback window drops it.
#: Enforced against the DURABLE `attempt_count`, which the database trigger
#: forbids from decreasing -- so a container restart cannot hand the budget
#: back, which was the whole defect this pass exists to fix.
MAX_ATTEMPTS = 6

#: The one real abbreviation divergence between BALLDONTLIE and this project's
#: canonical `games.home_team` text, CONFIRMED from the 2026-09-11 Week 1
#: capture: BALLDONTLIE writes `WSH` for the Washington Commanders where the
#: canonical row says `WAS`. (`JAX` was also flagged at the time but matches
#: canonically -- checked, not assumed.) Mapped explicitly rather than
#: normalized by a fuzzy rule: an alias table is auditable and a similarity
#: score is not, and HQ's directive forbids fuzzy game matching outright.
_HOME_TEAM_ALIASES = {"WSH": "WAS"}


class BallDontLieFinalizationError(Exception):
    """Raised for failures this worker cannot attribute to one game."""


@dataclass
class FinalizationResult:
    status: str = "success"  # "success" | "partial" | "failed" | "paused"
    games_considered: int = 0
    weeks_fetched: list[str] = field(default_factory=list)
    provider_requests: int = 0
    finalized: list[str] = field(default_factory=list)
    not_final_yet: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    already_finalized: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    error: str | None = None


def _enabled() -> bool:
    """Explicit-opt-in gate, matching `MASTER_REFRESH_ENABLED`'s polarity
    rather than `MSF_POSTGAME_ENABLED`'s. Deliberate: a removed flag must
    never be able to start spending provider calls on its own."""
    return os.environ.get("BALLDONTLIE_FINALIZATION_ENABLED", "").strip().lower() == "true"


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


def _canonical_home(abbreviation: str) -> str:
    return _HOME_TEAM_ALIASES.get(abbreviation, abbreviation)


def _match_key(scheduled_start: datetime, home_team: str) -> tuple[datetime, str]:
    """The exact identity key, used identically on both sides of the match so
    a canonical row and a provider row can only ever agree by genuinely being
    the same fixture. Normalized to UTC because one side arrives from
    PostgREST and the other from the provider, and two identical instants in
    different offsets must not read as different games."""
    return (scheduled_start.astimezone(timezone.utc), _canonical_home(home_team))


async def _read_candidates(
    client: httpx.AsyncClient, headers: dict, *, now: datetime
) -> list[dict]:
    """Every canonical game that has kicked off, is not yet finalized, and is
    inside the lookback window. All three bounds are enforced in the query, so
    an oversized candidate set can never reach the fetch loop and turn into
    provider calls."""
    window_start = now - timedelta(days=LOOKBACK_DAYS)
    latest_kickoff = now - timedelta(hours=FIRST_CHECK_AFTER_KICKOFF_HOURS)
    response = await client.get(
        "/rest/v1/games",
        params={
            "select": "id,scheduled_start,home_team,away_team,week,season_id,status",
            "sport": "eq.nfl",
            "finalized_at": "is.null",
            "scheduled_start": [
                f"gte.{window_start.isoformat()}",
                f"lte.{latest_kickoff.isoformat()}",
            ],
            "week": "not.is.null",
            "order": "scheduled_start.asc,id.asc",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise BallDontLieFinalizationError(
            f"failed to read finalization candidates: {response.status_code} {response.text}"
        )
    return response.json()


async def _claim(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, now: datetime
) -> dict | None:
    """Ensures a durable state row exists, promotes it if due, and claims it.

    The three steps are the existing generic foundation's own chain, called
    with `provider_name=balldontlie` -- no new locking primitive, no new
    table, and no bespoke claim logic for this provider.
    """
    await ensure_scheduled_row(
        client,
        headers,
        game_id=game_id,
        first_eligible_at=now,
        provider_name=PROVIDER_NAME,
    )
    await promote_due_scheduled_row(
        client, headers, game_id=game_id, now=now, provider_name=PROVIDER_NAME
    )
    return await claim_game_for_capture(
        client, headers, game_id=game_id, now=now, provider_name=PROVIDER_NAME
    )


async def _release(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    state: str,
    now: datetime,
    attempt_count: int,
    retry_in_minutes: int | None = None,
    **extra,
) -> None:
    """Returns a claimed row to a resting state. Always called, on every
    branch -- a row left in `capture_in_progress` would be unclaimable
    forever, which is the same class of bug as the process-local dict."""
    fields: dict = {"state": state, "attempt_count": attempt_count, "last_attempt_at": now.isoformat()}
    if retry_in_minutes is not None:
        fields["next_eligible_attempt_at"] = (now + timedelta(minutes=retry_in_minutes)).isoformat()
    fields.update(extra)
    await update_ingestion_state(
        client, headers, game_id=game_id, provider_name=PROVIDER_NAME, **fields
    )


async def run_balldontlie_finalization(
    *,
    supabase_client: httpx.AsyncClient,
    balldontlie_client: httpx.AsyncClient | None = None,
    balldontlie_api_key: str | None = None,
    now: datetime | None = None,
    adapter: BallDontLieFinalScoreAdapter | None = None,
    season: int = 2026,
) -> FinalizationResult:
    """Runs one finalization cycle. Never raises -- same finite-job shape as
    every other worker here, so a cron exits 0 on a normal empty cycle."""
    if not _enabled():
        # The gate precedes every query and every request, so a paused cycle
        # makes no call of any kind -- not to the provider, not to Supabase.
        return FinalizationResult(status="paused")

    now = now or datetime.now(timezone.utc)
    headers = _auth_headers()
    result = FinalizationResult()

    try:
        candidates = await _read_candidates(supabase_client, headers, now=now)
    except BallDontLieFinalizationError as exc:
        return FinalizationResult(status="failed", error=str(exc))

    result.games_considered = len(candidates)
    if not candidates:
        return result

    # Claim first, fetch second. A game nobody could claim contributes no week,
    # so a slate of already-claimed or backed-off games costs zero requests.
    claimed: dict[str, dict] = {}
    for game in candidates:
        try:
            row = await _claim(supabase_client, headers, game_id=game["id"], now=now)
        except IngestionStateError as exc:
            result.failures.append(f"{game['id']}: claim failed: {exc}")
            continue
        if row is None:
            continue
        if row.get("attempt_count", 0) >= MAX_ATTEMPTS:
            await _release(
                supabase_client,
                headers,
                game_id=game["id"],
                state="capture_failed_permanent",
                now=now,
                attempt_count=row.get("attempt_count", 0),
                error_classification="permanent",
                quarantine_reason=f"exceeded MAX_ATTEMPTS={MAX_ATTEMPTS}",
            )
            result.failures.append(f"{game['id']}: attempt budget exhausted")
            continue
        claimed[game["id"]] = {"game": game, "state": row}

    if not claimed:
        return result

    if adapter is None:
        if balldontlie_client is None or balldontlie_api_key is None:
            return FinalizationResult(status="failed", error="no BALLDONTLIE adapter or client configured")
        adapter = BallDontLieFinalScoreAdapter(
            client=balldontlie_client, api_key=balldontlie_api_key
        )

    weeks = sorted({entry["game"]["week"] for entry in claimed.values()})
    lines_by_key: dict[tuple[datetime, str], FinalScoreLine] = {}
    raw_by_week: dict[int, list] = {}
    failed_weeks: set[int] = set()

    for week in weeks:
        try:
            response = await adapter.fetch_week_final_scores(season=season, week=week)
        except (ProviderRateLimitError, ProviderUnavailableError) as exc:
            _logger.warning("transient BALLDONTLIE failure for week %s: %s", week, exc)
            failed_weeks.add(week)
            result.failures.append(f"week {week}: transient provider failure: {exc}")
            continue
        except ProviderError as exc:
            _logger.error("permanent BALLDONTLIE failure for week %s: %s", week, exc)
            failed_weeks.add(week)
            result.failures.append(f"week {week}: provider failure: {exc}")
            continue
        finally:
            # Counted before the outcome is known: a request that was sent and
            # then failed has still been spent.
            result.provider_requests += 1

        result.weeks_fetched.append(str(week))
        raw_by_week[week] = [line.model_dump(mode="json") for line in response.value]
        for line in response.value:
            lines_by_key[_match_key(line.scheduled_start, line.home_team)] = line

    for game_id, entry in claimed.items():
        game = entry["game"]
        attempts = entry["state"].get("attempt_count", 0) + 1
        week = game["week"]

        if week in failed_weeks:
            classification = "transient"
            await _release(
                supabase_client,
                headers,
                game_id=game_id,
                state="capture_failed_transient",
                now=now,
                attempt_count=attempts,
                retry_in_minutes=RETRY_BACKOFF_MINUTES,
                error_classification=classification,
                last_error=f"week {week} fetch failed",
            )
            continue

        key = _match_key(_parse_ts(game["scheduled_start"]), game["home_team"])
        line = lines_by_key.get(key)
        if line is None:
            # No exact match. Never guessed, never fuzzily matched -- the game
            # simply is not finalizable from this response, and says so.
            result.unresolved.append(game_id)
            await _release(
                supabase_client,
                headers,
                game_id=game_id,
                state="capture_failed_transient",
                now=now,
                attempt_count=attempts,
                retry_in_minutes=RETRY_BACKOFF_MINUTES,
                error_classification="transient",
                last_error="no exact (kickoff, home_team) match in provider response",
            )
            continue

        if not line.is_final or line.home_score is None or line.away_score is None:
            # Still running, or final-but-scoreless. Both are real information
            # and neither is a failure; the game goes back to resting state and
            # is checked again after the backoff. This is the branch that stops
            # a first-quarter 3-0 from being frozen as a result.
            result.not_final_yet.append(game_id)
            await _release(
                supabase_client,
                headers,
                game_id=game_id,
                state="eligible_for_postgame_check",
                now=now,
                attempt_count=attempts,
                retry_in_minutes=RETRY_BACKOFF_MINUTES,
                last_error=None,
                error_classification=None,
            )
            continue

        # Raw evidence BEFORE the canonical write, so no final score can ever
        # exist in this system without the provider payload that justifies it.
        try:
            await write_raw_game_events(
                game_id=game_id,
                provider_name=PROVIDER_NAME,
                raw_response={
                    "endpoint": "https://api.balldontlie.io/nfl/v1/games",
                    "request_params": {"seasons[]": str(season), "weeks[]": str(week)},
                    "captured_at": now.isoformat(),
                    "matched_provider_game_id": line.provider_game_id,
                    "week_payload": raw_by_week.get(week, []),
                },
                now=now,
            )
        except Exception as exc:  # noqa: BLE001 -- evidence failure must not finalize
            result.failures.append(f"{game_id}: raw evidence write failed: {exc}")
            await _release(
                supabase_client,
                headers,
                game_id=game_id,
                state="capture_failed_transient",
                now=now,
                attempt_count=attempts,
                retry_in_minutes=RETRY_BACKOFF_MINUTES,
                error_classification="transient",
                last_error=f"raw evidence write failed: {exc}",
            )
            continue

        try:
            written = await finalize_game(
                supabase_client,
                headers,
                game_id=game_id,
                # COPIED. Same {"home": int, "away": int} shape the existing
                # canonical rows already use -- checked against dev's own
                # Week 1 values, not invented here.
                final_score={"home": line.home_score, "away": line.away_score},
                finalized_at=now,
            )
        except GamesQueryError as exc:
            result.failures.append(f"{game_id}: finalize failed: {exc}")
            await _release(
                supabase_client,
                headers,
                game_id=game_id,
                state="capture_failed_transient",
                now=now,
                attempt_count=attempts,
                retry_in_minutes=RETRY_BACKOFF_MINUTES,
                error_classification="transient",
                last_error=str(exc),
            )
            continue

        if written:
            result.finalized.append(game_id)
        else:
            # Someone else finalized it between our candidate read and now.
            # Not an error -- the idempotency guard doing its job.
            result.already_finalized.append(game_id)

        await _release(
            supabase_client,
            headers,
            game_id=game_id,
            state="confirmed_complete",
            now=now,
            attempt_count=attempts,
            # `captured_at` rather than `raw_capture_id`: the evidence writer
            # returns a row count, not an id, and pointing the FK at a
            # fabricated value would be worse than leaving it null. The
            # evidence is found by (game_id, provider_name) in `game_events`.
            captured_at=now.isoformat(),
            error_classification=None,
            last_error=None,
        )

    if result.failures or result.unresolved:
        result.status = "partial"
    return result


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


__all__ = [
    "BallDontLieFinalizationError",
    "FinalizationResult",
    "LOOKBACK_DAYS",
    "MAX_ATTEMPTS",
    "PROVIDER_NAME",
    "RETRY_BACKOFF_MINUTES",
    "run_balldontlie_finalization",
]
