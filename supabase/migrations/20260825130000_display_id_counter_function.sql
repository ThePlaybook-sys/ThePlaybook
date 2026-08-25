-- Milestone 5.1: exposes the atomic display_id_counters increment (see
-- 20260825120000_recommendation_products_schema.sql's own comment for the
-- full atomicity proof) as a callable RPC -- ai-orchestrator only talks to
-- Postgres through PostgREST, which has no way to express
-- "INSERT ... ON CONFLICT ... DO UPDATE SET counter = counter + 1
-- RETURNING counter" as a single request against the table endpoint
-- directly (its upsert support only replaces columns with client-supplied
-- values, never a server-side expression referencing the existing row).
-- Wrapping the exact same single atomic statement in a function and
-- calling it via /rest/v1/rpc/next_display_id_counter preserves the
-- single-statement, no-prior-read atomicity property unchanged -- this is
-- a transport wrapper, not a different mechanism.
create or replace function next_display_id_counter(p_bucket_key text)
returns integer
language plpgsql
set search_path = public
as $$
declare
  v_counter integer;
begin
  insert into display_id_counters (bucket_key, counter, updated_at)
  values (p_bucket_key, 1, now())
  on conflict (bucket_key)
  do update set counter = display_id_counters.counter + 1, updated_at = now()
  returning counter into v_counter;
  return v_counter;
end;
$$;
