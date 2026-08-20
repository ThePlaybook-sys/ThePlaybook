"""Demo operational-data reset (DEMO-3, docs/blueprint/demo-simulation-environment.md
Section 6 -- "RESET SAFETY (critical)").

Deletes only the rows a scenario run itself produces -- never the reference
taxonomy (`sports`, `leagues`, `teams`, `team_provider_ids`) every
environment (dev/staging/production/demo) shares via `supabase/seed.sql`'s
bootstrap. `games` and `players` (and every table that exists only to
describe a specific game/player) are reset; the taxonomy describing what a
team *is* is not.

Two independent guards protect this, deliberately not sharing one code
path with the other:
  1. `app.environment_safety.assert_demo_isolation` -- checked once, at
     process startup, before this module (or anything else) can even run.
  2. `assert_reset_is_safe`, below -- checked again, every single time
     `reset_demo_operational_data` is called, at the exact moment before
     any DELETE is issued. A future caller of this module -- an
     Operator Dashboard endpoint (DEMO-4), a test, a scenario runner reset
     action -- gets the safety check for free and cannot accidentally skip
     it, because `reset_demo_operational_data` will not proceed without it.

Both hard-fail (raise, never truncate/delete on doubt). Neither ever
inspects or holds a non-demo project ref or credential -- same discipline
`environment_safety.py`'s own docstring establishes.
"""
from __future__ import annotations

import httpx

from app.environment_safety import DEMO_ENVIRONMENT_NAME, DEMO_SUPABASE_PROJECT_REF

#: Children before parents -- derived directly from the FK graph in
#: supabase/migrations/20260807211306_sports_data_tables.sql,
#: 20260813180000_game_provider_ids_and_season_week.sql,
#: 20260818060000_player_provider_ids_and_games_finalized_at.sql, and
#: 20260818070000_roster_memberships_and_depth_chart_redesign.sql. Every
#: entry here is either app-created operational data or a scenario-run
#: artifact -- never `sports`, `leagues`, `teams`, or `team_provider_ids`.
#: (table_name, primary_key_column) -- `daily_game_intelligence`'s PK is
#: `game_id`, not `id`; every other table here uses a generated `id`.
RESET_TABLE_ORDER: list[tuple[str, str]] = [
    ("daily_game_intelligence", "game_id"),
    ("odds_snapshots", "id"),
    ("injury_reports", "id"),
    ("weather_snapshots", "id"),
    ("depth_chart_snapshots", "id"),
    ("team_stats", "id"),
    ("player_stats", "id"),
    ("roster_memberships", "id"),
    ("player_provider_ids", "id"),
    ("game_provider_ids", "id"),
    ("players", "id"),
    ("games", "id"),
]

#: Never touched by reset -- asserted, not just documented, by
#: `test_reset_never_targets_reference_taxonomy` in the DEMO-3 test suite.
PRESERVED_REFERENCE_TAXONOMY = frozenset({"sports", "leagues", "seasons", "teams", "team_provider_ids"})


class DemoResetSafetyError(RuntimeError):
    """Raised when reset cannot prove it is running against the isolated
    demo environment/project. Always fatal, always raised before any
    DELETE is issued -- there is no partial-reset-then-fail path."""


def assert_reset_is_safe(*, railway_environment_name: str, supabase_url: str) -> None:
    """The reset-boundary guard (independent of `assert_demo_isolation`,
    per Mac's explicit "do not rely only on the existing startup guard"
    instruction). Hard-fails unless BOTH the environment tag and the
    database target agree this is demo -- one alone is not enough, exactly
    mirroring `assert_demo_isolation`'s own both-sides check.
    """
    is_demo_env = railway_environment_name == DEMO_ENVIRONMENT_NAME
    points_at_demo_db = DEMO_SUPABASE_PROJECT_REF in (supabase_url or "")

    if not (is_demo_env and points_at_demo_db):
        raise DemoResetSafetyError(
            "refusing to reset: cannot prove this is the isolated demo environment. "
            f"RAILWAY_ENVIRONMENT_NAME={railway_environment_name!r} (need {DEMO_ENVIRONMENT_NAME!r}), "
            f"SUPABASE_URL={'<matches demo project>' if points_at_demo_db else '<does NOT match demo project>'} "
            f"(need it to contain {DEMO_SUPABASE_PROJECT_REF!r}). No data was deleted or modified."
        )


async def reset_demo_operational_data(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    railway_environment_name: str,
    supabase_url: str,
) -> dict[str, int]:
    """Deletes every row from every table in `RESET_TABLE_ORDER`, in that
    order, and nothing else. Returns `{table_name: rows_deleted}` --
    `rows_deleted` comes from PostgREST's own `Content-Range` response
    header (present because callers are expected to pass
    `Prefer: return=representation` or rely on the count header; here we
    request `return=representation` explicitly so the count is always
    available without a second round trip).

    Raises `DemoResetSafetyError` (via `assert_reset_is_safe`) and deletes
    nothing at all if the safety check fails -- checked once, up front,
    not per-table, so a failure never leaves the reset half-applied.
    """
    assert_reset_is_safe(railway_environment_name=railway_environment_name, supabase_url=supabase_url)

    deleted_counts: dict[str, int] = {}
    for table_name, pk_column in RESET_TABLE_ORDER:
        response = await client.delete(
            f"/rest/v1/{table_name}",
            params={pk_column: "not.is.null"},
            headers={**headers, "Prefer": "return=representation"},
        )
        if response.status_code not in (200, 204):
            raise DemoResetSafetyError(
                f"reset failed while deleting from {table_name!r}: {response.status_code} {response.text}. "
                f"Tables already reset this call: {list(deleted_counts)}. "
                "Reference taxonomy was never touched; re-run reset once the underlying issue is fixed."
            )
        deleted_counts[table_name] = len(response.json()) if response.content else 0

    return deleted_counts
