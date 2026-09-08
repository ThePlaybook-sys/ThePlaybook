"""MANSA Phase 8.2 -- Controlled DEV Roster/Identity Activation
(2026-09-08).

TEMPORARY module, same "temporary hook, then revert -- but the DATA
stays" discipline as every prior real activation in this project
(Phase 8.0.5 Data Activation Pass 1's BALLDONTLIE injuries, Weather
Activation) -- unlike the two read-only Phase 8.2 diagnostics that
preceded this (both fully reverted, including their captured rows,
since they wrote nothing), this module performs a REAL, durable write
via the REAL, now-provider-neutral `persist_roster()` path. Only the
temporary wiring (this file, its startup hook, its `__init__.py`) is
reverted after -- the resulting `players`/`player_provider_ids`/
`roster_memberships` rows are real, durable, and untouched by the
revert.

**No new live MySportsFeeds call is made here.** Per HQ's own "no
additional provider diagnostic is needed" instruction, this module
constructs the exact real `RosterEntry` data already captured live by
Phase 8.2 Diagnostic #2 (`docs/ops/phase-8.2-mysportsfeeds-players-
diagnostic-2-2026-09-08.md`) -- the 34 real players (17 NE + 17 SEA)
whose full field data that diagnostic's own `id_cross_check` output
already captured verbatim, matched against the 2026-09-03 gap test's
real `lineup.json` capture. This is real provider data already
obtained under this session's own authorized calls, not fabricated,
not re-fetched.

**Scope, disclosed plainly:** these 34 players are the real "expected
lineup" players MySportsFeeds' `lineup.json` reported for game 163541
(NE @ SEA, 2026-09-10), not each team's complete ~53-man active roster
-- `players.json`'s full ~2,322-player payload was never persisted
verbatim, only the subset this project already has complete real field
data for. A future pass wanting full-roster coverage would need either
a fresh `players.json` call filtered/scanned for every NE/SEA row (not
just the 34 already-known ones) or accepting this same subset scope
permanently -- a real product decision, not resolved here.

Calls the now-generalized `persist_roster(response, provider_name=
"mysportsfeeds", write_depth_chart_snapshot=False)` once per team --
`write_depth_chart_snapshot=False` because this data source carries no
real depth/lineup information (Phase 8.2's own "keep concepts separate"
rule); depth/lineup activation is explicitly deferred to a future pass
per HQ's own item 3 framing this pass.
"""
from __future__ import annotations

from app.adapters.models import AdapterResponse, RosterEntry
from app.persistence.roster_ingestion import RosterIngestionResult, persist_roster

#: Real players captured live by Phase 8.2 Diagnostic #2's
#: `id_cross_check` output (2026-09-08, HTTP 200, `/nfl/players.json`) --
#: each a verbatim field match against the 2026-09-03 gap test's real
#: `lineup.json` capture (game 163541, NE @ SEA). Not re-derived, not
#: invented. Each entry: (msf_player_id, first_name, last_name,
#: primary_position, team_abbreviation).
_REAL_ACTIVATED_PLAYERS: tuple[tuple[int, str, str, str, str], ...] = (
    (8771, "Morgan", "Moses", "OT", "NE"),
    (9999, "Hunter", "Henry", "TE", "NE"),
    (14990, "Carlton", "Davis", "CB", "NE"),
    (15069, "Harold", "Landry III", "OLB", "NE"),
    (16786, "A.J.", "Brown", "WR", "NE"),
    (18759, "Kindle", "Vildor", "CB", "NE"),
    (18943, "Mike", "Onwenu", "G", "NE"),
    (30398, "Christian", "Elliss", "ILB", "NE"),
    (30602, "Milton", "Williams", "DE", "NE"),
    (31103, "Rhamondre", "Stevenson", "RB", "NE"),
    (39293, "Romeo", "Doubs", "WR", "NE"),
    (108896, "Demario", "Douglas", "WR", "NE"),
    (112190, "Cory", "Durden", "DT", "NE"),
    (133837, "Drake", "Maye", "QB", "NE"),
    (166763, "Jared", "Wilson", "C", "NE"),
    (166894, "Andres", "Borregales", "K", "NE"),
    (166899, "Jaylen", "Reed", "FS", "NE"),
    (7266, "Jason", "Myers", "K", "SEA"),
    (10027, "Jarran", "Reed", "DT", "SEA"),
    (13412, "Cooper", "Kupp", "WR", "SEA"),
    (14494, "Sam", "Darnold", "QB", "SEA"),
    (39182, "Chris", "Paul Jr.", "ILB", "SEA"),
    (55455, "Rashid", "Shaheed", "WR", "SEA"),
    (79758, "Jaxon", "Smith-Njigba", "WR", "SEA"),
    (79775, "Derick", "Hall", "OLB", "SEA"),
    (108837, "Mike", "Morris", "DE", "SEA"),
    (112361, "Ty", "Okada", "FS", "SEA"),
    (133956, "AJ", "Barner", "TE", "SEA"),
    (134585, "Jalen", "Sundell", "C", "SEA"),
    (166842, "Amari", "Kight", "OT", "SEA"),
    (168249, "Brock", "Lampe", "FB", "SEA"),
    (207936, "Jadarian", "Price", "RB", "SEA"),
    (208053, "Beau", "Stephens", "G", "SEA"),
    (208569, "Avery", "Smith", "CB", "SEA"),
)


def _roster_entries_for_team(team: str) -> list[RosterEntry]:
    return [
        RosterEntry(
            team=team,
            player_external_id=str(msf_id),
            player_name=f"{first} {last}",
            position=position,
            depth_chart_rank=None,
        )
        for msf_id, first, last, position, team_abbrev in _REAL_ACTIVATED_PLAYERS
        if team_abbrev == team
    ]


async def run_msf_roster_activation() -> dict[str, RosterIngestionResult]:
    """Runs `persist_roster` once per real tracked team (NE, SEA), each
    against the real, already-captured `RosterEntry` subset above.
    Returns `{team_abbreviation: RosterIngestionResult}`. Idempotent by
    construction (same guarantee `persist_roster`/`ensure_player`
    already provide) -- a second real invocation would report
    `players_confirmed`/`memberships_unchanged` rather than duplicating
    any row, so an accidental double-fire (the same overlapping-Railway-
    deployment risk both prior Phase 8.2 diagnostics disclosed) cannot
    corrupt state, only redundantly confirm it."""
    results: dict[str, RosterIngestionResult] = {}
    for team in ("NE", "SEA"):
        entries = _roster_entries_for_team(team)
        response = AdapterResponse(value=entries, source="mysportsfeeds")
        results[team] = await persist_roster(
            response, provider_name="mysportsfeeds", write_depth_chart_snapshot=False
        )
    return results
