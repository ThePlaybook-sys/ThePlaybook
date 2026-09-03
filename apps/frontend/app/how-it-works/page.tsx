import Link from "next/link";
import { Container, Surface, Text } from "@/components/ds";
import { PublicNav } from "@/components/marketing/PublicNav";
import { PublicFooter } from "@/components/marketing/PublicFooter";
import { ScrollReveal } from "@/components/marketing/ScrollReveal";
import { getCurrentUser } from "@/app/lib/auth";

export const metadata = { title: "How It Works — MANSA" };

const PIPELINE = [
  {
    title: "Data",
    body: "Real game, market, and situational data is gathered from sports and odds providers — schedules, rosters, injuries, weather, and the market itself.",
  },
  {
    title: "Intelligence",
    body: "That data is organized into one intelligence profile per game — matchup context, rest, and the current market, assembled before any decision is made.",
  },
  {
    title: "AI Committee",
    body: "A committee of specialized AI agents independently evaluates the game and the market, each contributing its own read before anything is combined.",
  },
  {
    title: "Decision",
    body: "The committee's agreement produces one recommendation — or the deliberate decision to make none. Both are real outcomes.",
  },
  {
    title: "Explainability",
    body: "Every decision carries its own reasoning: confidence, expected value, and the evidence behind it — never a black-box score.",
  },
  {
    title: "Time Machine",
    body: "The exact state of a decision at the moment it was made is preserved and can be reconstructed afterward, stage by stage.",
  },
  {
    title: "Grading & Track Record",
    body: "Once a game settles, the outcome is graded and added to a running, unedited track record — wins, losses, pushes, and voids alike.",
  },
];

/**
 * Public Web M2 -- the real How It Works page (M1's "coming soon"
 * placeholder is now built out). Explains the pipeline HQ specified
 * (Data -> Intelligence -> AI Committee -> Decision -> Explainability ->
 * Time Machine -> Grading/Track Record) as a restrained vertical list,
 * not seven heavy cards -- each step already correspond to a real,
 * shipped capability documented elsewhere in this codebase (Volume 4's
 * committee, `components/history/TimeMachine.tsx`'s six stages,
 * `TrackRecordSnapshot`'s real, undoctored sample). Nothing here is
 * aspirational or Phase-7-scoped.
 *
 * The two clarifications HQ explicitly required ("confidence is not win
 * probability," "No Bet is a legitimate decision") get their own
 * distinct, illuminated callouts rather than being buried in prose --
 * the same "MANSA Decision" visual treatment (illuminated top edge,
 * inset panel) the real product already uses for its own decision
 * zones, reused here for consistency, not reinvented.
 */
export default async function HowItWorksPage() {
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
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_rgb(var(--mansa-cobalt)/0.12),_transparent_60%)]"
          />
          <Container className="mx-auto flex max-w-2xl flex-col items-center gap-lg text-center lg:max-w-3xl">
            <Text variant="display" as="h1" className="text-4xl sm:text-5xl">
              How MANSA Works
            </Text>
            <Text variant="body" className="max-w-xl text-lg text-text-secondary">
              One pipeline, from raw data to a decision you can check afterward — every stage
              preserved, nothing hidden behind a score.
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
          <Container className="lg:max-w-4xl">
            <ol className="flex flex-col gap-2xl">
              {PIPELINE.map((step, index) => (
                <ScrollReveal key={step.title} delayMs={index * 60}>
                  <li className="flex gap-lg">
                    <div
                      aria-hidden="true"
                      className="mansa-illuminated-edge-top flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-t-transparent border-border bg-surface-card text-label font-semibold text-text-primary"
                    >
                      {index + 1}
                    </div>
                    <div className="flex flex-col gap-xs pt-xs">
                      <Text variant="heading" as="h2" className="text-lg">
                        {step.title}
                      </Text>
                      <Text variant="body">{step.body}</Text>
                    </div>
                  </li>
                </ScrollReveal>
              ))}
            </ol>
          </Container>
        </section>

        {/* The two required clarifications -- distinct, illuminated callouts,
            not prose asides. */}
        <section className="relative overflow-hidden border-t border-border py-3xl">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_bottom,_rgb(var(--mansa-violet)/0.10),_transparent_60%)]"
          />
          <Container className="grid gap-lg lg:max-w-5xl lg:grid-cols-2">
            <ScrollReveal>
              <Surface level="card" className="mansa-illuminated-edge-top flex h-full flex-col gap-sm border-t-2 border-t-transparent p-lg">
                <Text variant="label" as="span" className="tracking-wide">
                  Make No Mistake
                </Text>
                <Text variant="heading" as="h2" className="text-lg">
                  Confidence ≠ Win Probability
                </Text>
                <Text variant="body">
                  Confidence describes how strongly MANSA&apos;s committee agreed — not the likelihood
                  that a wager wins. Where the data supports it, MANSA separately estimates a modeled
                  probability; the two are never the same number, and neither is a promise.
                </Text>
              </Surface>
            </ScrollReveal>

            <ScrollReveal delayMs={80}>
              <Surface level="card" className="flex h-full flex-col gap-sm border-t-2 border-t-attention-amber p-lg">
                <Text variant="label" as="span" className="tracking-wide">
                  By Design
                </Text>
                <Text variant="heading" as="h2" className="text-lg">
                  No Bet Is a Legitimate Decision
                </Text>
                <Text variant="body">
                  MANSA is built to pass when the market doesn&apos;t offer real value. No Bet and
                  Bankroll Preservation are intentional, equally-weighted outcomes — never a failure to
                  find a recommendation.
                </Text>
              </Surface>
            </ScrollReveal>
          </Container>
        </section>

        <section className="border-t border-border py-3xl">
          <Container className="flex flex-col items-center gap-lg text-center">
            <ScrollReveal className="flex flex-col items-center gap-lg">
              <Text variant="heading" as="h2">
                See it on real games.
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
