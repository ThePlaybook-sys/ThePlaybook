-- Centralized Product Entitlement Foundation (2026-09-09, HQ-authorized).
--
-- Replaces the two independent copies of tier-membership nesting logic
-- that existed before this migration (Python `app.entitlement.
-- tier_permits`, and this exact SQL policy's own inline CASE-shaped
-- EXISTS subquery -- the same duplication the 2026-09-02 syndicate hotfix
-- already proved is easy to let drift) with ONE authoritative resolution
-- path, `resolve_permitted_tiers(uuid)`, that both the RLS policy below
-- and every Python consumer now call instead of re-deriving the ordering
-- themselves.
--
-- Also introduces `entitlement_grants`: exceptional, non-billing product
-- access (owner, complimentary, promo) -- deliberately separate from
-- `subscriptions` (normal paid tier/billing truth, untouched by this
-- migration) and deliberately NOT modeling discount percentages (Friends
-- & Family is future pricing/billing policy, a different concern, not
-- built here). `capability_key` values are namespaced (`product:*`,
-- `product:recommendations`, ...); a `product:*` grant matches ONLY the
-- `product:` namespace (see `entitlement_capability_matches` below) and
-- can never authorize an `admin:`/`internal:`/any-other-namespace
-- capability -- administrative authorization is an explicitly separate,
-- not-yet-built concern.

-- ============================================================================
-- 1. entitlement_grants
-- ============================================================================

