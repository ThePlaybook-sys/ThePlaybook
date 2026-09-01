import { redirect } from "next/navigation";
import { Container, Surface, Text } from "@/components/ds";
import { CoreConcepts } from "@/components/education/CoreConcepts";
import { OnboardingForm } from "@/components/onboarding/OnboardingForm";
import { requireUser } from "@/app/lib/auth";
import { getUserProfile } from "@/app/lib/api";

export const metadata = { title: "Get Started — The Playbook" };

/** Phase 6 Milestone 6. Deliberately short (HQ's explicit instruction):
 * one required field (jurisdiction_state) plus first-use education, not
 * a multi-step profile wizard. A user who already completed onboarding
 * lands here only via a stale link/back-navigation -- bounced onward
 * rather than shown a redundant step. */
export default async function OnboardingPage() {
  await requireUser();

  const profile = await getUserProfile();
  if (profile.kind === "ok" && profile.data.onboarding_completed_at) {
    redirect("/today");
  }

  return (
    <Container className="flex flex-col gap-xl py-xl">
      <div className="flex flex-col gap-sm">
        <Text variant="display" as="h1">
          Welcome to The Playbook
        </Text>
        <Text variant="body">
          A quick look at how recommendations work, then one question and you're in.
        </Text>
      </div>

      <CoreConcepts compact />

      <Surface level="card" className="flex flex-col gap-md p-lg">
        <Text variant="heading" as="h2">
          One Last Thing
        </Text>
        <OnboardingForm />
      </Surface>
    </Container>
  );
}
