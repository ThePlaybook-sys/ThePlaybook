-- Centralized Product Entitlement Foundation (2026-09-09) required test
-- evidence, all 8 items from the HQ directive:
--   1. current free/pro/elite/syndicate behavior is unchanged
--   2. product:* grants all product capabilities
--   3. product:* does NOT grant an admin/non-product capability
--   4. expired grants do not work
--   5. revoked grants do not work
--   6. another user cannot use the owner's grant
--   7. users cannot self-create grants
--   8. subscription access still works without any entitlement_grants row
-- Run via `supabase test db`, or manually inside a transaction that's
-- rolled back -- same convention as game_provider_ids_constraints_test.sql,
-- rls_policies_test.sql, and migration_reversibility_check.sql.

begin;
create extension if not exists pgtap with schema extensions;
select plan(13);

insert into auth.users (id) values
  ('e2000000-0000-0000-0000-000000000001'), -- free_user: no subscription, no grant
  ('e2000000-0000-0000-0000-000000000002'), -- pro_user: real active subscription
  ('e2000000-0000-0000-0000-000000000003'), -- syndicate_user: real active subscription
  ('e2000000-0000-0000-0000-000000000004'), -- wildcard_grant_user: product:*, no subscription
  ('e2000000-0000-0000-0000-000000000005'), -- expired_grant_user: product:*, expired
  ('e2000000-0000-0000-0000-000000000006'), -- revoked_grant_user: product:*, revoked
  ('e2000000-0000-0000-0000-000000000007'), -- admin_grant_user: admin:dashboard (wrong namespace)
  ('e2000000-0000-0000-0000-000000000008'), -- exact_key_grant_user: product:recommendations
  ('e2000000-0000-0000-0000-000000000009'); -- other_user: no grant of their own

insert into subscriptions (user_id, tier, status) values
  ('e2000000-0000-0000-0000-000000000002', 'pro', 'active'),
  ('e2000000-0000-0000-0000-000000000003', 'syndicate', 'active');

insert into entitlement_grants (user_id, capability_key, source, expires_at, revoked_at) values
  ('e2000000-0000-0000-0000-000000000004', 'product:*', 'owner', null, null),
  ('e2000000-0000-0000-0000-000000000005', 'product:*', 'owner', now() - interval '1 day', null),
  ('e2000000-0000-0000-0000-000000000006', 'product:*', 'owner', null, now() - interval '1 hour'),
  ('e2000000-0000-0000-0000-000000000007', 'admin:dashboard', 'owner', null, null),
  ('e2000000-0000-0000-0000-000000000008', 'product:recommendations', 'complimentary', null, null);

-- Proof 1: current free/pro/elite/syndicate behavior is unchanged.
select is(
  resolve_permitted_tiers('e2000000-0000-0000-0000-000000000001'), array['free'],
  'free user (no subscription, no grant) resolves to exactly [free]'
);
select is(
  resolve_permitted_tiers('e2000000-0000-0000-0000-000000000002'), array['free', 'pro'],
  'pro subscriber resolves to exactly [free, pro]'
);
select is(
  resolve_permitted_tiers('e2000000-0000-0000-0000-000000000003'), array['free', 'pro', 'elite', 'syndicate'],
  'syndicate subscriber resolves to exactly [free, pro, elite, syndicate]'
);

-- Proof 2: product:* grants all product capabilities (equivalent to the
-- full syndicate ladder for the one real product gate that exists today).
select is(
  resolve_permitted_tiers('e2000000-0000-0000-0000-000000000004'), array['free', 'pro', 'elite', 'syndicate'],
  'a product:* grant resolves to the full tier ladder with zero subscription'
);
select ok(
  has_entitlement('e2000000-0000-0000-0000-000000000004', 'syndicate'),
  'has_entitlement() confirms the product:* grant satisfies the syndicate gate'
);
select ok(
  entitlement_capability_matches('product:*', 'product:sharing'),
  'product:* matches a hypothetical future product:sharing capability -- generic, not hardcoded to recommendations'
);

-- Proof 3: product:* does NOT grant an admin/non-product capability.
select ok(
  not entitlement_capability_matches('product:*', 'admin:dashboard'),
  'product:* never matches a different namespace (admin:dashboard)'
);
select is(
  resolve_permitted_tiers('e2000000-0000-0000-0000-000000000007'), array['free'],
  'a grant in the admin: namespace does not elevate product/tier access at all'
);

-- Proof 4: expired grants do not work.
select is(
  resolve_permitted_tiers('e2000000-0000-0000-0000-000000000005'), array['free'],
  'an expired product:* grant does not elevate access'
);

-- Proof 5: revoked grants do not work.
select is(
  resolve_permitted_tiers('e2000000-0000-0000-0000-000000000006'), array['free'],
  'a revoked product:* grant does not elevate access'
);

-- Proof 6: another user cannot use the owner's grant -- simulate
-- other_user's own authenticated PostgREST session asking about
-- wildcard_grant_user's uuid directly.
select set_config('request.jwt.claims', '{"role":"authenticated","sub":"e2000000-0000-0000-0000-000000000009"}', true);
select set_config('role', 'authenticated', true);
select is(
  resolve_permitted_tiers('e2000000-0000-0000-0000-000000000004'), array['free'],
  'a different authenticated user probing the grant holder''s uuid gets only [free], never the real grant'
);

-- Proof 7: users cannot self-create grants (still running as
-- 'authenticated', from Proof 6's simulated session).
select throws_ok(
  $$ insert into entitlement_grants (user_id, capability_key, source)
     values ('e2000000-0000-0000-0000-000000000009', 'product:*', 'owner') $$,
  '42501',
  null,
  'an authenticated user cannot insert their own entitlement_grants row (RLS has no insert policy at all)'
);

-- Proof 8: subscription access still works without any entitlement_grants
-- row (reset to a service-role context for this check -- pro_user has
-- zero grants rows, proven again explicitly here as its own numbered
-- proof). `reset role` alone is not enough: `request.jwt.claims` is a
-- separate GUC that Proof 6/7's simulated session also set and which
-- `auth.role()`/`auth.uid()` actually read -- it must be reset too, or
-- this check would inherit Proof 6/7's simulated identity, exactly the
-- kind of stale-context artifact that can only happen inside one
-- rolled-back test transaction (a real PostgREST request always gets a
-- fresh claims GUC per request, never carried over from a prior one).
reset role;
select set_config('request.jwt.claims', '{"role":"service_role"}', true);
select ok(
  has_entitlement('e2000000-0000-0000-0000-000000000002', 'pro'),
  'a real pro subscriber with zero entitlement_grants rows still passes the pro gate'
);

select * from finish();
rollback;
