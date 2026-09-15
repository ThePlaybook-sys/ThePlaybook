"""MSF -> canonical game finalization (2026-09-15, HQ-authorized "CANONICAL
SCHEDULE + FINALIZATION HARDENING").

**The gap this closes.** `mark_game_finalized`/`update_final_score` have existed
since Phase 3E-8, but their only caller was `app.workers.postgame_worker` -- the
*SportsDataIO* path, which derives `final_score` from `TeamGameStats` and relies on
a SportsDataIO Schedule refresh to have already moved `games.status` to `final`.
The MySportsFeeds postgame path captures a complete boxscore, marks
`game_postgame_ingestion_state.state = 'confirmed_complete'`, and then stops --
it never finalized the canonical game. So 16 real Week 1 games sat at
`status='scheduled'`/`'live'` with null `final_score`/`finalized_at` while their
real final scores were already durably persisted. SportsDataIO finalization was
assumed; MSF completion was never wired to it.

This module is that wiring, built as permanent architecture rather than a one-off
backfill: every future MSF `confirmed_complete` observation finalizes its canonical
game by the same path the Week 1 backfill uses.

**Zero provider calls, by construction.** Everything here reads
already-persisted rows -- `game_postgame_ingestion_state` and the
`game_events.raw_payload` it points at via `raw_capture_id`. No adapter is
imported and no provider client is constructed anywhere in this module.

**Deterministic canonical resolution, never inferred.**
`game_postgame_ingestion_state.game_id` IS the canonical game id, and
`raw_capture_id` IS the exact capture that justified the `confirmed_complete`
state. There is no team/date matching, no payload-shape scanning, and no guessing
about which capture belongs to which game.

**Authority rules, all refusals rather than guesses:**
  - only `state = 'confirmed_complete'` is considered;
  - the capture's own `body.game.playedStatus` must read `COMPLETED` --
    a non-completed observation NEVER finalizes anything, whatever the state row
    says;
  - both `homeScoreTotal` and `awayScoreTotal` must be present and integral --
    a one-sided or unparseable score is skipped with a reason, never
    half-written (the same "never a partial, one-sided score" rule
    `postgame_worker` already follows);
  - a score is only ever copied, never derived, defaulted or invented.

**Idempotent, and duplicate captures cannot double-process.** Repeated captures
for one game are collapsed to a single canonical observation before anything is
written (`resolve_canonical_capture`, mirroring the observation-identity pattern
`app.context_intelligence.observation_identity.resolve_canonical_observation`
established in the ai-orchestrator service -- duplicated rather than imported,
matching this repo's standing separate-deployables convention, e.g.
`app.persistence.games.find_previous_final_game`'s own note). The write itself is
then guarded at the database level: `finalize_game` PATCHes only rows whose
`finalized_at` is still null, so a second run updates nothing at all rather than
overwriting the original finalization moment.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from app.persistence.games import GamesQueryError, finalize_game
from app.persistence.game_events import read_game_event
from app.persistence.game_postgame_ingestion_state import read_confirmed_complete_states

_logger = logging.getLogger(__name__)

#: The only `playedStatus` that authorizes finalization. Anything else --
#: including an in-progress or postponed game whose state row somehow reads
#: complete -- is refused, not interpreted.
COMPLETED_PLAYED_STATUS = "COMPLETED"

#: The provider whose postgame observations this module finalizes from.
MSF_PROVIDER_NAME = "mysportsfeeds"


@dataclass(frozen=True)
class FinalScore:
    home: int
    away: int

    def to_json(self) -> dict:
        """The exact `games.final_score` shape `app.workers.postgame_worker`
        already writes -- one shape for both providers, never a second dialect."""
        return {"home": self.home, "away": self.away}


@dataclass(frozen=True)
class FinalizationOutcome:
    game_id: str
    #: "finalized" | "already_finalized" | "skipped"
    status: str
    final_score: dict | None = None
    #: Present only for "skipped" -- the specific, stable reason.
    reason: str | None = None


@dataclass
class FinalizationResult:
    considered: int = 0
    finalized: int = 0
    already_finalized: int = 0
    skipped: int = 0
    duplicate_captures_collapsed: int = 0
    outcomes: list[FinalizationOutcome] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def _coerce_score(value: object) -> int | None:
    """MSF reports scores as integers, but a JSON round-trip can present them as
    strings. Accepts either; refuses anything else (including `None`, a float
    with a fractional part, or a bool) rather than coercing it into a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def is_completed_observation(payload: dict) -> bool:
    """True only when the capture itself says the game is COMPLETED. The
    ingestion state row is NOT taken as sufficient evidence on its own -- the
    payload is the observation, the state row is only bookkeeping about it."""
    body = payload.get("body")
    if not isinstance(body, dict):
        return False
    game = body.get("game")
    if not isinstance(game, dict):
        return False
    return game.get("playedStatus") == COMPLETED_PLAYED_STATUS


def extract_final_score(payload: dict) -> FinalScore | None:
    """Both sides, or nothing. Returns `None` when the payload carries no usable
    `body.scoring.homeScoreTotal`/`awayScoreTotal` pair -- never a one-sided or
    partially-parsed score."""
    body = payload.get("body")
    if not isinstance(body, dict):
        return None
    scoring = body.get("scoring")
    if not isinstance(scoring, dict):
        return None
    home = _coerce_score(scoring.get("homeScoreTotal"))
    away = _coerce_score(scoring.get("awayScoreTotal"))
    if home is None or away is None:
        return None
    return FinalScore(home=home, away=away)


