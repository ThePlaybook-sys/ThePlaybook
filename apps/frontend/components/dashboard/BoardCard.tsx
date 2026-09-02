import Link from "next/link";
import { Surface, Text, StateBadge } from "@/components/ds";
import { formatOdds, formatPoint, GradeBadge, FreshnessLabel } from "@/components/recommendations";
import { formatDateTime } from "@/app/lib/format";
import type { RecommendationCardData, RecommendationLeg } from "@/app/lib/api-types";

export interface BoardCardProps {
  recommendation: RecommendationCardData;
}

/** Short, authoritative decision-value copy for the two "passing" product
 * types -- reuses the exact vocabulary `recentDecisionState.ts` already
 * established and tests for Recent Decisions, never a third variant of
 * the same concept. Not a fabrication: it labels the already-persisted
 * `recommendationType` enum value, the same way `GRADE_LABEL` labels
 * `GradeOutcome`. */
function passingDecisionLabel(recommendationType: RecommendationCardData["recommendationType"]): string {
  return recommendationType === "no_bet" ? "No Bet" : "Bankroll Preservation";
}

/** Human label for the market-type enum -- not a fabrication, the same
 * enum-to-copy mapping `GRADE_LABEL` already uses for `GradeOutcome`.
 * M7.5's contract audit confirmed the schema has no separate free-text
 * "market qualifier"/promo-line field (`market_type` is a hard
 * CHECK-constrained enum: moneyline/spread/total/prop) -- this label is
 * the most specific market descriptor the real contract can safely
 * produce without inventing betting semantics. */
function marketTypeLabel(marketType: RecommendationLeg["marketType"]): string {
  switch (marketType) {
    case "moneyline":
      return "Moneyline";
    case "spread":
      return "Spread";
    case "total":
      return "Total";
    case "prop":
      return "Player Prop";
  }
}

/**
 * EV as a signed percentage, e.g. `+6.3%` / `-2.0%`. Sign is purely
 * numeric -- never colored positive/negative (HQ's explicit M7.2
 * instruction: positive EV is not equivalent to a winning outcome, so
 * this must never borrow the WIN/LOSS emerald/coral vocabulary).
 */
