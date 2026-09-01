import Link from "next/link";
import { Surface, Text } from "@/components/ds";
import { formatDateTime } from "@/app/lib/format";
import type { ApiResult, SubscriptionData, UserProfile } from "@/app/lib/api-types";

export interface AccountSummaryProps {
  email: string | null;
  profile: UserProfile;
  subscription: ApiResult<SubscriptionData>;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-border-default py-xs last:border-b-0">
      <Text variant="label" as="span">
        {label}
      </Text>
      <Text variant="body" as="span" className="text-text-primary">
        {value}
      </Text>
    </div>
  );
}

/**
 * Only authorized, already-contracted user-specific data is shown here
 * (HQ's explicit M6 boundary) -- no invented settings, no paywall/
 * locked-content UX, no reinterpretation of tier/entitlement semantics.
 * `subscription.tier === null` is a real, honest "no active
 * subscription" state, never defaulted to a fabricated "free" tier
 * (matches `app.subscription`'s own "never default to any tier" rule).
 */
export function AccountSummary({ email, profile, subscription }: AccountSummaryProps) {
  return (
    <div className="flex flex-col gap-lg">
      <Surface level="card" className="flex flex-col gap-md p-lg">
        <Text variant="heading" as="h2">
          Account
        </Text>
        <div className="flex flex-col">
          <Row label="Email" value={email ?? "—"} />
          <Row label="State" value={profile.jurisdiction_state ?? "Not set"} />
        </div>
      </Surface>

      <Surface level="card" className="flex flex-col gap-md p-lg">
        <Text variant="heading" as="h2">
          Subscription
        </Text>
        {subscription.kind === "ok" && subscription.data.tier === null && (
          <Text variant="body">No active subscription.</Text>
        )}
        {subscription.kind === "ok" && subscription.data.tier !== null && (
          <div className="flex flex-col">
            <Row label="Tier" value={subscription.data.tier} />
            <Row label="Status" value={subscription.data.status ?? "—"} />
            {subscription.data.billingPeriod && (
              <Row label="Billing Period" value={subscription.data.billingPeriod} />
            )}
            {subscription.data.currentPeriodEnd && (
              <Row label="Renews" value={formatDateTime(subscription.data.currentPeriodEnd)} />
            )}
          </div>
        )}
        {subscription.kind !== "ok" && (
          <Text variant="body">Subscription details aren&apos;t available right now.</Text>
        )}
      </Surface>

      <Surface level="card" className="flex flex-col gap-md p-lg">
        <Link href="/account/how-it-works" className="text-body text-accent underline">
          How The Playbook Works
        </Link>
      </Surface>

      <form action="/auth/sign-out" method="post">
        <button
          type="submit"
          className="min-h-[44px] w-full rounded-sm border border-border-default px-md py-sm text-base text-text-secondary"
        >
          Sign Out
        </button>
      </form>
    </div>
  );
}
