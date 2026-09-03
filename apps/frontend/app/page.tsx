import Link from "next/link";
import { Container, Text } from "@/components/ds";
import { PublicNav } from "@/components/marketing/PublicNav";
import { PublicFooter } from "@/components/marketing/PublicFooter";
import { ScrollReveal } from "@/components/marketing/ScrollReveal";
import { IllustrativeDecisionCard } from "@/components/marketing/IllustrativeDecisionCard";
import { MARKETING_BODY_CLASS } from "@/components/marketing/typography";
import { getCurrentUser } from "@/app/lib/auth";

export const metadata = { title: "MANSA — Sports Intelligence" };

/**
 * Public Web M1 -- `/` is the public MANSA landing page.
 *
 * Web M1 routing correction (Mac's live mobile validation, 2026-09-02):
 * `/` previously redirected a signed-in visitor straight to
 * `/onboarding`/`/today`, so an authenticated visitor manually revisiting
 * `/` never saw the marketing page at all -- confirmed as the root cause
 * of that report (this file's own earlier `if (user) { ... redirect(...) }`
 * branch). `/` now ALWAYS renders this page for every visitor, signed in
 * or not; the authenticated product's real entry point is `/today`, not
 * `/`. This does not weaken any route guard -- `/onboarding`, `/account`,
 * and every other authenticated route still call `requireUser()`/their
 * own `resolveRootDestination`-based check exactly as before (both
 * untouched, still covered by their own existing tests); only `/`
 * itself no longer redirects.
 *
 * `getCurrentUser()` is still called here -- not to gate rendering, but
 * to drive the one thing that legitimately differs for a signed-in
 * visitor: the nav's actions ("Account"/"Open MANSA" instead of "Sign
 * In"/"Create Account", per HQ's explicit auth-aware-nav requirement)
 * and this page's own CTAs, which would otherwise nonsensically invite
 * an already-registered visitor to create a second account.
 *
 * Note on the mantra: `app/sign-in/page.tsx`'s own comment describes
 * "MANSA / Sports Intelligence / mantra" as a brand moment appearing
 * "here and nowhere else" (M7 alignment). HQ's explicit Public Web M1
 * brief places the same mantra in this page's hero, which supersedes
 * that "nowhere else" scope now that a public landing page exists as a
 * second legitimate brand-moment context -- flagged here rather than
 * silently overridden.
 */
