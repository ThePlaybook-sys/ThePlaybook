import Link from "next/link";
import { Container, Text } from "@/components/ds";
import { PublicNav } from "@/components/marketing/PublicNav";
import { PublicFooter } from "@/components/marketing/PublicFooter";

export const metadata = { title: "Pricing — MANSA" };

/** Public Web M1 placeholder -- see app/how-it-works/page.tsx for the
 * same M1/M2 scope note. Deliberately shows no numbers here: fabricating
 * a price ahead of the real Pricing page would be worse than a clean
 * "coming soon" state. */
export default function PricingPage() {
  return (
    <>
      <PublicNav />
      <Container as="main" className="flex min-h-[50vh] flex-col items-center justify-center gap-md py-3xl text-center">
        <Text variant="display" as="h1">
          Pricing
        </Text>
        <Text variant="body" className="max-w-lg">
          Pricing details are coming soon. In the meantime, create an account to see MANSA in
          action.
        </Text>
        <Link
          href="/sign-in?mode=sign-up"
          className="mt-md flex min-h-[44px] items-center justify-center rounded-sm bg-accent px-xl text-label font-semibold text-surface-page transition-opacity duration-micro hover:opacity-90"
        >
          Create Account
        </Link>
      </Container>
      <PublicFooter />
    </>
  );
}
