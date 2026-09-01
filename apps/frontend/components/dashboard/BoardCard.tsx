import Link from "next/link";
import { Surface, Text, StateBadge } from "@/components/ds";
import { headlineFor, LegLine, GradeBadge, FreshnessLabel } from "@/components/recommendations";
import { formatDateTime } from "@/app/lib/format";
import type { RecommendationCardData } from "@/app/lib/api-types";

export interface BoardCardProps {
  recommendation: RecommendationCardData;
}

/**
 * Today's Board's own card presentation (Milestone 7.1) -- a genuinely
 * different composition from `RecommendationCard`'s list-view layout,
 * not the same card dropped into a CSS grid (HQ's explicit
 * instruction). Leads with MATCHUP / GAME CONTEXT (a context strip:
 * scheduled time + live game status, when a game exists), then the
 * MANSA DECISION (the same headline/grade vocabulary
 * `RecommendationCard` already established, reused rather than
 * reinvented), then supported metrics (selection, line/price,
 * confidence, EV via the existing `LegLine`).
 *
 * `RecommendationCard` itself is intentionally untouched by this
 * component -- `/recommendations` and `/history` keep their own tested
 * list-view rendering; this is a new sibling, not a modification.
 *
 * One card per recommendation PRODUCT, never merged (HQ's explicit
 * M7.1 correction): if two products share a game, each renders its own
 * full BoardCard here, at equal visual weight, in whatever order the
 * API already returned them -- this component never groups, ranks, or
 * hides one in favor of another.
 *
 * No_bet/bankroll_preservation render as a real, equal-weight MANSA
 * decision (§8 of the authorization) -- same Surface level and card
 * structure as an active recommendation, never smaller or "empty"
 * framed.
 */
export function BoardCard({ recommendation }: BoardCardProps) {
  const isPassing =
    recommendation.recommendationType === "no_bet" ||
    recommendation.recommendationType === "bankroll_preservation";
  const game = recommendation.game;
  const gameStatusIsNotable = game !== null && game.status !== "scheduled";

  return (
    <Link
      href={`/recommendations/${recommendation.displayId}`}
      className="block rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
    >
      <Surface
        level="card"
        className="flex flex-col gap-sm p-lg transition-colors hover:border-accent"
        data-recommendation-type={recommendation.recommendationType}
        data-recommendation-status={recommendation.status}
      >
        <div className="flex items-baseline justify-between gap-md">
          <Text variant="label" as="span">
            {game ? formatDateTime(game.scheduledStart) : "Today's Slate"}
          </Text>
          {gameStatusIsNotable && (
            <Text variant="label" as="span">
              {game.status}
            </Text>
          )}
        </div>

        <div className="flex items-start justify-between gap-md">
          <Text variant="heading" as="h2" className="min-w-0">
            {headlineFor(recommendation)}
          </Text>
          <div className="flex shrink-0 flex-col items-end gap-xs">
            {recommendation.status === "withdrawn" && <StateBadge tone="neutral" label="Withdrawn" />}
            <GradeBadge grade={recommendation.grade} />
          </div>
        </div>

        {recommendation.oneLineSummary && <Text variant="body">{recommendation.oneLineSummary}</Text>}

        {!isPassing && recommendation.legs.length > 0 && (
          <div className="flex flex-col gap-xs border-t border-border pt-sm">
            {recommendation.legs.map((leg) => (
              <LegLine key={`${leg.legOrder}-${leg.marketType}-${leg.selection}`} leg={leg} />
            ))}
          </div>
        )}

        {recommendation.status === "withdrawn" && recommendation.withdrawalReason && (
          <Text variant="label">Withdrawn: {recommendation.withdrawalReason}</Text>
        )}

        <FreshnessLabel decidedAt={recommendation.decidedAt} />
      </Surface>
    </Link>
  );
}
