-- Phase 2, Milestone 1 + AC #1: auto-create user_profiles on signup via a DB trigger
-- on auth.users INSERT, per Mac's explicit implementation choice (consistent with
-- Phase 1's DB-level-enforcement pattern rather than application code).
--
-- Blueprint-vs-reality conflict found and resolved (documented in CHANGELOG and
-- Volume 3 §3): jurisdiction_state was NOT NULL, but jurisdiction is collected during
-- onboarding (Milestone 4), a separate, later step from signup. A trigger firing at
-- signup has no jurisdiction value yet. Resolved by relaxing jurisdiction_state to
-- nullable and enforcing the constraint's intent at the application layer instead —
-- exactly what Phase 2's own Key Tasks call for.

alter table user_profiles alter column jurisdiction_state drop not null;

-- SECURITY DEFINER is required: user_profiles has RLS enabled with only select/update
-- policies (Phase 1 Milestone 1) and no insert policy, so an insert executed as any
-- non-owning role would be denied. Running as the function owner (the migration role,
-- which owns the table and bypasses RLS) is the standard, well-established pattern for
-- this exact "create profile row on auth signup" trigger.
create or replace function handle_new_user()
returns trigger as $$
begin
  insert into user_profiles (id)
  values (new.id)
  on conflict (id) do nothing;
  return new;
end;
$$ language plpgsql security definer set search_path = public;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();
