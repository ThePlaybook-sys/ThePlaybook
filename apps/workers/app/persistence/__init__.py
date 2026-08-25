"""Read-only Supabase data-access layer for the Background Workers
service (Milestone 4.9). The Recommendation Worker reads `master_refresh_
runs`/`games` directly via its own service-role Supabase access (Mac's
approved "durable-state coordination through Supabase" decision) --
never through a new sports-intel-layer HTTP endpoint. Nothing here
writes; every write this milestone needs happens inside `ai-orchestrator`
via the internal endpoint this service calls."""
