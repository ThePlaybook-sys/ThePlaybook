"""In-memory fake PostgREST server for DEMO-3's scenario-runner integration
tests (`tests/test_demo_scenario_runner.py`).

Test-only infrastructure -- lives under tests/, never imported by
app/demo/*. It exists because a full scenario run legitimately chains
across every one of Master Refresh's 8 worker entrypoints, several of
which read back a UUID (`games.id`, `players.id`) that an earlier step in
the *same run* just generated -- something a static per-worker respx mock
(as used by tests/test_adapter_injection_seam.py) cannot express, since
that id doesn't exist until the fake actually "inserts" it.

Call-shape coverage here is not a guess: every route this fake implements
was catalogued by directly reading every persistence module and worker
this pipeline touches (schedule.py, games.py, game_identity.py,
team_identity.py, player_identity.py, roster_ingestion.py,
odds_snapshots.py, injury_reports.py, weather_snapshots.py, team_stats.py,
player_stats.py, daily_game_intelligence.py, snapshots.py, seasons.py,
teams.py, odds_game_linking.py, and the three workers' own inline
`_reverse_resolve_*` helpers) before writing a single line of this file.
"""
from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

_clock_counter = itertools.count(1)
_CLOCK_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _fake_now() -> str:
    """A monotonically increasing fake timestamp -- real wall-clock time
    would work too, but this guarantees insertion order is always
    recoverable from an `order=col.desc` query even when a test runs
    faster than the host clock's own resolution. Unbounded (unlike a
    plain 0-59 seconds field): a long-running scenario or a full-suite
    run sharing this module-level counter across many tests can insert
    far more than 60 rows total."""
    return (_CLOCK_EPOCH + timedelta(seconds=next(_clock_counter))).isoformat()


#: Column defaults applied to a freshly-inserted row, merged UNDER the
#: request body (body always wins) -- mirrors a real table's column
#: defaults, so a partial-column upsert (e.g. News Worker's `write_news`
#: writing only `game_id`/`news`) still produces a row where every other
#: column reads back as `None`, exactly like a real Postgres row would.
_TABLE_DEFAULTS: dict[str, dict[str, Any]] = {
    "daily_game_intelligence": {
        "teams": None, "players": None, "odds": None, "props": None, "weather": None,
        "injuries": None, "news": None, "travel": None, "rest": None, "stadium": None,
        "public_betting": None, "sharp_money": None, "last_updated": None,
    },
    "games": {
        "external_provider_id": None, "stadium": None, "season_type": None, "week": None,
        "venue_lat": None, "venue_long": None, "venue_type": None, "finalized_at": None,
        "final_score": None,
    },
}

#: Every table whose primary key is a generated uuid (everything except
#: daily_game_intelligence, whose PK is game_id and is always supplied by
#: the caller).
_GENERATED_ID_TABLES = frozenset(
    {
        "games", "players", "game_provider_ids", "player_provider_ids", "team_provider_ids",
        "odds_snapshots", "injury_reports", "weather_snapshots", "depth_chart_snapshots",
        "roster_memberships", "team_stats", "player_stats",
        "master_refresh_runs",  # Milestone 4.9
    }
)


def _clause_matches(row: dict, clause: str) -> bool:
    """Evaluates one `col.op.value` clause (the shape used inside both a
    top-level `?col=op.value` filter and an `or=(...)` group) against a
    single row."""
    column, op, value = clause.split(".", 2)
    actual = row.get(column)
    if op == "eq":
        return str(actual) == value
    if op == "neq":
        return str(actual) != value
    if op == "lt":
        return actual is not None and str(actual) < value
    if op == "lte":
        return actual is not None and str(actual) <= value
    if op == "gt":
        return actual is not None and str(actual) > value
    if op == "gte":
        return actual is not None and str(actual) >= value
    if op == "in":
        candidates = value.strip("()").split(",") if value.strip("()") else []
        return str(actual) in candidates
    if op == "is" and value == "null":
        return actual is None
    raise NotImplementedError(f"fake_supabase: unsupported filter op {op!r} in clause {clause!r}")


