-- Post-Phase-1 defect fix, caught by Supabase's own security advisor while starting
-- Phase 2: four Phase 1 functions had no explicit search_path set, a search_path
-- hijacking risk (a malicious role could shadow expected schema objects earlier in
-- an unset search_path). Fixed per Mac's explicit "correct proven defects" carve-out
-- in the Phase 1 close-out instructions — mechanical, no design decision involved.
-- set_updated_at() was not flagged by the advisor and is left untouched.

alter function public.block_snapshot_updates() set search_path = public;
alter function public.uuid_generate_v7() set search_path = public;
alter function public.block_agent_output_updates() set search_path = public;
alter function public.log_config_change() set search_path = public;