export default async function RootPage() {
  const user = await getCurrentUser();
  const signedIn = user !== null;
  const primaryCta = signedIn
    ? { href: "/today", label: "Open MANSA" }
    : { href: "/sign-in?mode=sign-up", label: "Create Account" };

  return (
    <>
      <PublicNav signedIn={signedIn} />

      <main>
        {/* Hero -- kept especially clean per HQ's "first viewport" instruction:
            headline, one supporting sentence, two CTAs, one restrained product
            visual. A single low-key ambient gradient (not a particle/data
            animation) sits behind the copy -- static under
            prefers-reduced-motion via globals.css's own global rule, and
            purely decorative (aria-hidden) either way. */}
        <section className="relative overflow-hidden py-3xl">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_rgb(var(--mansa-cobalt)/0.12),_transparent_60%)]"
          />
          <Container className="flex flex-col items-center gap-2xl text-center lg:max-w-6xl">
            <div className="flex max-w-2xl flex-col items-center gap-lg">
              <Text variant="display" as="h1" className="text-4xl sm:text-5xl lg:text-6xl">
                See the game.
                <br />
                Know the market.
                <br />
                Own the decision.
              </Text>
              <Text variant="body" className={`max-w-xl text-lg ${MARKETING_BODY_CLASS}`}>
                MANSA runs a committee of AI agents against the market in real time, then shows you
                exactly how it reached its conclusion — so every decision is yours, made with full
                visibility into the reasoning behind it.
              </Text>
              <div className="flex flex-col gap-sm sm:flex-row">
                <Link
                  href={primaryCta.href}
                  className="flex min-h-[44px] items-center justify-center rounded-sm bg-accent px-xl text-label font-semibold text-surface-page transition-opacity duration-micro hover:opacity-90"
                >
                  {primaryCta.label}
                </Link>
                <Link
                  href="/how-it-works"
                  className="flex min-h-[44px] items-center justify-center rounded-sm border border-border px-xl text-label text-text-primary transition-colors duration-micro hover:border-accent"
                >
                  See How It Works
                </Link>
              </div>
            </div>

            <ScrollReveal className="w-full max-w-md">
              <IllustrativeDecisionCard />
            </ScrollReveal>
          </Container>
        </section>

        {/* What MANSA Does -- one concise section, three short pillars, no
            icon wall. */}
        <section className="border-t border-border py-3xl">
          <Container className="flex flex-col gap-2xl lg:max-w-6xl">
            <ScrollReveal className="mx-auto flex max-w-2xl flex-col gap-md text-center">
              <Text variant="heading" as="h2">
                What MANSA Does
              </Text>
              <Text variant="body" className={MARKETING_BODY_CLASS}>
                A committee of specialized AI agents reads the game, the market, and the surrounding
                intelligence together — then converges on one recommendation, or the deliberate
                decision to make none at all.
              </Text>
            </ScrollReveal>

            <div className="grid gap-xl sm:grid-cols-3">
              {[
                {
                  title: "Committee Analysis",
                  body: "Multiple independent agents evaluate every angle, and only converge when they genuinely agree.",
                },
                {
                  title: "Full Reasoning",
                  body: "Every recommendation carries the confidence, value, and evidence behind it — never a black box.",
                },
                {
                  title: "Real Discipline",
                  body: "No Bet is a legitimate outcome. MANSA passes when the market doesn't offer a real edge.",
                },
              ].map((item, index) => (
                <ScrollReveal key={item.title} delayMs={index * 80}>
                  <div className="flex flex-col gap-xs">
                    <Text variant="heading" as="h3" className="text-lg">
                      {item.title}
                    </Text>
                    <Text variant="body" className={MARKETING_BODY_CLASS}>
                      {item.body}
                    </Text>
                  </div>
                </ScrollReveal>
              ))}
            </div>
          </Container>
        </section>

        {/* Product / Command Center showcase -- the one deeper look at real
            product UI, distinct from the hero's more compact glimpse. */}
        <section className="border-t border-border py-3xl">
          <Container className="grid gap-2xl lg:max-w-6xl lg:grid-cols-2 lg:items-center">
            <ScrollReveal className="flex flex-col gap-md">
              <Text variant="heading" as="h2">
                The MANSA Command Center
              </Text>
              <Text variant="body" className={MARKETING_BODY_CLASS}>
                Every recommendation ships with the full picture behind it — confidence, expected
                value, and market price, presented together, never separately. Nothing is hidden
                behind a summary score.
              </Text>
            </ScrollReveal>

            <ScrollReveal delayMs={100} className="mx-auto w-full max-w-md">
              <IllustrativeDecisionCard />
            </ScrollReveal>
          </Container>
        </section>

        {/* Transparency / process teaser -- real, already-shipped capability
            (Time Machine reproducibility), described plainly. No Phase 7
            anomaly-detection claims. */}
        <section className="border-t border-border py-3xl">
          <Container className="mx-auto flex max-w-2xl flex-col gap-md text-center lg:max-w-3xl">
            <ScrollReveal className="flex flex-col gap-md">
              <Text variant="heading" as="h2">
                Built to Be Checked
              </Text>
              <Text variant="body" className={MARKETING_BODY_CLASS}>
                Every MANSA decision is reconstructable after the fact — the exact reasoning, timing,
                and market data behind it, preserved and available to review. Confidence describes
                how strongly MANSA&apos;s committee agreed, not a promised outcome.
              </Text>
            </ScrollReveal>
          </Container>
        </section>

        {/* Final CTA */}
        <section className="border-t border-border py-3xl">
          <Container className="flex flex-col items-center gap-lg text-center">
            <ScrollReveal className="flex flex-col items-center gap-lg">
              <Text variant="heading" as="h2">
                Own the decision.
              </Text>
              <Link
                href={primaryCta.href}
                className="flex min-h-[44px] items-center justify-center rounded-sm bg-accent px-xl text-label font-semibold text-surface-page transition-opacity duration-micro hover:opacity-90"
              >
                {primaryCta.label}
              </Link>
            </ScrollReveal>
          </Container>
        </section>
      </main>

      <PublicFooter />
    </>
  );
}
