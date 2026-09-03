import Link from "next/link";
import { Surface, Text } from "@/components/ds";
import { MARKETING_BODY_CLASS } from "./typography";
import type { PricingPlan } from "./pricingData";

export interface PricingCardProps {
  plan: PricingPlan;
  ctaHref: string;
  ctaLabel: string;
}

/**
 * Public Web M3 -- one plan card. Deliberately concise (HQ's explicit
 * "do not stuff every entitlement into them" instruction): a name, a
 * price, one tagline, and a short highlight list -- the full capability
 * breakdown lives only in `PricingComparisonTable` below it on
 * `/pricing`, never duplicated here.
 *
 * Visual distinction reuses existing, already-established roles rather
 * than inventing new ones: Pro's "Most Popular" tag uses `bg-accent`
 * (MANSA Cobalt, the same "real, primary action" color every CTA
 * button on these pages already uses -- Pro is the recommended default
 * action). Elite gets `mansa-illuminated-edge-top`, the same cobalt-to-
 * violet premium treatment already used for every other "MANSA Decision"
 * zone and the Elite-adjacent "coming at launch" language elsewhere --
 * violet's documented role is "identity/premium depth," which is
 * exactly what the top tier needs, without introducing a new color.
 */
export function PricingCard({ plan, ctaHref, ctaLabel }: PricingCardProps) {
  return (
    <Surface
      level={plan.mostPopular ? "elevated" : "card"}
      className={`relative flex h-full flex-col gap-md p-lg ${
        plan.id === "elite" ? "mansa-illuminated-edge-top border-t-2 border-t-transparent" : ""
      }`}
    >
      {plan.mostPopular && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-sm bg-accent px-md py-xs text-label font-semibold uppercase tracking-wide text-surface-page">
          Most Popular
        </span>
      )}

      <div className="flex flex-col gap-xs">
        <Text variant="heading" as="h3">
          {plan.name}
        </Text>
        <div className="flex items-baseline gap-xs">
          <Text variant="display" as="p" className="text-3xl">
            {plan.price}
          </Text>
          <Text variant="label" as="span" className="normal-case text-text-meta">
            /mo
          </Text>
        </div>
        <Text variant="body" className={MARKETING_BODY_CLASS}>
          {plan.tagline}
        </Text>
      </div>

      <ul className="flex flex-col gap-xs">
        {plan.highlights.map((highlight) => (
          <li key={highlight} className="flex items-start gap-xs">
            <span aria-hidden="true" className="text-accent">
              ✓
            </span>
            <Text variant="body" as="span" className={MARKETING_BODY_CLASS}>
              {highlight}
            </Text>
          </li>
        ))}
      </ul>

      <Link
        href={ctaHref}
        className="mt-auto flex min-h-[44px] items-center justify-center rounded-sm bg-accent px-lg text-label font-semibold text-surface-page transition-opacity duration-micro hover:opacity-90"
      >
        {ctaLabel}
      </Link>
    </Surface>
  );
}
