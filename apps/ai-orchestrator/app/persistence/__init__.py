"""Read-only Phase 3 -> Phase 4 data-access layer (Milestone 4.1).

Everything in this package reads already-persisted Supabase state; nothing
here writes. Duplicated from, rather than imported from,
`apps/sports-intel-layer/app/persistence/*` where the same table is read
by both services -- `ai-orchestrator` and `sports-intel-layer` are
separate deployable services with no shared package (Volume 2 Section 3's
service boundary), so the read *contract* is kept identical by convention,
not by a shared import.
"""
