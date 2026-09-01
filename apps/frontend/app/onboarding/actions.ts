"use server";

import { redirect } from "next/navigation";
import { updateOnboarding } from "@/app/lib/api";

export type OnboardingActionResult = { ok: true } | { ok: false; error: string };

/** Server Action backing the onboarding form -- runs server-side where
 * the Supabase session cookie is directly readable, so no token ever
 * needs to reach the browser for this call. `jurisdiction_state` is the
 * only field this milestone's form collects (HQ's "keep onboarding
 * short" instruction). Called directly from `OnboardingForm`'s submit
 * handler (not via `useFormState`, which requires a `react-dom` build
 * this project's plain npm dependency doesn't export outside Next's own
 * build pipeline) -- functionally identical, and matches `AuthForm`'s
 * already-established client-submit-handler pattern. */
export async function completeOnboarding(jurisdictionState: string): Promise<OnboardingActionResult> {
  if (jurisdictionState.trim() === "") {
    return { ok: false, error: "Select your state to continue." };
  }

  const result = await updateOnboarding({ jurisdiction_state: jurisdictionState });

  if (result.kind === "unauthenticated") {
    redirect("/sign-in");
  }
  if (result.kind !== "ok") {
    return { ok: false, error: "Something went wrong saving that. Try again." };
  }

  redirect("/today");
}
