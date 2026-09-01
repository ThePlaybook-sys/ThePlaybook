import { redirect } from "next/navigation";
import { createClient } from "./supabase/server";
import { getUserProfile } from "./api";

export type RootDestination = "/sign-in" | "/onboarding" | "/today";

/**
 * Pure routing decision (HQ's M6 root/entry requirement) -- kept
 * separate from any Supabase/Next.js call so it can be unit tested
 * directly against real-shaped inputs, not by mocking the auth
 * architecture itself.
 *
 *   signed out                          -> /sign-in
 *   signed in, onboarding incomplete    -> /onboarding
 *   signed in, onboarding complete      -> /today
 *
 * "Onboarding complete" is read from `user_profiles.onboarding_completed_at`
 * (non-null) -- the same authoritative signal `PATCH /v1/user/profile`
 * (Phase 2 Milestone 4) already writes, not a new business rule.
 * `hasProfile=false` (no `user_profiles` row readable, e.g. a genuine
 * 404) is treated as onboarding-incomplete: it can only mean the
 * profile hasn't been created for a signed-in user, never that
 * onboarding is somehow already done.
 */
export function resolveRootDestination(input: {
  signedIn: boolean;
  hasProfile: boolean;
  onboardingCompletedAt: string | null;
}): RootDestination {
  if (!input.signedIn) return "/sign-in";
  if (!input.hasProfile || !input.onboardingCompletedAt) return "/onboarding";
  return "/today";
}

/** Server-only: the currently authenticated user's id/email, or null. */
export async function getCurrentUser(): Promise<{ id: string; email: string | null } | null> {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;
  return { id: user.id, email: user.email ?? null };
}

/** Server-only: redirects to `/sign-in` if no authenticated user exists. */
export async function requireUser(): Promise<{ id: string; email: string | null }> {
  const user = await getCurrentUser();
  if (!user) redirect("/sign-in");
  return user;
}

/**
 * Server-only: resolves and performs the root-entry redirect for the
 * current request. Used by `/`, and by `/onboarding` and `/sign-in`
 * themselves to bounce a user who is already past that step onward
 * rather than re-showing a stale step.
 */
export async function redirectToRootDestination(): Promise<never> {
  const user = await getCurrentUser();
  if (!user) redirect("/sign-in");

  const profile = await getUserProfile();
  const destination = resolveRootDestination({
    signedIn: true,
    hasProfile: profile.kind === "ok",
    onboardingCompletedAt: profile.kind === "ok" ? profile.data.onboarding_completed_at : null,
  });
  redirect(destination);
}
