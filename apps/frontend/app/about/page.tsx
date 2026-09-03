import Link from "next/link";
import { Container, Text } from "@/components/ds";
import { PublicNav } from "@/components/marketing/PublicNav";
import { PublicFooter } from "@/components/marketing/PublicFooter";
import { ScrollReveal } from "@/components/marketing/ScrollReveal";
import { getCurrentUser } from "@/app/lib/auth";

export const metadata = { title: "About — MANSA" };

/**
 * Public Web M2 -- why MANSA exists, in plain language. No founder
 * history, no fabricated stats, no testimonials -- HQ's explicit
 * instruction. Personality comes from voice and conviction, not from
 * invented claims.
 */
export default async function AboutPage() {
  const user = await getCurrentUser();
  const signedIn = user !== null;
  const primaryCta = signedIn
    ? { href: "/today", label: "Open MANSA" }
    : { href: "/sign-in?mode=sign-up", label: "Create Account" };

  return (
    <>
      <PublicNav signedIn={signedIn} />

      <main>
        <section className="relative overflow-hidden py-3xl">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_rgb(var(--mansa-cobalt)/0.10),_transparent_50%),radial-gradient(ellipse_at_bottom,_rgb(var(--mansa-violet)/0.08),_transparent_55%)]"
          />
          <Container className="mx-auto flex max-w-2xl flex-col items-center gap-lg text-center lg:max-w-3xl">
            <Text variant="display" as="h1" className="text-4xl sm:text-5xl">
              About MANSA
            </Text>
            <Text variant="body" className="max-w-xl text-lg text-text-secondary">
              Sports betting information is everywhere. Almost none of it is organized, and most of
              it isn&apos;t built to be checked.
            </Text>
          </Container>
        </section>

        <section className="border-t border-border py-3xl">
          <Container className="mx-auto flex max-w-2xl flex-col gap-2xl lg:max-w-3xl">
            <ScrollReveal className="flex flex-col gap-md">
              <Text variant="heading" as="h2">
                Why MANSA Exists
              </Text>
              <Text variant="body">
                Odds boards, injury reports, national narratives, gut feel — the information a bettor
                needs is scattered across a dozen places, most of it noise dressed up as insight.
                MANSA exists to put that information in one place, run it through a committee of AI
                agents instead of a single opinion, and hand back one decision at a time — with the
                reasoning behind it always available to check.
              </Text>
            </ScrollReveal>

            <ScrollReveal delayMs={80} className="flex flex-col gap-md">
              <Text variant="heading" as="h2">
                How We Think About This
              </Text>
              <Text variant="body">
                MANSA isn&apos;t built to be right every time — it&apos;s built to be checked every
                time. Confidence is never sold as a promise. A pass is treated as seriously as a play.
                And every decision stays reconstructable long after it&apos;s made, because a system
                that can&apos;t show its work isn&apos;t intelligence — it&apos;s just another hot
                take with better production values.
              </Text>
            </ScrollReveal>
          </Container>
        </section>

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