def _row_matches_filter(row: dict, key: str, raw_value: str) -> bool:
    if key == "or":
        # "(col.eq.a,col2.eq.b)" -- OR'd together, no nested groups needed
        # by anything this pipeline issues.
        clauses = raw_value.strip("()").split(",")
        return any(_clause_matches(row, clause) for clause in clauses)
    if raw_value.startswith("not.is.null"):
        return row.get(key) is not None
    return _clause_matches(row, f"{key}.{raw_value}")


class FakeSupabase:
    """One instance = one isolated in-memory Postgres-shaped store, safe to
    reuse across every step of a single scenario run (mirrors the real
    demo Supabase project being one durable target for the whole run) and
    to throw away between tests.
    """

    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}

    def seed(self, table: str, rows: list[dict]) -> None:
        self.tables.setdefault(table, []).extend(row.copy() for row in rows)

    def register_routes(self, base_url: str) -> None:
        import re

        import respx

        respx.route(url__regex=rf"^{re.escape(base_url)}/rest/v1/(?P<table>\w+)(\?.*)?$").mock(
            side_effect=self._handle
        )

    # -- dispatch --

    def _handle(self, request: httpx.Request, **_route_kwargs: str) -> httpx.Response:
        table = request.url.path.rsplit("/", 1)[-1]
        method = request.method
        if method == "GET":
            return self._get(table, request)
        if method == "POST":
            return self._post(table, request)
        if method == "PATCH":
            return self._patch(table, request)
        if method == "DELETE":
            return self._delete(table, request)
        raise NotImplementedError(f"fake_supabase: unsupported method {method!r}")

    # -- GET --

    def _get(self, table: str, request: httpx.Request) -> httpx.Response:
        rows = self.tables.get(table, [])
        matched = self._filter(rows, request)

        order = request.url.params.get("order")
        if order:
            column, _, direction = order.partition(".")
            matched = sorted(matched, key=lambda r: (r.get(column) is None, r.get(column)), reverse=(direction == "desc"))

        limit = request.url.params.get("limit")
        if limit is not None:
            matched = matched[: int(limit)]

        return httpx.Response(200, json=matched)

    def _filter(self, rows: list[dict], request: httpx.Request) -> list[dict]:
        skip_keys = {"select", "order", "limit"}
        # url.params collapses repeated keys to the last value; multi_items()
        # preserves every occurrence (needed for scheduled_start=gte.X&scheduled_start=lt.Y).
        filters: list[tuple[str, str]] = [
            (key, value) for key, value in request.url.params.multi_items() if key not in skip_keys
        ]
        result = rows
        for key, raw_value in filters:
            result = [row for row in result if _row_matches_filter(row, key, raw_value)]
        return result

    # -- POST (insert, or upsert when on_conflict is present) --

    def _post(self, table: str, request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        items = body if isinstance(body, list) else [body]
        on_conflict = request.url.params.get("on_conflict")
        rows = self.tables.setdefault(table, [])
        stored: list[dict] = []

        for item in items:
            if on_conflict:
                conflict_columns = on_conflict.split(",")
                existing = next(
                    (r for r in rows if all(r.get(c) == item.get(c) for c in conflict_columns)), None
                )
                if existing is not None:
                    existing.update(item)
                    stored.append(existing)
                    continue

            new_row = {**_TABLE_DEFAULTS.get(table, {}), **item}
            if table in _GENERATED_ID_TABLES and "id" not in new_row:
                new_row["id"] = _new_id()
            for timestamp_column in ("captured_at", "created_at", "observed_at"):
                new_row.setdefault(timestamp_column, _fake_now())
            rows.append(new_row)
            stored.append(new_row)

        return httpx.Response(201, json=stored)

    # -- PATCH --

    def _patch(self, table: str, request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        rows = self.tables.get(table, [])
        matched = self._filter(rows, request)
        for row in matched:
            row.update(body)
        return httpx.Response(200, json=matched)

    # -- DELETE (app.demo.reset's own boundary) --

    def _delete(self, table: str, request: httpx.Request) -> httpx.Response:
        rows = self.tables.get(table, [])
        matched = self._filter(rows, request)
        remaining = [r for r in rows if r not in matched]
        self.tables[table] = remaining
        return httpx.Response(200, json=matched)
