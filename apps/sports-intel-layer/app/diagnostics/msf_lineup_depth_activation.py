"""MANSA Phase 8.2 -- Controlled DEV Lineup/Depth Activation
(2026-09-08).

TEMPORARY module, same "temporary hook, but real data persists"
discipline as the prior Phase 8.2 player/roster activation pass
(`app.diagnostics.msf_roster_activation`, since reverted -- see
`docs/ops/phase-8.2-player-roster-depth-activation-2026-09-08.md`).
Only the wiring here is temporary; the resulting `depth_chart_snapshots`
rows are real, durable DEV data.

**Zero new live MySportsFeeds calls, per HQ's explicit preference.**
`_REAL_LINEUP_BODY` below is the exact real `lineup.json` response body
captured live by the 2026-09-03 gap test (game 163541, NE @ SEA,
`http_status=200`) -- the same source both prior Phase 8.2 diagnostics
already drew their 34-player reference set from, reproduced here
verbatim (slimmed to only the fields `app.persistence.
lineup_depth_ingestion` actually reads: `lastUpdatedOn`, `game.id`,
`teamLineups[].team`, `teamLineups[].expected.lineupPositions[].
position`/`.player`), not re-derived or invented. 80 total lineup
slots across both teams, 34 named (non-null) -- the same 34 players
the prior pass already activated into canonical identity/roster
membership, so every one is expected to resolve.
"""
from __future__ import annotations

import json

from app.persistence.lineup_depth_ingestion import LineupDepthIngestionResult, persist_lineup_depth_chart

