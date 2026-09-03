import Link from "next/link";
import { Text } from "@/components/ds";
import { MARKETING_BODY_CLASS } from "./typography";
import { PRICING_PLANS } from "./pricingData";

/**
 * Public Web M3 -- the homepage's ONLY pricing content (HQ's explicit
 * "do not put the full comparison matrix on the homepage" instruction).
 * Three prices and one link to `/pricing` -- no entitlement list, no
 * "Most Popular" tag, no card chrome. Shares `PRICING_PLANS` with the
 * full `/pricing` page so the three numbers can never drift between the
 * two places they appear.
 */
export function PricingTeaser() {
  return (
    <div className="flex flex-col items-center gap-lg text-center">
      <Text variant="heading" as="h2">
        Simple, Tiered Pricing
      </Text>
      <Text variant="body" className={MARKETING_BODY_CLASS}>
        Three ways to get MANSA&apos;s intelligence — from Command Center essentials to the full
        conversational experience.
      </Text>

      <div className="grid w-full max-w-2xl gap-md sm:grid-cols-3">
        {PRICING_PLANS.map((plan) => (
          <div key={plan.id} className="flex flex-col items-center gap-xs rounded-sm border border-border p-md">
            <Text variant="label" as="span">
              {plan.name}
            </Text>
            <Text variant="display" as="p" className="text-2xl">
              {plan.price}
              <Text variant="label" as="span" className="ml-xs normal-case text-text-meta">
                /mo
              </Text>
            </Text>
          </div>
        ))}
      </div>

      <Link
        href="/pricing"
        className="flex min-h-[44px] items-center justify-center rounded-sm border border-border px-xl text-label text-text-primary transition-colors duration-micro hover:border-accent"
      >
        Compare Plans
      </Link>
    </div>
  );
}
