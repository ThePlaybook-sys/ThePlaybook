import { Surface, Text } from "@/components/ds";
import { formatOdds } from "@/components/recommendations/RecommendationCard";

/**
 * Public Web M1 -- the landing page's one product visual (HQ's "ONE
 * strong MANSA Command Center/product visual... show enough product UI
 * to communicate this is sophisticated sports intelligence, not an
 * entire miniature dashboard").
 *
 * Deliberately a new, non-interactive presentational component rather
 * than reusing `BoardCard` directly: `BoardCard` is a real `<Link>` into
 * the authenticated `/recommendations/{displayId}` route, which would be
 * a broken/confusing destination for a signed-out marketing visitor. This
 * component reuses the exact same design tokens and visual grammar
 * (Surface levels, the MANSA Decision inset panel, Confidence/EV/Price
 * as separate instrument readings, `formatOdds`/`formatPoint`) so the
 * showcase is visually authentic to the real product, without
 * duplicating BoardCard's real-data wiring or claiming to be one.
 *
 * Product-truth compliance (HQ's explicit M1 instruction): fixed,
 * clearly-labeled illustrative content only -- never framed as a live
 * recommendation, a guarantee, or a win probability. "Confidence" is the
 * AI committee's agreement level, the same established distinction
 * `components/education/CoreConcepts.tsx` already states explicitly.
 */
export function IllustrativeDecisionCard() {
  return (
    <Surface
      level="card"
      className="mansa-illuminated-edge-top flex flex-col gap-sm border-t-2 border-t-transparent p-md sm:gap-md sm:p-lg"
    >
      <div className="flex items-center justify-between gap-md">
        <Text variant="label" as="span">
          Illustrative Example
        </Text>
        <Text variant="label" as="span" className="normal-case text-text-meta">
          Not a live recommendation
        </Text>
      </div>

      <Text variant="body" as="p" className="text-text-primary">
        Buffalo Bills @ Kansas City Chiefs
      </Text>

      <div className="flex flex-col gap-xs rounded-sm border-l-2 border-l-mansa-cobalt bg-surface-inset p-sm sm:gap-sm sm:p-md">
        <Text variant="label" as="span" className="tracking-wide">
          MANSA Decision
        </Text>

        <Text variant="display" as="p" className="text-text-primary">
          Kansas City Chiefs
        </Text>
        <Text variant="label" as="span">
          Moneyline
        </Text>

        <div className="flex flex-wrap gap-md sm:gap-lg">
          <div className="flex flex-col gap-xs">
            <Text variant="label" as="span">
              Confidence
            </Text>
            <Text variant="data" as="span" className="text-intel-cyan">
              78%
            </Text>
          </div>
          <div className="flex flex-col gap-xs border-l border-border pl-md sm:pl-lg">
            <Text variant="label" as="span">
              EV
            </Text>
            <Text variant="data" as="span" className="text-intel-cyan">
              +5.2%
            </Text>
          </div>
          <div className="flex flex-col gap-xs border-l border-border pl-md sm:pl-lg">
            <Text variant="label" as="span">
              Price
            </Text>
            <Text variant="data" as="span" className="text-intel-cyan">
              {formatOdds(-145)}
            </Text>
          </div>
        </div>

        <Text variant="body">
          Consensus favors Kansas City on value relative to the market line.
        </Text>
      </div>
    </Surface>
  );
}
