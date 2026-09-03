import Link from "next/link";
import { Container, Text } from "@/components/ds";
import { PublicNav } from "@/components/marketing/PublicNav";
import { PublicFooter } from "@/components/marketing/PublicFooter";
import { ScrollReveal } from "@/components/marketing/ScrollReveal";
import { getCurrentUser } from "@/app/lib/auth";

export const metadata = { title: "Features — MANSA" };

/**
 * Public Web M2 -- only real, shipped capabilities. Each description
 * below is grounded in an actual component this codebase already ships
 * (referenced in-line), never an aspirational or Phase-7-scoped claim.
 * Deliberately excludes parlays, Telegram, bet verification, sharp
 * money, and anything not yet built -- HQ's explicit M2 boundary.
 */
const FEATURES = [
  {
    title: "Today's Board",
    body: "Every recommendation MANSA has made for today's games, in one place, in the order they were decided.",
  },
  {
    title: "Recommendations",
    body: "Full detail behind every recommendation — the selection, the market, and the reasoning that produced it.",
  },
  {
    title: "AI Committee",
    body: "Multiple independent AI agents evaluate every game before MANSA commits to a decision.",
  },
  {
    title: "Modeled Probability & EV",
    body: "Where the data supports it, MANSA estimates the probability of an outcome and its expected value relative to the market price.",
  },
  {
    title: "Explainability",
    body: "Every decision shows its confidence, its evidence, and why MANSA reached it — never a black-box score.",
  },
  {
    title: "No Bet & Bankroll Preservation",
    body: "Passing is a real decision. MANSA declines when the market doesn't offer a genuine edge, and says so plainly.",
  },
  {
    title: "Time Machine",
    body: "Reconstruct any past decision exactly as it was made — the data, the committee's reasoning, and everything that happened to it since.",
  },
  {
    title: "Track Record",
    body: "A complete, unedited history of graded outcomes — wins, losses, pushes, and voids, exactly as they happened.",
  },
  {
    title: "Data Freshness & Provenance",
    body: "Know exactly how current the underlying game and market data is, every time you look.",
  },
];

export default async function FeaturesPage() {
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
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_rgb(var(--mansa-violet)/0.10),_transparent_60%)]"
          />
          <Container className="mx-auto flex max-w-2xl flex-col items-center gap-lg text-center lg:max-w-3xl">
            <Text variant="display" as="h1" className="text-4xl sm:text-5xl">
              Features
            </Text>
            <Text variant="body" className="max-w-xl text-lg text-text-secondary">
              What MANSA actually does today — nothing promised, nothing aspirational.
            </Text>
            <Link
              href={primaryCta.href}
              className="flex min-h-[44px] items-center justify-center rounded-sm bg-accent px-xl text-label font-semibold text-surface-page transition-opacity duration-micro hover:opacity-90"
            >
              {primaryCta.label}
            </Link>
          </Container>
        </section>

        <section className="border-t border-border py-3xl">
          <Container className="lg:max-w-6xl">
            <div className="grid gap-xl sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((feature, index) => (
                <ScrollReveal key={feature.title} delayMs={(index % 3) * 60}>
                  <div className="flex h-full flex-col gap-xs border-l-2 border-l-border pl-md">
                    <Text variant="heading" as="h2" className="text-lg">
                      {feature.title}
                    </Text>
                    <Text variant="body">{feature.body}</Text>
                  </div>
                </ScrollReveal>
              ))}
            </div>
          </Container>
        </section>

        <section className="border-t border-border py-3xl">
          <Container className="flex flex-col items-center gap-lg text-center">
            <ScrollReveal className="flex flex-col items-center gap-lg">
              <Text variant="heading" as="h2">
                Put it to work on today&apos;s games.
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
