import { Container, Text } from "@/components/ds";
import { EmptyState } from "@/components/recommendations";
import { AccountSummary } from "@/components/account/AccountSummary";
import { AppNav } from "@/components/nav/AppNav";
import { requireUser } from "@/app/lib/auth";
import { getSubscription, getUserProfile } from "@/app/lib/api";

export const metadata = { title: "Account — MANSA" };

export default async function AccountPage() {
  const user = await requireUser();
  const [profile, subscription] = await Promise.all([getUserProfile(), getSubscription()]);

  return (
    <>
      <AppNav />
      <Container as="main" className="flex flex-col gap-lg py-xl">
        <Text variant="display" as="h1">
          Account
        </Text>

        {profile.kind === "unauthenticated" && <EmptyState headline="Sign in to see your account." />}
        {profile.kind === "not_found" && (
          <EmptyState
            headline="Account profile not found."
            body="Something went wrong setting up your profile. Contact support if this persists."
          />
        )}
        {profile.kind === "error" && (
          <EmptyState
            headline="Account isn't available right now."
            body="Something went wrong reaching the account service. Try again shortly."
          />
        )}
        {profile.kind === "ok" && (
          <AccountSummary email={user.email} profile={profile.data} subscription={subscription} />
        )}
      </Container>
    </>
  );
}
