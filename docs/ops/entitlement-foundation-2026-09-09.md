# Centralized Product Entitlement Foundation (2026-09-09)

**Status: implemented, HQ-authorized.** Implements Option C from the prior
Entitlement Architecture Decision (chat-only, no artifact), corrected twice
by HQ before this pass: no unrestricted `all` entitlement (product-scoped
`product:*` only, never admin/internal), and Friends & Family is future
pricing/billing policy, never modeled as an entitlement grant.

## What was built

1. **`entitlement_grants`** (`supabase/migrations/20260909200400_entitlement_grants_foundation.sql`):
   `user_id`, `capability_key` (namespaced, e.g. `product:*`/`product:recommendations`,
   format-checked but not value-enumerated so future capabilities need no
   migration), `source` (`owner`/`complimentary`/`promo` -- deliberately
   excludes `friends_and_family`), `granted_at`, `granted_by` (nullable),
   `expires_at`, `revoked_at`, `created_at`/`updated_at`. RLS enabled, **no**
   select/insert/update/delete policy for `anon`/`authenticated` -- the exact
   "RLS enabled, no policy = service-role only" convention already used for
   every non-user-facing table in this schema. Soft-revocation via
   `revoked_at` (the `withdrawn_at`/`deleted_at` pattern), not the strict
   append-only-block-trigger convention, since revocation is a real,
   intended state transition on the same row.
2. **`entitlement_capability_matches(grant_key, requested_key)`**: the one
   generic, namespace-safe wildcard rule -- `'product:*'` matches any
   `'product:...'` key, never a different namespace. Live-verified:
   matches `product:sharing` (a capability that doesn't exist yet), never
   matches `admin:dashboard`.
3. **`resolve_permitted_tiers(user_id)`**: the ONE authoritative
   tier-membership resolution path, replacing the two independent copies of
   the nested-membership ordering that existed before (Python
   `tier_permits`'s own elif chain, and the RLS policy's own inline
   subquery) -- the exact duplication the 2026-09-02 syndicate hotfix
   already proved drifts. Returns the full `min_required_tier` ladder a
   user may reach: always includes `'free'`; adds the rest when either a
   real active `subscriptions` row justifies it (unchanged semantics) OR
   an active (`revoked_at is null`, not expired) `entitlement_grants` row
   matches `'product:recommendations'` (exactly or via `'product:*'`).
   `security definer` + an `auth.role()`/`auth.uid()` guard: a
   non-service-role caller asking about a `user_id` that isn't their own
   `auth.uid()` gets the safe default (`['free']`), never another user's
   real entitlement state -- live-verified via a simulated PostgREST
   session (`request.jwt.claims` GUC).
4. **`has_entitlement(user_id, min_required_tier)`**: a one-line SQL wrapper
   (`min_required_tier = any(resolve_permitted_tiers(user_id))`) -- the
   single call every consumer (RLS policy, Python) now makes.
5. **`recommendation_products_tier_gated_select`** rewritten to
   `deleted_at is null and has_entitlement(auth.uid(), min_required_tier)`
   -- same access outcome as before, one function call instead of a
   hand-written subquery.
6. **Python**: `apps/api-gateway/app/entitlement.py`'s `read_active_subscription_tier`
   replaced by `read_permitted_tiers` (calls the `resolve_permitted_tiers`
   RPC once per request, matching the module's existing fetch-once-loop-
   many-products shape -- no RPC-per-product regression); `tier_permits`
   is now a one-line membership test (`min_required_tier in
   permitted_tiers`) with zero ordering logic of its own. Every call site
   in `recommendations.py` (6) and `track_record.py` (2) updated to the
   new shape. `apps/ai-orchestrator/app/persistence/subscriptions.py`
   (`read_subscription_tier`) was deliberately **not** touched: traced and
   confirmed it has zero real callers today (only its own tests) -- the
   one thing that superficially resembles a "recommendation-worker
   entitlement consumer" (`recommendation_worker.py`'s `elite_tier_present`,
   via `read_active_subscribers`) is an aggregate scheduling signal
   deciding whether to run extra per-cycle work, not a per-user access
   gate, and touching it would mean touching recommendation-worker logic,
   explicitly out of scope for this pass.

## Live database verification (before writing the permanent test files)

Every scenario below was run directly against the `dev` Supabase project
(`nhwjtsdebgiwskshzqiq`) inside a rolled-back transaction, confirmed with
zero residue afterward:

- free/pro/elite/syndicate subscribers each resolve to exactly the
  expected ladder.
- a `product:*` grant with zero subscription resolves to the full ladder;
  `has_entitlement(..., 'syndicate')` is true.
- `entitlement_capability_matches('product:*', 'product:sharing')` is
  true; `entitlement_capability_matches('product:*', 'admin:dashboard')`
  is false; a real `admin:dashboard` grant resolves to `['free']` only.
- an expired grant and a revoked grant both resolve to `['free']` only.
- a simulated different `authenticated` user (via `request.jwt.claims`)
  probing the grant holder's `user_id` directly gets `['free']` only --
  never the real grant.
- that same simulated `authenticated` session's attempt to `INSERT` its
  own `entitlement_grants` row fails with `42501` (RLS, no insert policy).
- a real `pro` subscriber with zero `entitlement_grants` rows still
  passes the `pro` gate (subscriptions untouched, unaffected).

## Tests added

- `apps/api-gateway/tests/test_entitlement.py` -- rewritten for the new
  `tier_permits(min_required_tier, permitted_tiers: list[str])` signature,
  same scenarios as before (Requirement 1: current behavior unchanged).
- `apps/api-gateway/tests/test_recommendations.py` -- one new integration
  test, a zero-subscription user with a mocked `product:*`-equivalent RPC
  response reaching a syndicate-gated product exactly like a real
  subscriber would.
- Five existing test files' `_mock_authenticated_user` helpers
  (`test_recommendations.py`, `test_recommendation_grade_contract.py`,
  `test_recommendations_ask.py`, `test_recommendation_detail.py`,
  `test_track_record.py`) updated to mock the new
  `POST /rest/v1/rpc/resolve_permitted_tiers` endpoint instead of the old
  `GET /rest/v1/subscriptions` read -- mechanical, same tier semantics.
- `supabase/tests/database/entitlement_grants_test.sql` -- new pgTAP file,
  13 assertions covering all 8 HQ-required proof points, live-executed
  and confirmed passing directly against the dev database (this sandbox
  has no local Supabase CLI, so `supabase test db` itself could not be
  run, but this file's exact assertions were verified live via `execute_sql`
  in a rolled-back transaction before being committed -- not merely
  written on faith).

**Full api-gateway suite: 187/187 passing** (186 after the refactor's own
mechanical fixture updates, +1 new integration test), zero regressions.

## Owner grant -- not created

Queried `auth.users` directly: no account matches the on-file owner email
exactly. One real account, `m.dubuisson2@outlook.com`, is similar but not
identical (different domain than the email on file) -- not a conclusive
match, per HQ's own explicit instruction not to create the grant absent
conclusive identification. No `entitlement_grants` row was created for
this or any other real user.

## Out of scope, exactly as specified

Friends & Family pricing/discount system, an admin/role authorization
system, `ai-orchestrator`'s `read_active_subscribers`/`recommendation_worker.py`
aggregate scheduling logic, Gate B, provider adapters, Context
Intelligence, staging, production.
