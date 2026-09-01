import { Container, Text } from "@/components/ds";
import { AuthForm } from "@/components/auth/AuthForm";
import { getCurrentUser, redirectToRootDestination } from "@/app/lib/auth";

export const metadata = { title: "Sign In — The Playbook" };

/** The signed-out entry point (Phase 6 Milestone 6). A signed-in user
 * who lands here (e.g. a stale bookmark) is bounced onward via the same
 * root-routing decision `/` uses, rather than being shown a redundant
 * sign-in form. */
export default async function SignInPage() {
  const user = await getCurrentUser();
  if (user) {
    await redirectToRootDestination();
  }

  return (
    <Container className="flex min-h-screen flex-col items-center justify-center gap-lg py-xl">
      <div className="flex w-full max-w-sm flex-col gap-lg">
        <Text variant="display" as="h1" className="text-center">
          The Playbook
        </Text>
        <AuthForm />
      </div>
    </Container>
  );
}