_REAL_LINEUP_BODY_JSON = r"""
{"lastUpdatedOn": "2026-09-03T19:24:29.492Z", "game": {"id": 163541}, "teamLineups": [{"team": {"id": 50, "abbreviation": "NE"}, "expected": {"lineupPositions": [{"position": "Offense-RB-1", "player": {"id": 31103, "firstName": "Rhamondre", "lastName": "Stevenson", "position": "RB", "jerseyNumber": 38}}, {"position": "Offense-C", "player": {"id": 166763, "firstName": "Jared", "lastName": "Wilson", "position": "C", "jerseyNumber": 58}}, {"position": "Offense-RB-3", "player": null}, {"position": "Offense-RB-2", "player": null}, {"position": "Offense-TE-2", "player": null}, {"position": "Offense-TE-1", "player": {"id": 9999, "firstName": "Hunter", "lastName": "Henry", "position": "TE", "jerseyNumber": 85}}, {"position": "Defense-DE-3", "player": null}, {"position": "Defense-DE-1", "player": {"id": 30602, "firstName": "Milton", "lastName": "Williams", "position": "DE", "jerseyNumber": 97}}, {"position": "Defense-DE-2", "player": null}, {"position": "Offense-T-3", "player": null}, {"position": "Offense-T-2", "player": null}, {"position": "Offense-T-1", "player": {"id": 8771, "firstName": "Morgan", "lastName": "Moses", "position": "OT", "jerseyNumber": 76}}, {"position": "Defense-DT-3", "player": null}, {"position": "Defense-DT-2", "player": null}, {"position": "Defense-DT-1", "player": {"id": 112190, "firstName": "Cory", "lastName": "Durden", "position": "DT", "jerseyNumber": 94}}, {"position": "Offense-QB-1", "player": {"id": 133837, "firstName": "Drake", "lastName": "Maye", "position": "QB", "jerseyNumber": 10}}, {"position": "Offense-QB-2", "player": null}, {"position": "SpecialTeams-K-2", "player": null}, {"position": "Defense-LB-1", "player": {"id": 15069, "firstName": "Harold", "lastName": "Landry III", "position": "OLB", "jerseyNumber": 2}}, {"position": "SpecialTeams-K-1", "player": {"id": 166894, "firstName": "Andres", "lastName": "Borregales", "position": "K", "jerseyNumber": 36}}, {"position": "Offense-WR-4", "player": null}, {"position": "Offense-WR-3", "player": {"id": 108896, "firstName": "Demario", "lastName": "Douglas", "position": "WR", "jerseyNumber": 3}}, {"position": "Offense-WR-5", "player": null}, {"position": "Defense-LB-2", "player": {"id": 30398, "firstName": "Christian", "lastName": "Elliss", "position": "ILB", "jerseyNumber": 53}}, {"position": "Defense-LB-3", "player": null}, {"position": "Defense-NT", "player": null}, {"position": "Defense-LB-4", "player": null}, {"position": "Offense-WR-2", "player": {"id": 39293, "firstName": "Romeo", "lastName": "Doubs", "position": "WR", "jerseyNumber": 87}}, {"position": "Defense-LB-5", "player": null}, {"position": "Offense-WR-1", "player": {"id": 16786, "firstName": "A.J.", "lastName": "Brown", "position": "WR", "jerseyNumber": 1}}, {"position": "Defense-CB-5", "player": null}, {"position": "Defense-CB-2", "player": {"id": 14990, "firstName": "Carlton", "lastName": "Davis", "position": "CB", "jerseyNumber": 7}}, {"position": "Offense-G-2", "player": null}, {"position": "Defense-CB-1", "player": {"id": 18759, "firstName": "Kindle", "lastName": "Vildor", "position": "CB", "jerseyNumber": 28}}, {"position": "Offense-G-1", "player": {"id": 18943, "firstName": "Mike", "lastName": "Onwenu", "position": "G", "jerseyNumber": 71}}, {"position": "Defense-CB-4", "player": null}, {"position": "Defense-CB-3", "player": null}, {"position": "Offense-G-3", "player": null}, {"position": "Defense-S-1", "player": {"id": 166899, "firstName": "Jaylen", "lastName": "Reed", "position": "FS", "jerseyNumber": 23}}, {"position": "Defense-S-2", "player": null}]}}, {"team": {"id": 79, "abbreviation": "SEA"}, "expected": {"lineupPositions": [{"position": "Offense-RB-1", "player": {"id": 207936, "firstName": "Jadarian", "lastName": "Price", "position": "RB", "jerseyNumber": 8}}, {"position": "Offense-C", "player": {"id": 134585, "firstName": "Jalen", "lastName": "Sundell", "position": "C", "jerseyNumber": 61}}, {"position": "Offense-RB-3", "player": null}, {"position": "Offense-RB-2", "player": null}, {"position": "Offense-TE-2", "player": null}, {"position": "Offense-TE-1", "player": {"id": 133956, "firstName": "AJ", "lastName": "Barner", "position": "TE", "jerseyNumber": 88}}, {"position": "Defense-DE-3", "player": null}, {"position": "Defense-DE-1", "player": {"id": 108837, "firstName": "Mike", "lastName": "Morris", "position": "DE", "jerseyNumber": 94}}, {"position": "Defense-DE-2", "player": null}, {"position": "Offense-T-3", "player": null}, {"position": "Offense-T-2", "player": null}, {"position": "Offense-T-1", "player": {"id": 166842, "firstName": "Amari", "lastName": "Kight", "position": "OT", "jerseyNumber": 79}}, {"position": "Defense-DT-3", "player": null}, {"position": "Defense-DT-2", "player": null}, {"position": "Defense-DT-1", "player": {"id": 10027, "firstName": "Jarran", "lastName": "Reed", "position": "DT", "jerseyNumber": 90}}, {"position": "Offense-QB-1", "player": {"id": 14494, "firstName": "Sam", "lastName": "Darnold", "position": "QB", "jerseyNumber": 14}}, {"position": "Offense-QB-2", "player": null}, {"position": "SpecialTeams-K-2", "player": null}, {"position": "Defense-LB-1", "player": {"id": 79775, "firstName": "Derick", "lastName": "Hall", "position": "OLB", "jerseyNumber": 58}}, {"position": "SpecialTeams-K-1", "player": {"id": 7266, "firstName": "Jason", "lastName": "Myers", "position": "K", "jerseyNumber": 5}}, {"position": "Offense-WR-4", "player": null}, {"position": "Offense-WR-3", "player": {"id": 13412, "firstName": "Cooper", "lastName": "Kupp", "position": "WR", "jerseyNumber": 10}}, {"position": "Offense-WR-5", "player": null}, {"position": "Defense-LB-2", "player": {"id": 39182, "firstName": "Chris", "lastName": "Paul Jr.", "position": "ILB", "jerseyNumber": 49}}, {"position": "Defense-LB-3", "player": null}, {"position": "Defense-NT", "player": null}, {"position": "Defense-LB-4", "player": null}, {"position": "Offense-WR-2", "player": {"id": 55455, "firstName": "Rashid", "lastName": "Shaheed", "position": "WR", "jerseyNumber": 22}}, {"position": "Defense-LB-5", "player": null}, {"position": "Offense-WR-1", "player": {"id": 79758, "firstName": "Jaxon", "lastName": "Smith-Njigba", "position": "WR", "jerseyNumber": 11}}, {"position": "Defense-CB-5", "player": null}, {"position": "Defense-CB-2", "player": {"id": 168249, "firstName": "Brock", "lastName": "Lampe", "position": "FB", "jerseyNumber": 46}}, {"position": "Offense-G-2", "player": null}, {"position": "Defense-CB-1", "player": {"id": 208569, "firstName": "Avery", "lastName": "Smith", "position": "CB", "jerseyNumber": 36}}, {"position": "Offense-G-1", "player": {"id": 208053, "firstName": "Beau", "lastName": "Stephens", "position": "G", "jerseyNumber": 60}}, {"position": "Defense-CB-4", "player": null}, {"position": "Defense-CB-3", "player": null}, {"position": "Offense-G-3", "player": null}, {"position": "Defense-S-1", "player": {"id": 112361, "firstName": "Ty", "lastName": "Okada", "position": "FS", "jerseyNumber": 39}}, {"position": "Defense-S-2", "player": null}]}}]}
"""

_REAL_LINEUP_BODY = json.loads(_REAL_LINEUP_BODY_JSON)


async def run_msf_lineup_depth_activation() -> dict[str, LineupDepthIngestionResult]:
    """Runs `persist_lineup_depth_chart` once per real tracked team (NE,
    SEA) against the real, already-captured lineup body above. Returns
    `{team_abbreviation: LineupDepthIngestionResult}`. Zero live
    MySportsFeeds calls -- only real Supabase reads/writes."""
    results: dict[str, LineupDepthIngestionResult] = {}
    for team in ("NE", "SEA"):
        results[team] = await persist_lineup_depth_chart(
            _REAL_LINEUP_BODY, team=team, provider_name="mysportsfeeds"
        )
    return results
