import Link from "next/link";
import { Surface, Text, StateBadge } from "@/components/ds";
import type { RecommendationCardData, RecommendationLeg } from "@/app/lib/api-types";
import { GradeBadge } from "./GradeBadge";
import { FreshnessLabel } from "./FreshnessLabel";

function formatOdds(americanOdds: number): string {
  return americanOdds > 0 ? `+${americanOdds}` : `${americanOdds}`;
}

function formatPoint(point: number | null): string {
  if (point == null) {
    return "";
  }
  return ` ${point > 0 ? "+" : ""}${point}`;
}

export function LegLine({ leg }: { leg: RecommendationLeg }) {
  return (
    <div className="flex items-baseline justify-between gap-md">
      <Text variant="body" as="span">
        {leg.selection}
        {formatPoint(leg.point)}
      </Text>
      <div className="flex items-baseline gap-sm">
        <Text variant="label" as="span">
          {Math.round(leg.finalAggregateConfidence * 100)}%
        </Text>
        <Text variant="data" as="span">
          {formatOdds(leg.americanOdds)}
        </Text>
      </div>
    </div>
  );
}

export function headlineFor(recommendation: RecommendationCardData): string {
  if (recommendation.recommendationType === "no_bet") {
    return "The Playbook Is Passing On This Game";
  }
  if (recommendation.recommendationType === "bankroll_preservation") {
    return "The Playbook Is Passing Today";
  }
  if (recommendation.game) {
    return `${recommendation.game.awayTeam} @ ${recommendation.game.homeTeam}`;
  }
  return "Recommendation";
}

export interface RecommendationCardProps {
  recommendation: RecommendationCardData;
}

/**
 * Layer 1 (Volume 5 v5.0 §5) -- the fields visible before a user opens
 * a recommendation. `no_bet`/`bankroll_preservation` render at equal
 * visual weight to an active recommendation (§6): same Surface level,
 * same card structure, just no leg list -- never smaller/grayed-out,
 * never "no data available" framing. Cards render in whatever order
 * the API already returned them (neutral chronological, HQ Final
 * Decision 1) -- this component never reorders or ranks them.
 */
export function RecommendationCard({ recommendation }: RecommendationCardProps) {
  const isPassing =
    recommendation.recommendationType === "no_bet" ||
    recommendation.recommendationType === "bankroll_preservation";

  return (
    <Link
      href={`/recommendations/${recommendation.displayId}`}
      className="block rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-primary"
    >
      <Surface
        level="card"
        className="flex flex-col gap-sm p-md transition-colors hover:border-accent-primary"
        data-recommendation-type={recommendation.recommendationType}
        data-recommendation-status={recommendation.status}
      >
        <div className="flex items-start justify-between gap-md">
          <Text variant="heading">{headlineFor(recommendation)}</Text>
          <div className="flex flex-col items-end gap-xs">
            {recommendation.status === "withdrawn" && <StateBadge tone="neutral" label="Withdrawn" />}
            <GradeBadge grade={recommendation.grade} />
          </div>
        </div>

        {recommendation.oneLineSummary && <Text variant="body">{recommendation.oneLineSummary}</Text>}

        {!isPassing && recommendation.legs.length > 0 && (
          <div className="flex flex-col gap-xs border-t border-border-default pt-sm">
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
