import { Container, Text } from "@/components/ds";
import { PublicNav } from "@/components/marketing/PublicNav";
import { PublicFooter } from "@/components/marketing/PublicFooter";
import { ScrollReveal } from "@/components/marketing/ScrollReveal";
import { PricingCard } from "@/components/marketing/PricingCard";
import { PricingComparisonTable } from "@/components/marketing/PricingComparisonTable";
import { MARKETING_BODY_CLASS } from "@/components/marketing/typography";
import { PRICING_PLANS } from "@/components/marketing/pricingData";
import { getCurrentUser } from "@/app/lib/auth";

export const metadata = { title: "Pricing — MANSA" };

/**
 * Public Web M3 -- the real Pricing page (M1's "coming soon" placeholder
 * is now built out, matching how M2 replaced How It Works/Features/About).
 *
 * HQ's explicit guardrails, applied throughout: monthly prices only (no
 * annual discount, no fake "save X%"), no checkout/Stripe -- every CTA
 * routes into the same `/sign-in?mode=sign-up`/`/today` pair every other
 * public page uses, never a payment flow. No invented usage numbers
 * (message counts, refresh intervals, token limits) anywhere -- the
 * comparison table's cells are exactly HQ's own qualitative values
 * (✓/—/Basic/Full/etc.), never a number. `PRICING_PLANS`/
 * `COMPARISON_ROWS` (components/marketing/pricingData.ts) are the one
 * source of truth this page and the homepage teaser both read, so the
 * numbers can't drift between the two places they appear.
 */
export default async function PricingPage() {
  const user = await getCurrentUser();
  const signedIn = user !== null;
  const ctaHref = signedIn ? "/today" : "/sign-in?mode=sign-up";
  const ctaLabel = signedIn ? "Open MANSA" : "Create Account";

  return (
    <>
      <PublicNav signedIn={signedIn} />

      <main>
        <section className="relative overflow-hidden py-3xl">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_rgb(var(--mansa-cobalt)/0.12),_transparent_60%)]"
          />
          <Container className="mx-auto flex max-w-2xl flex-col items-center gap-lg text-center lg:max-w-3xl">
            <Text variant="display" as="h1" className="text-4xl sm:text-5xl">
              Choose Your MANSA Experience
            </Text>
            <Text variant="body" className={`max-w-xl text-lg ${MARKETING_BODY_CLASS}`}>
              Three tiers of the same committee-reviewed intelligence — monthly, no contracts.
              Capability tiering shown below is MANSA&apos;s launch direction; account sign-up and
              billing enforcement are not live in DEV yet.
            </Text>
          </Container>
        </section>

        <section className="border-t border-border py-3xl">
          <Container className="lg:max-w-6xl">
            <div className="grid gap-xl pt-md sm:grid-cols-3">
              {PRICING_PLANS.map((plan, index) => (
                <ScrollReveal key={plan.id} delayMs={index * 60}>
                  <PricingCard plan={plan} ctaHref={ctaHref} ctaLabel={ctaLabel} />
                </ScrollReveal>
              ))}
            </div>
          </Container>
        </section>

        <section className="border-t border-border py-3xl">
          <Container className="lg:max-w-5xl">
            <ScrollReveal className="flex flex-col gap-xl">
              <div className="flex flex-col gap-sm text-center">
                <Text variant="heading" as="h2">
                  Compare Plans
                </Text>
                <Text variant="body" className={MARKETING_BODY_CLASS}>
                  A closer look at what each tier includes today, and what&apos;s launching with
                  MANSA.
                </Text>
              </div>
              <PricingComparisonTable />
            </ScrollReveal>
          </Container>
        </section>
      </main>

      <PublicFooter />
    </>
  );
}
