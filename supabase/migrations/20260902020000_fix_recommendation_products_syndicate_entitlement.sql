-- Hotfix (HQ-authorized, 2026-09-02, DEV only): recommendation_products_tier_gated_select
-- never granted access to syndicate-tier subscribers for a syndicate-gated product
-- (min_required_tier = 'syndicate'), even though 'syndicate' is a schema-permitted
-- subscriptions.tier value (CHECK constraint,
-- supabase/migrations/20260807205946_core_user_account_tables.sql:30) and MANSA's
-- own top paid tier. recommendation_products.min_required_tier has no CHECK
-- constraint (supabase/migrations/20260825120000_recommendation_products_schema.sql:57),
-- so this is a real gap, not a theoretical one -- the policy's USING clause only
-- special-cased min_required_tier in ('free','pro','elite'); a syndicate-gated row
-- fell through to deny for every caller, syndicate subscribers included. Disclosed
-- but deliberately not "fixed" at Milestone 2 (mirrored, not fixed, in
-- apps/api-gateway/app/entitlement.py -- see that file's own docstring/history).
--
-- Minimum correction: extends the exact nested-membership pattern the policy
-- already uses for 'pro' ({'pro','elite','syndicate'}) and 'elite'
-- ({'elite','syndicate'}) one rung further for 'syndicate' ({'syndicate'}) --
-- same ordering semantics (free < pro < elite < syndicate), no new architecture,
-- no change to any other tier's access.

drop policy "recommendation_products_tier_gated_select" on recommendation_products;

create policy "recommendation_products_tier_gated_select" on recommendation_products
  for select using (
    deleted_at is null
    and (
      min_required_tier = 'free'
      or exists (
        select 1 from subscriptions s
        where s.user_id = auth.uid() and s.status = 'active'
          and ((min_required_tier = 'pro' and s.tier in ('pro','elite','syndicate'))
            or (min_required_tier = 'elite' and s.tier in ('elite','syndicate'))
            or (min_required_tier = 'syndicate' and s.tier in ('syndicate')))
      )
    )
  );
