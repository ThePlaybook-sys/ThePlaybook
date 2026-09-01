import Link from "next/link";
import { Container, Surface, Text } from "@/components/ds";
import { CoreConcepts } from "@/components/education/CoreConcepts";
import { AppNav } from "@/components/nav/AppNav";
import { requireUser } from "@/app/lib/auth";

export const metadata = { title: "How The Playbook Works — The Playbook" };

/** Reopenable from Account at any time (HQ's explicit M6 requirement),
 * not a one-time onboarding-only screen. No performance claims are made
 * here -- Track Record's own page is the one place actual graded
 * history is shown, and even there only as authoritative counts. */
export default async function HowItWorksPage() {
  await requireUser();

  return (
    <>
      <AppNav />
      <Container className="flex flex-col gap-xl py-xl">
        <div className="flex flex-col gap-sm">
          <Text variant="display" as="h1">
            How The Playbook Works
          </Text>
          <Text variant="body">
            A plain-language look at how a recommendation gets made, and how you can check our
            work later.
          </Text>
        </div>

        <CoreConcepts />

        <Surface level="card" className="flex flex-col gap-md p-lg">
          <Text variant="heading" as="h2">
            The Recommendation Process
          </Text>
          <Text variant="body">
            Every recommendation comes from a committee of specialized AI agents reviewing a game
            or market independently, then reconciling their views into one consensus. When the
            committee doesn&apos;t find a play that clears its confidence bar, the recommendation
            is No Bet -- itself a real product decision, not a gap.
          </Text>
        </Surface>

        <Surface level="card" className="flex flex-col gap-md p-lg">
          <Text variant="heading" as="h2">
            Historical Transparency
          </Text>
          <Text variant="body">
            <Link href="/history" className="text-accent underline">
              Time Machine
            </Link>{" "}
            reconstructs exactly what was known and recommended at the moment of each decision --
            never edited by anything learned afterward.
          </Text>
          <Text variant="body">
            <Link href="/track-record" className="text-accent underline">
              Track Record
            </Link>{" "}
            shows the authoritative graded record of past recommendation products, with sample
            size always visible.
          </Text>
        </Surface>
      </Container>
    </>
  );
}