create table entitlement_grants (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  -- Namespaced capability string (e.g. 'product:*', 'product:recommendations').
  -- Deliberately no fixed-value CHECK enum -- see module comment above and
  -- HQ's own examples ("product:sharing", "product:analysis", etc.): future
  -- product capabilities must be addable as data, not as a migration each
  -- time. The format guard below only rejects obviously malformed values
  -- (empty segments, no namespace separator) -- it does not enumerate or
  -- limit which namespaces or capability names may exist.
  capability_key text not null check (capability_key ~ '^[a-z_]+:[a-z_*]+$'),
  -- Where this grant came from -- 'owner' (this pass's only real use),
  -- 'complimentary', 'promo'. NOT 'friends_and_family': F&F is pricing
  -- policy (a discount on a normal paid subscription), never modeled as
  -- an entitlement grant, per HQ's explicit correction to the Option C
  -- design this migration implements.
  source text not null check (source in ('owner', 'complimentary', 'promo')),
  granted_at timestamptz not null default now(),
  -- Nullable: a grant seeded by a migration/script has no specific human
  -- granter; a grant created through a future admin action would set this.
  granted_by uuid references auth.users(id),
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_entitlement_grants_user on entitlement_grants(user_id);

-- Soft-revocation via `revoked_at`, exactly the `withdrawn_at`/`deleted_at`
-- pattern already used on `recommendation_products`/`user_profiles` --
-- NOT the strict append-only-with-block-trigger convention used for
-- historical-evidence tables (odds_snapshots, injury_reports, etc.). A
-- grant's revocation is a real, intended state transition on the same
-- row, not a correction requiring a new historical row.
create trigger trg_entitlement_grants_updated
  before update on entitlement_grants
  for each row execute function set_updated_at();

alter table entitlement_grants enable row level security;
-- Deliberately NO select/insert/update/delete policy for anon/authenticated
-- -- service-role only, the exact same "RLS enabled, no policy" convention
-- already applied to every non-user-facing table in this schema
-- (recommendation_legs, consensus_snapshots, recommendation_agent_outputs,
-- etc.). Users cannot see, create, or modify their own grants; only the
-- service role (this project's own backend/admin tooling) ever writes or
-- reads this table directly. This is the literal mechanism behind HQ's
-- "users must not be able to grant themselves access" requirement.

-- ============================================================================
-- 2. entitlement_capability_matches -- the one wildcard-matching rule
-- ============================================================================

-- Generic, namespace-safe matching: a grant's capability_key matches a
-- requested capability_key iff they are exactly equal, OR the grant is a
-- namespace wildcard ('<namespace>:*') and the requested key starts with
-- that exact namespace prefix. A 'product:*' grant matches
-- 'product:recommendations'/'product:sharing'/'product:anything' but can
-- NEVER match 'admin:x' or any other namespace -- there is no cross-
-- namespace fallthrough anywhere in this expression, so this holds for
-- every future namespace, not just 'product', without a special case.
create or replace function entitlement_capability_matches(p_grant_key text, p_requested_key text)
returns boolean
language sql
immutable
set search_path = public
as $$
  select p_grant_key = p_requested_key
      or (p_grant_key like '%:*' and p_requested_key like (left(p_grant_key, length(p_grant_key) - 1) || '%'));
$$;

-- ============================================================================
-- 3. resolve_permitted_tiers -- the ONE authoritative tier-membership
--    resolution path (replaces the nested-membership logic previously
--    duplicated in `app.entitlement.tier_permits` and in this policy's
--    own inline subquery).
-- ============================================================================

-- Returns the exact set of `recommendation_products.min_required_tier`
-- values `p_user_id` may see -- always includes 'free'. A real, active
-- 'syndicate' subscription, OR any entitlement_grants row matching
-- 'product:recommendations' (exactly or via a 'product:*' wildcard,
-- active: not revoked, not expired) both resolve to the full ladder --
-- the "owner automatically gets every present and future PAID-TIER
-- product capability" requirement, implemented as "an active product
-- grant is equivalent to being a top-tier subscriber for gating
-- purposes," never as an unconditional bypass of every check in the
-- system (that would be the 'all' entitlement HQ explicitly rejected).
--
-- `security definer` + the `auth.role()`/`auth.uid()` guard below: this
-- function is called both by RLS policies (as the row's own querying
-- role, typically 'authenticated', asking about `auth.uid()` -- always
-- itself) and by the API Gateway/orchestrator services using the service
-- role key (which may legitimately ask about any user_id, since that key
-- already bypasses RLS on every table directly). A plain authenticated
-- caller asking about a DIFFERENT user_id gets the safe default ('free'
-- only) rather than another user's real entitlement state -- `security
-- definer` is what makes this function able to read `entitlement_grants`
-- at all (that table has no select policy for `authenticated`), so this
-- guard is what keeps that elevated read from becoming an information
-- leak about other users.
create or replace function resolve_permitted_tiers(p_user_id uuid)
returns text[]
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  v_subscription_tier text;
  v_has_product_grant boolean;
begin
  if auth.role() <> 'service_role' and (auth.uid() is null or auth.uid() <> p_user_id) then
    return array['free'];
  end if;

  select s.tier into v_subscription_tier
  from subscriptions s
  where s.user_id = p_user_id and s.status = 'active'
  order by s.created_at desc
  limit 1;

  select exists (
    select 1 from entitlement_grants g
    where g.user_id = p_user_id
      and g.revoked_at is null
      and (g.expires_at is null or g.expires_at > now())
      and entitlement_capability_matches(g.capability_key, 'product:recommendations')
  ) into v_has_product_grant;

  if v_has_product_grant or v_subscription_tier = 'syndicate' then
    return array['free', 'pro', 'elite', 'syndicate'];
  elsif v_subscription_tier = 'elite' then
    return array['free', 'pro', 'elite'];
  elsif v_subscription_tier = 'pro' then
    return array['free', 'pro'];
  else
    return array['free'];
  end if;
end;
$$;

revoke all on function resolve_permitted_tiers(uuid) from public;
grant execute on function resolve_permitted_tiers(uuid) to authenticated, service_role;

-- ============================================================================
-- 4. has_entitlement -- trivial wrapper, the single call every RLS policy
--    uses (Postgres re-evaluates a policy's USING clause per row, exactly
--    the same cost characteristic as the inline subquery it replaces).
-- ============================================================================

create or replace function has_entitlement(p_user_id uuid, p_min_required_tier text)
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select p_min_required_tier = any(resolve_permitted_tiers(p_user_id));
$$;

revoke all on function has_entitlement(uuid, text) from public;
grant execute on function has_entitlement(uuid, text) to authenticated, service_role;

-- ============================================================================
-- 5. Update the existing recommendation_products RLS policy to use the
--    centralized mechanism -- same access outcome, one function call
--    instead of a hand-written subquery.
-- ============================================================================

drop policy "recommendation_products_tier_gated_select" on recommendation_products;

create policy "recommendation_products_tier_gated_select" on recommendation_products
  for select using (
    deleted_at is null
    and has_entitlement(auth.uid(), min_required_tier)
  );