def resolve_canonical_capture(state_rows: list[dict]) -> tuple[list[dict], int]:
    """Collapses repeated captures for the same canonical game down to one.

    Returns `(canonical_rows, collapsed_count)`. The canonical row for a game is
    the most recently captured one (`captured_at`, falling back to `updated_at`
    then `created_at` when a timestamp is missing), with the row `id` as the final
    deterministic tie-break so the choice is never arbitrary between two rows
    sharing a timestamp. `collapsed_count` is how many rows were dropped as
    duplicates -- reported rather than silently discarded, so a duplicate-capture
    condition stays visible."""
    by_game: dict[str, list[dict]] = {}
    for row in state_rows:
        by_game.setdefault(row["game_id"], []).append(row)

    canonical: list[dict] = []
    collapsed = 0
    for game_id, rows in sorted(by_game.items()):
        if len(rows) > 1:
            collapsed += len(rows) - 1
        canonical.append(
            max(
                rows,
                key=lambda r: (
                    r.get("captured_at") or r.get("updated_at") or r.get("created_at") or "",
                    str(r.get("id") or ""),
                ),
            )
        )
    return canonical, collapsed


async def finalize_completed_games(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    provider_name: str = MSF_PROVIDER_NAME,
    now: datetime | None = None,
    limit: int = 500,
) -> FinalizationResult:
    """Finalizes every canonical game with a `confirmed_complete` MSF observation
    whose capture genuinely reads COMPLETED and carries both scores.

    Makes ZERO provider calls -- reads only `game_postgame_ingestion_state` and
    the `game_events` rows it points at. Safe to re-run: the write is guarded on
    `finalized_at is null`, so a second run reports `already_finalized` and
    changes nothing."""
    now = now or datetime.now(timezone.utc)
    result = FinalizationResult()

    state_rows = await read_confirmed_complete_states(
        client, headers, provider_name=provider_name, limit=limit
    )
    canonical_rows, collapsed = resolve_canonical_capture(state_rows)
    result.duplicate_captures_collapsed = collapsed
    result.considered = len(canonical_rows)

    for row in canonical_rows:
        game_id = row["game_id"]
        capture_id = row.get("raw_capture_id")
        if not capture_id:
            result.skipped += 1
            result.outcomes.append(
                FinalizationOutcome(game_id=game_id, status="skipped", reason="no_raw_capture_id")
            )
            continue

        try:
            capture = await read_game_event(event_id=capture_id)
        except Exception as exc:  # noqa: BLE001 -- isolate one game; never abort the batch
            result.failures.append(f"{game_id}: capture read failed: {exc}")
            continue

        payload = (capture or {}).get("raw_payload")
        if not isinstance(payload, dict):
            result.skipped += 1
            result.outcomes.append(
                FinalizationOutcome(game_id=game_id, status="skipped", reason="capture_missing_or_unreadable")
            )
            continue

        if not is_completed_observation(payload):
            result.skipped += 1
            result.outcomes.append(
                FinalizationOutcome(game_id=game_id, status="skipped", reason="observation_not_completed")
            )
            continue

        score = extract_final_score(payload)
        if score is None:
            result.skipped += 1
            result.outcomes.append(
                FinalizationOutcome(game_id=game_id, status="skipped", reason="incomplete_or_unparseable_score")
            )
            continue

        try:
            written = await finalize_game(
                client, headers, game_id=game_id, final_score=score.to_json(), finalized_at=now
            )
        except GamesQueryError as exc:
            result.failures.append(f"{game_id}: finalize failed: {exc}")
            continue

        if written:
            result.finalized += 1
            result.outcomes.append(
                FinalizationOutcome(game_id=game_id, status="finalized", final_score=score.to_json())
            )
        else:
            result.already_finalized += 1
            result.outcomes.append(
                FinalizationOutcome(game_id=game_id, status="already_finalized", final_score=score.to_json())
            )

    _logger.info(
        "canonical_finalization considered=%d finalized=%d already_finalized=%d skipped=%d "
        "duplicates_collapsed=%d failures=%d",
        result.considered,
        result.finalized,
        result.already_finalized,
        result.skipped,
        result.duplicate_captures_collapsed,
        len(result.failures),
    )
    return result


async def run_canonical_finalization(
    *, provider_name: str = MSF_PROVIDER_NAME, limit: int = 500
) -> FinalizationResult:
    """Self-contained entry point: builds its own Supabase client and headers
    from the environment and runs `finalize_completed_games`.

    Exists so `app.main`'s HTTP boundary can invoke finalization without
    reading the Supabase service-role key itself -- the same credential-
    isolation discipline every other `/v1/internal/*` endpoint in this project
    follows (main.py only ever reads `SUPABASE_URL`). Mirrors
    `app.persistence.game_events`' own env-constructed-client pattern.

    Still ZERO provider calls: nothing here reaches past Supabase.
    """
    supabase_url = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(base_url=supabase_url, timeout=60.0) as client:
        return await finalize_completed_games(
            client, headers, provider_name=provider_name, limit=limit
        )
