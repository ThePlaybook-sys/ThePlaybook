"""MANSA Phase 8.2 -- MySportsFeeds Players Identity Diagnostic (2026-09-08).

TEMPORARY, DIAGNOSTIC-ONLY module, same shape and same "temporary probe,
then revert" discipline as `app.diagnostics.msf_bakeoff` (2026-09-03,
already reverted -- see `docs/ops/nfl-provider-gap-test-mysportsfeeds-
2026-09-03.md`). Not a `ProviderAdapter`, never wired into any permanent
route. Invoked once, at process startup, from a dev-only, flag-gated
hook (see `app.main`), for the exact same reason as every prior probe in
this project: this workspace's own egress policy blocks direct HTTPS to
`mysportsfeeds.com`/`api.mysportsfeeds.com` and to this service's own
public Railway domain, so results are retrieved via `logger.warning`
lines in Railway's deploy logs, never an HTTP response.

**Exactly ONE live HTTP call is made** (`GET /nfl/players.json`), per
HQ's explicit "ONE controlled MySportsFeeds players-feed diagnostic. No
repeated probing." instruction. No retries, no pagination follow-up
call, no second feed.

Endpoint path CONFIRMED from the official `mysportsfeeds-node` npm
package source (`lib/API_v2_0.js`'s `feeds.players = {season: false,
endpoint: 'players'}`, combined with `API_v2_0.prototype.__determineUrl`
-- a `season: false` feed with no `path` array resolves to
`{baseUrl}/{league}/{endpoint}.{format}`, i.e. no season segment, no
game/team path segment). Base URL and Basic-auth scheme
(`username=api_key`, `password="MYSPORTSFEEDS"` literal) reused verbatim
from the 2026-09-03 probe, itself confirmed from the same SDK source.

Cross-feed identity check: this module also compares the real response
against a small, already-real reference set of player IDs -- not
invented here, but the actual `teamLineups[].expected.lineupPositions[]`
player IDs captured live by the 2026-09-03 gap test's own `lineup`
call (`http_status=200`, game NE @ SEA, `docs/ops/nfl-provider-gap-test-
mysportsfeeds-2026-09-03.md`'s own underlying raw capture). This answers
HQ's item 3 ("do player IDs from the players feed align with the already
validated lineup.json player IDs") using data this project already has,
without a second live call.
"""
from __future__ import annotations

import base64
import time
from typing import Any

import httpx

_MSF_PASSWORD = "MYSPORTSFEEDS"  # CONFIRMED literal, not a real password -- SDK's own authenticate() example
_PLAYERS_PATH = "/nfl/players.json"

#: Real player IDs captured live by the 2026-09-03 MySportsFeeds gap test's
#: `lineup` call (run 2, http_status=200, game id 163541, NE @ SEA,
#: kickoff 2026-09-10T00:20:00Z) -- reused here verbatim, not re-derived
#: or invented this pass. Each entry: (player_id, first_name, last_name,
#: position, team_abbreviation).
KNOWN_LINEUP_PLAYER_IDS: tuple[tuple[int, str, str, str, str], ...] = (
    (31103, "Rhamondre", "Stevenson", "RB", "NE"),
    (166763, "Jared", "Wilson", "C", "NE"),
    (9999, "Hunter", "Henry", "TE", "NE"),
    (30602, "Milton", "Williams", "DE", "NE"),
    (8771, "Morgan", "Moses", "OT", "NE"),
    (112190, "Cory", "Durden", "DT", "NE"),
    (133837, "Drake", "Maye", "QB", "NE"),
    (15069, "Harold", "Landry III", "OLB", "NE"),
    (166894, "Andres", "Borregales", "K", "NE"),
    (108896, "Demario", "Douglas", "WR", "NE"),
    (30398, "Christian", "Elliss", "ILB", "NE"),
    (39293, "Romeo", "Doubs", "WR", "NE"),
    (16786, "A.J.", "Brown", "WR", "NE"),
    (14990, "Carlton", "Davis", "CB", "NE"),
    (18759, "Kindle", "Vildor", "CB", "NE"),
    (18943, "Mike", "Onwenu", "G", "NE"),
    (166899, "Jaylen", "Reed", "FS", "NE"),
    (207936, "Jadarian", "Price", "RB", "SEA"),
    (134585, "Jalen", "Sundell", "C", "SEA"),
    (133956, "AJ", "Barner", "TE", "SEA"),
    (108837, "Mike", "Morris", "DE", "SEA"),
    (166842, "Amari", "Kight", "OT", "SEA"),
    (10027, "Jarran", "Reed", "DT", "SEA"),
    (14494, "Sam", "Darnold", "QB", "SEA"),
    (79775, "Derick", "Hall", "OLB", "SEA"),
    (7266, "Jason", "Myers", "K", "SEA"),
    (13412, "Cooper", "Kupp", "WR", "SEA"),
    (39182, "Chris", "Paul", "Jr.", "SEA"),  # deliberately kept as-captured; see report data-quality note
    (55455, "Rashid", "Shaheed", "WR", "SEA"),
    (79758, "Jaxon", "Smith-Njigba", "WR", "SEA"),
    (168249, "Brock", "Lampe", "FB", "SEA"),
    (208569, "Avery", "Smith", "CB", "SEA"),
    (208053, "Beau", "Stephens", "G", "SEA"),
    (112361, "Ty", "Okada", "FS", "SEA"),
)


