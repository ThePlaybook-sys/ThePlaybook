"""MANSA Phase 8.2 -- MySportsFeeds Players Identity Diagnostic #2
(2026-09-08).

TEMPORARY, DIAGNOSTIC-ONLY module. Identical in every respect to the
first pass's `app.diagnostics.msf_players_diagnostic` (built, run once,
reverted earlier the same day -- see `docs/ops/phase-8.2-mysportsfeeds-
players-diagnostic-2026-09-08.md`), with exactly ONE change: the client
read timeout is raised from 30s to 120s. The first pass's one authorized
call sent a real request and received no HTTP response within 30
seconds (`httpx.ReadTimeout`) -- HQ's own diagnosis is that this is very
likely a whole-league, un-scoped payload needing more time to generate/
transfer than the carried-forward 30s bake-off default, not an access
rejection. This pass tests that theory with exactly one more real call,
per HQ's explicit "no automatic retry... exactly ONE MySportsFeeds
request" instruction.

Same reasons as every prior probe in this project for the startup-hook +
Railway-deploy-log retrieval shape: this workspace's own egress policy
blocks direct HTTPS to `mysportsfeeds.com`/`api.mysportsfeeds.com` and to
this service's own public Railway domain.

Endpoint path/auth CONFIRMED from the official `mysportsfeeds-node` npm
package source, identical to pass #1 -- see that module's own docstring
(since reverted) for the full derivation.

Cross-feed identity check: reuses the exact same 34 real player IDs
captured live by the 2026-09-03 gap test's own `lineup.json` call (NE @
SEA, game 163541), including explicit, itemized investigation of the two
previously-flagged anomalies (`id=9999`, and the entry captured as
"Chris Paul" under NE) -- per HQ's explicit "do not infer identity if
evidence is ambiguous" instruction, this pass reports what the players
feed actually says about those two IDs rather than guessing.
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
#: or invented this pass, identical to pass #1's own reference set. Each
#: entry: (player_id, first_name, last_name, position, team_abbreviation).
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
    (39182, "Chris", "Paul", "Jr.", "SEA"),  # explicitly investigated this pass, see id_cross_check
    (55455, "Rashid", "Shaheed", "WR", "SEA"),
    (79758, "Jaxon", "Smith-Njigba", "WR", "SEA"),
    (168249, "Brock", "Lampe", "FB", "SEA"),
    (208569, "Avery", "Smith", "CB", "SEA"),
    (208053, "Beau", "Stephens", "G", "SEA"),
    (112361, "Ty", "Okada", "FS", "SEA"),
)

#: The two anomalies flagged by pass #1, explicitly investigated this
#: pass per HQ's item 3 -- never inferred, only reported as found.
FLAGGED_ANOMALY_IDS: tuple[int, ...] = (9999, 39182)


def _auth_header(api_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{api_key}:{_MSF_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def _find_player_lists(body: Any) -> list[tuple[str, list]]:
    """Defensive shape discovery -- unchanged from pass #1."""
    found: list[tuple[str, list]] = []
    if isinstance(body, list):
        found.append(("<root>", body))
    elif isinstance(body, dict):
        for key, value in body.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                found.append((key, value))
    return found


def _extract_player_id(entry: dict) -> int | None:
    """Defensive ID extraction -- unchanged from pass #1."""
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
    """Makes exactly ONE real GET to `/nfl/players.json`, with a 120s
    read timeout (raised from pass #1's 30s, per HQ's explicit
    instruction). Returns a structured result for the caller to log --
    never persists anything, never makes a second call."""
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
            "content_length_bytes": None,
            "player_lists_found": [],
            "id_cross_check": {},
            "anomaly_findings": {},
        }
    latency_ms = round((time.monotonic() - started) * 1000, 1)
    interesting_headers = {
        k: v
        for k, v in response.headers.items()
        if any(term in k.lower() for term in ("ratelimit", "retry-after", "last-modified", "etag", "cache", "content-length"))
    }
    content_length_bytes = len(response.content) if response.content else 0
    try:
        body = response.json() if response.content else None
    except ValueError:
        body = {"_non_json_body_preview": response.text[:500]}

    player_lists = _find_player_lists(body) if body is not None else []
    top_level_keys = list(body.keys()) if isinstance(body, dict) else None
    capped_lists = {key: _cap_sample(items) for key, items in player_lists}

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

    # Explicit, itemized anomaly investigation (HQ item 3: ID 9999 and
    # "Chris Paul") -- never inferred, only what the real response says.
    anomaly_findings = {}
    for anomaly_id in FLAGGED_ANOMALY_IDS:
        match = all_ids_in_response.get(anomaly_id)
        anomaly_findings[anomaly_id] = {
            "found_in_players_feed": match is not None,
            "matched_entry": match if match is not None else None,
        }

    return {
        "path": _PLAYERS_PATH,
        "http_status": response.status_code,
        "latency_ms": latency_ms,
        "error": None,
        "response_headers": interesting_headers,
        "content_length_bytes": content_length_bytes,
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
        "anomaly_findings": anomaly_findings,
    }