function formatEv(evPerDollar: number): string {
  const pct = evPerDollar * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

/** One instrument reading (§9/§11): small uppercase label, tabular data
 * value tinted Intelligence Cyan -- M7.4's restrained "this is an
 * analytical reading, not the decision itself" signal, deliberately a
 * different color role than the MANSA-Cobalt-tinted decision value above
 * it. Never a gauge, meter, or decorative chart. A subtle left divider
 * (skipped on the first metric) replaces the earlier bare gap, per
 * HQ's "subtle separators" instruction. */
function InstrumentMetric({ label, value, first = false }: { label: string; value: string; first?: boolean }) {
  return (
    <div className={`flex flex-col gap-xs ${first ? "" : "border-l border-border pl-md sm:pl-lg"}`}>
      <Text variant="label" as="span">
        {label}
      </Text>
      <Text variant="data" as="span" className="text-intel-cyan">
        {value}
      </Text>
    </div>
  );
}

/** BoardCard-only leg row -- deliberately parallel to, not a reuse of,
 * `LegLine` (which stays untouched for `RecommendationCard`,
 * `RecommendationDetail`, and Time Machine so this restyle carries zero
 * risk to those pages). The selection itself is the MANSA Decision value
 * (M7.4 §4) -- rendered at `display` scale, deliberately larger than the
 * `data`-scale instrument metrics beneath it, so the decision visually
 * dominates the analysis that supports it, never the reverse. Always the
 * full, authoritative `leg.selection` string verbatim -- M7.5's contract
 * audit confirmed no shortened/abbreviated team-name field exists
 * anywhere in the schema, so this never invents one (HQ's explicit "do
 * not invent a shortened team name" rule); de-emphasis for a long
 * selection comes from the subordinate market-type line beneath it, not
 * from truncating or fabricating the selection itself. */
function BoardCardDecisionLeg({ leg }: { leg: RecommendationLeg }) {
  return (
    <div className="flex flex-col gap-xs sm:gap-sm">
      <Text variant="display" as="p" className="text-text-primary">
        {leg.selection}
        {formatPoint(leg.point)}
      </Text>
      <Text variant="label" as="span">
        {marketTypeLabel(leg.marketType)}
      </Text>
      <div className="flex flex-wrap gap-md sm:gap-lg">
        <InstrumentMetric
          first
          label="Confidence"
          value={`${Math.round(leg.finalAggregateConfidence * 100)}%`}
        />
        <InstrumentMetric label="EV" value={formatEv(leg.evPerDollar)} />
        <InstrumentMetric label="Price" value={formatOdds(leg.americanOdds)} />
      </div>
    </div>
  );
}

/**
 * Today's Board's own card presentation -- a genuinely different
 * composition from `RecommendationCard`'s list-view layout, not the same
 * card dropped into a CSS grid.
 *
 * M7.4's hierarchy correction (HQ's populated-review finding): a card's
 * GAME CONTEXT (which matchup this is) and its MANSA DECISION (what
 * MANSA concluded) are not visually equivalent information and must
 * never be presented as such. The matchup is always shown directly from
 * `game.awayTeam`/`game.homeTeam` -- for every recommendation type,
 * including `no_bet`, so a game-specific decline never reads as an
 * anonymous card with only a kickoff time (HQ's explicit M7.4 §5
 * correction). The MANSA Decision -- the selection for an active/graded
 * product, or the authoritative "No Bet"/"Bankroll Preservation" label
 * for a passing one -- sits in its own raised inset panel with a
 * MANSA-Cobalt-or-Attention-Amber edge accent (Level 3->4 depth cue,
 * §7/§8) and dominant `display`-scale typography, so it is legible as
 * "the answer" within about a second, never blended into the rest of
 * the card.
 *
 * `RecommendationCard` itself is intentionally untouched by this
 * component -- `/recommendations` and `/history` keep their own tested
 * list-view rendering; this is a new sibling, not a modification.
 *
 * One card per recommendation PRODUCT, never merged: if two products
 * share a game, each renders its own full BoardCard here, at equal
 * visual weight, in whatever order the API already returned them -- this
 * component never groups, ranks, or hides one in favor of another.
 *
 * No_bet/bankroll_preservation render as a real, equal-weight MANSA
 * decision -- same Surface level and card structure as an active
 * recommendation, never smaller or "empty" framed. Its top edge and
 * decision-zone accent are a restrained solid Attention Amber instead of
 * the cobalt-to-violet MANSA Illumination -- a deliberate, non-error
 * visual signal ("MANSA evaluated the opportunity and deliberately
 * declined it"), never a second color meaning layered onto the same
 * edge. Bankroll Preservation (slate-scoped, no game) never gets a
 * fabricated matchup or kickoff time -- its game-context zone reads
 * "Today's Slate" exactly as it always has.
 *
 * M7.5 refinement: a contract audit (ai-orchestrator's candidate
 * generation, the `recommendation_legs` migration, and this file's own
 * consuming types) confirmed `leg.selection` is always the provider's
 * raw outcome name -- a clean team/side/player string, never a compound
 * string with market-qualifier text baked in, and the schema has no
 * separate free-text qualifier field to split out. So the decision value
 * always renders the full, authoritative selection verbatim (never
 * shortened/abbreviated); the new market-type line beneath it (Moneyline/
 * Spread/Total/Player Prop, the same enum-to-copy pattern `GRADE_LABEL`
 * already uses) is the one additional, safely-derivable piece of context
 * HQ's "PRIMARY SELECTION / MARKET / PRICE" separation asked for.
 * Padding and gaps are now responsive (tighter below the `sm` breakpoint)
 * for mobile information density -- typography sizes are unchanged, per
 * HQ's explicit "do not solve density by shrinking fonts" instruction.
 */
export function BoardCard({ recommendation }: BoardCardProps) {
  const isPassing =
    recommendation.recommendationType === "no_bet" ||
    recommendation.recommendationType === "bankroll_preservation";
  const game = recommendation.game;
  const gameStatusIsNotable = game !== null && game.status !== "scheduled";
  const isUngradedActiveDecision =
    !isPassing && recommendation.status === "active" && recommendation.grade === null;

  return (
    <Link
      href={`/recommendations/${recommendation.displayId}`}
      className="block rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
    >
      <Surface
        level="card"
        className={`flex flex-col gap-sm border-t-2 p-md transition-colors hover:border-accent sm:gap-md sm:p-lg ${
          isPassing ? "border-t-attention-amber" : "mansa-illuminated-edge-top border-t-transparent"
        }`}
        data-recommendation-type={recommendation.recommendationType}
        data-recommendation-status={recommendation.status}
      >
        {/* Game context -- always the real matchup, for every
            recommendation type, never inferred from a timestamp alone. */}
        <div className="flex flex-col gap-xs">
          <Text variant="body" as="h2" className="text-text-primary">
            {game ? `${game.awayTeam} @ ${game.homeTeam}` : "Today's Slate"}
          </Text>
          {game && (
            <div className="flex items-baseline justify-between gap-md">
              <Text variant="label" as="span">
                {formatDateTime(game.scheduledStart)}
              </Text>
              {gameStatusIsNotable && (
                <Text variant="label" as="span">
                  {game.status}
                </Text>
              )}
            </div>
          )}
        </div>

        {/* MANSA Decision -- a distinct raised plane, never blended into
            the game context above it. */}
        <div
          className={`flex flex-col gap-xs rounded-sm border-l-2 bg-surface-inset p-sm sm:gap-sm sm:p-md ${
            isPassing ? "border-l-attention-amber" : "border-l-mansa-cobalt"
          }`}
        >
          {/* Neutral meta color, not MANSA Cobalt -- hand-computed contrast
              for cobalt-on-surface-inset small text is 3.79:1, short of
              the 4.5:1 AA bar for 12px text (the same class of failure
              M7.2 found for CommandHeader's "Sports Intelligence" label
              and fixed the same way). The cobalt identity signal lives on
              the non-text edge accent below instead, which only needs
              the lower 3:1 non-text bar and clears it at ~3.79:1. */}
          <Text variant="label" as="span" className="tracking-wide">
            MANSA Decision
          </Text>

          {isPassing ? (
            <Text variant="display" as="p" className="text-text-primary">
              {passingDecisionLabel(recommendation.recommendationType)}
            </Text>
          ) : (
            recommendation.legs.map((leg) => (
              <BoardCardDecisionLeg key={`${leg.legOrder}-${leg.marketType}-${leg.selection}`} leg={leg} />
            ))
          )}

          {recommendation.oneLineSummary && <Text variant="body">{recommendation.oneLineSummary}</Text>}
        </div>

        {recommendation.status === "withdrawn" && recommendation.withdrawalReason && (
          <Text variant="label">Withdrawn: {recommendation.withdrawalReason}</Text>
        )}

        <div className="flex items-center justify-between gap-md">
          <div className="flex flex-wrap items-center gap-xs">
            {recommendation.status === "withdrawn" && <StateBadge tone="neutral" label="Withdrawn" />}
            <GradeBadge grade={recommendation.grade} />
            {isUngradedActiveDecision && <StateBadge tone="neutral" label="Active" />}
          </div>
          <FreshnessLabel decidedAt={recommendation.decidedAt} />
        </div>
      </Surface>
    </Link>
  );
}
