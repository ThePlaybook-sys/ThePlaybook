import { redirectToRootDestination } from "@/app/lib/auth";

/** Product entry routing only (HQ's explicit M6 boundary -- not a
 * marketing page). Resolves to /sign-in, /onboarding, or /today per
 * `resolveRootDestination`'s pure decision (app/lib/auth.ts). */
export default async function RootPage() {
  await redirectToRootDestination();
}
