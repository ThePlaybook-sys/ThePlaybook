import Link from "next/link";
import { Container, Text } from "@/components/ds";
import { PublicNav } from "@/components/marketing/PublicNav";
import { PublicFooter } from "@/components/marketing/PublicFooter";
import { getCurrentUser } from "@/app/lib/auth";

export const metadata = { title: "How It Works — MANSA" };

/** Public Web M1 placeholder -- HQ's explicit scope: M1 builds routing
 * and navigation only; full How It Works content is M2. A clearly
 * handled page (not a broken link or 404), never fabricated content
 * pretending to be the real explanation. Auth-aware nav (Web M1 routing
 * correction): this page renders for signed-in visitors too, exactly
 * like `/`, so its nav needs the same signed-in-vs-signed-out actions. */
export default async function HowItWorksPage() {
  const user = await getCurrentUser();
  const signedIn = user !== null;

  return (
    <>
      <PublicNav signedIn={signedIn} />
      <Container as="main" className="flex min-h-[50vh] flex-col items-center justify-center gap-md py-3xl text-center">
        <Text variant="display" as="h1">
          How It Works
        </Text>
        <Text variant="body" className="max-w-lg">
          {signedIn
            ? "The full walkthrough is coming soon."
            : "The full walkthrough is coming soon. In the meantime, create an account to see MANSA in action."}
        </Text>
        <Link
          href={signedIn ? "/today" : "/sign-in?mode=sign-up"}
          className="mt-md flex min-h-[44px] items-center justify-center rounded-sm bg-accent px-xl text-label font-semibold text-surface-page transition-opacity duration-micro hover:opacity-90"
        >
          {signedIn ? "Open MANSA" : "Create Account"}
        </Link>
      </Container>
      <PublicFooter />
    </>
  );
}
