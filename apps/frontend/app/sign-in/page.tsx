import { Container, Text } from "@/components/ds";
import { AuthForm } from "@/components/auth/AuthForm";
import { getCurrentUser, redirectToRootDestination } from "@/app/lib/auth";

export const metadata = { title: "Sign In — MANSA" };

/** The signed-out entry point (Phase 6 Milestone 6). A signed-in user
 * who lands here (e.g. a stale bookmark) is bounced onward via the same
 * root-routing decision `/` uses, rather than being shown a redundant
 * sign-in form. The one deliberate brand moment in the app (M7 MANSA
 * alignment): name, one-line category, and the mantra appear together
 * here and nowhere else, per HQ's "do not plaster it" instruction (now
 * joined by the public landing page's hero, per Public Web M1 -- see
 * `app/page.tsx`'s own note on this).
 *
 * `?mode=sign-up` (from the landing page's "Create Account" CTAs)
 * preselects `AuthForm`'s Create Account tab -- read here, server-side,
 * rather than by `AuthForm` itself reading the URL, so that component's
 * existing `next/navigation` test mocks stay untouched. Any value other
 * than exactly "sign-up" is treated as sign-in, matching this form's own
 * default. */
export default async function SignInPage({
  searchParams,
}: {
  searchParams: { mode?: string };
}) {
  const user = await getCurrentUser();
  if (user) {
    await redirectToRootDestination();
  }

  const initialMode = searchParams.mode === "sign-up" ? "sign-up" : "sign-in";

  return (
    <Container as="main" className="flex min-h-screen flex-col items-center justify-center gap-lg py-xl">
      <div className="flex w-full max-w-sm flex-col gap-lg">
        <div className="flex flex-col items-center gap-xs text-center">
          <Text variant="display" as="h1">
            MANSA
          </Text>
          <Text variant="label" as="p">
            Sports Intelligence
          </Text>
          <Text variant="label" as="p" className="normal-case text-text-meta">
            See the game. Know the market. Own the decision.
          </Text>
        </div>
        <AuthForm initialMode={initialMode} />
      </div>
    </Container>
  );
}