def _auth_header(api_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{api_key}:{_MSF_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def _find_player_lists(body: Any) -> list[tuple[str, list]]:
    """Defensive shape discovery -- the real top-level key holding the
    player array isn't known ahead of this call, so this looks for every
    list-of-dicts anywhere at the top level rather than assuming a key
    name (`players`, `playerList`, etc.)."""
    found: list[tuple[str, list]] = []
    if isinstance(body, list):
        found.append(("<root>", body))
    elif isinstance(body, dict):
        for key, value in body.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                found.append((key, value))
    return found


def _extract_player_id(entry: dict) -> int | None:
    """Defensive ID extraction -- real entries may be flat
    (`{"id": ..., "firstName": ...}`) or nested (`{"player": {"id": ...},
    "teamAsOfDate": {...}}`), matching the two shapes this project's own
    prior captures have both seen across different MSF feeds."""
    if "id" in entry and isinstance(entry.get("id"), int):
        return entry["id"]
    nested = entry.get("player")
    if isinstance(nested, dict) and isinstance(nested.get("id"), int):
        return nested["id"]
    return None


def _cap_sample(items: list, *, max_items: int = 5) -> dict:
    return {
        "_sample": items[:max_items],
        "_total_count": len(items),
        "_truncated_for_log": len(items) > max_items,
    }


async def run_msf_players_diagnostic(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    """Makes exactly ONE real GET to `/nfl/players.json`. Returns a
    structured result for the caller to log -- never persists anything,
    never makes a second call."""
    headers = _auth_header(api_key)
    started = time.monotonic()
    try:
        response = await client.get(_PLAYERS_PATH, headers=headers, params={"force": "false"})
    except httpx.HTTPError as exc:
        return {
            "path": _PLAYERS_PATH,
            "http_status": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}",
            "response_headers": {},
            "player_lists_found": [],
            "id_cross_check": {},
        }
    latency_ms = round((time.monotonic() - started) * 1000, 1)
    interesting_headers = {
        k: v
        for k, v in response.headers.items()
        if any(term in k.lower() for term in ("ratelimit", "retry-after", "last-modified", "etag", "cache"))
    }
    try:
        body = response.json() if response.content else None
    except ValueError:
        body = {"_non_json_body_preview": response.text[:500]}

    player_lists = _find_player_lists(body) if body is not None else []
    top_level_keys = list(body.keys()) if isinstance(body, dict) else None

    # Build a per-list capped sample for logging (real shape, bounded size).
    capped_lists = {key: _cap_sample(items) for key, items in player_lists}

    # Cross-feed identity check: does this response contain the real
    # lineup-confirmed player IDs above? Computed once, from this same
    # single response, against every list found (no assumption about
    # which key holds the real player array).
    all_ids_in_response: dict[int, dict] = {}
    for _key, items in player_lists:
        for entry in items:
            if not isinstance(entry, dict):
                continue
            pid = _extract_player_id(entry)
            if pid is not None:
                all_ids_in_response[pid] = entry

    id_cross_check = {}
    for pid, first, last, position, team in KNOWN_LINEUP_PLAYER_IDS:
        match = all_ids_in_response.get(pid)
        id_cross_check[pid] = {
            "expected_name": f"{first} {last}",
            "expected_position": position,
            "expected_team": team,
            "found_in_players_feed": match is not None,
            "matched_entry": match if match is not None else None,
        }

    return {
        "path": _PLAYERS_PATH,
        "http_status": response.status_code,
        "latency_ms": latency_ms,
        "error": None,
        "response_headers": interesting_headers,
        "top_level_keys": top_level_keys,
        "player_lists_found": [
            {"key": key, "count": len(items)} for key, items in player_lists
        ],
        "player_lists_sample": capped_lists,
        "id_cross_check": id_cross_check,
        "id_cross_check_summary": {
            "known_ids_checked": len(KNOWN_LINEUP_PLAYER_IDS),
            "known_ids_found": sum(1 for v in id_cross_check.values() if v["found_in_players_feed"]),
        },
    }
