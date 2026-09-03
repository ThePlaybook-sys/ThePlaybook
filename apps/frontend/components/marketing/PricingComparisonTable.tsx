import { Text } from "@/components/ds";
import { MARKETING_BODY_CLASS } from "./typography";
import { COMPARISON_ROWS } from "./pricingData";

function ComparisonValue({ value }: { value: string }) {
  if (value === "✓") return <span aria-label="Included">✓</span>;
  if (value === "—") return <span aria-label="Not included">—</span>;
  return <>{value}</>;
}

/**
 * Public Web M3 -- the full capability comparison, responsive via the
 * same horizontal-scroll idiom `AppNav` already established for its own
 * overflow ("scrolls horizontally rather than wrapping or overflowing")
 * rather than a second responsive pattern. A real `<table>` (not a div
 * grid pretending to be one) so screen readers get real row/column
 * header semantics -- `scope="col"`/`scope="row"` throughout.
 *
 * Rows whose capability doesn't exist in ANY operational form in DEV
 * yet (Telegram Companion, Conversational MANSA, Intelligent Parlays,
 * Market Intelligence, Bet Timing, Advanced Alerts) get a single `†`
 * marker on the row label plus one shared legend line below the table
 * -- HQ's explicit "distinguish...without cluttering every row with
 * badges" instruction. Rows whose underlying capability already ships
 * today (Explainability, Time Machine, Freshness Priority) get no
 * marker even though their specific tier differentiation isn't
 * enforced anywhere yet -- that caveat applies to the whole table
 * equally and is stated once, in `/pricing/page.tsx`'s own intro
 * copy, not per-row.
 */
export function PricingComparisonTable() {
  return (
    <div className="flex flex-col gap-md">
      <div className="overflow-x-auto" style={{ scrollbarWidth: "none" }}>
        <table className="w-full min-w-[560px] border-collapse text-left">
          <thead>
            <tr className="border-b border-border">
              <th scope="col" className="py-sm pr-md">
                <Text variant="label" as="span">
                  Capability
                </Text>
              </th>
              <th scope="col" className="px-sm py-sm text-center">
                <Text variant="label" as="span">
                  Core
                </Text>
              </th>
              <th scope="col" className="px-sm py-sm text-center">
                <Text variant="label" as="span">
                  Pro
                </Text>
              </th>
              <th scope="col" className="px-sm py-sm text-center">
                <Text variant="label" as="span">
                  Elite
                </Text>
              </th>
            </tr>
          </thead>
          <tbody>
            {COMPARISON_ROWS.map((row) => (
              <tr key={row.label} className="border-b border-border">
                <th scope="row" className="py-sm pr-md text-left font-normal">
                  <Text variant="body" as="span" className={MARKETING_BODY_CLASS}>
                    {row.label}
                    {row.notYetOperational && (
                      <>
                        <sup aria-hidden="true">†</sup>
                        <span className="sr-only"> (not yet operational in DEV)</span>
                      </>
                    )}
                  </Text>
                </th>
                <td className="px-sm py-sm text-center">
                  <Text variant="body" as="span" className={MARKETING_BODY_CLASS}>
                    <ComparisonValue value={row.core} />
                  </Text>
                </td>
                <td className="px-sm py-sm text-center">
                  <Text variant="body" as="span" className={MARKETING_BODY_CLASS}>
                    <ComparisonValue value={row.pro} />
                  </Text>
                </td>
                <td className="px-sm py-sm text-center">
                  <Text variant="body" as="span" className={MARKETING_BODY_CLASS}>
                    <ComparisonValue value={row.elite} />
                  </Text>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Text variant="label" as="p" className="normal-case text-text-meta">
        † Not yet operational in DEV — launching with MANSA.
      </Text>
    </div>
  );
}
