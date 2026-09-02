import Link from "next/link";
import { Text, StateBadge } from "@/components/ds";
import { headlineFor } from "@/components/recommendations";
import { formatDateTime } from "@/app/lib/format";
import { recentDecisionState } from "./recentDecisionState";
import type { ApiResult, RecommendationCardData } from "@/app/lib/api-types";

export interface RecentDecisionsListProps {
  recent: ApiResult<RecommendationCardData[]>;
}

const MAX_ROWS = 6;

/**
 * Recent Decisions -- a compact preview of the existing M2/M3
 * `/v1/recommendations` feed, reused verbatim (no new backend route, no
 * new state computation beyond `recentDecisionState`'s pure label
 * selection). Links each row into the same detail route
 * `RecommendationCard` already uses, and links out to the full feed.
 *
 * M7.2 renders this as structured rows directly on the dashboard plane
 * (HQ's "not everything is a card" rule) -- a section label, a hairline
 * top divider for separation from the module above it, and subtle
 * per-row separators, rather than a boxed list.
 */
export function RecentDecisionsList({ recent }: RecentDecisionsListProps) {
  return (
    <div className="flex flex-col gap-md border-t border-border pt-lg" aria-labelledby="recent-decisions-heading">
      <Text variant="heading" as="h2" id="recent-decisions-heading">
        Recent Decisions
      </Text>

      {recent.kind === "unauthenticated" && <Text variant="body">Sign in to see recent decisions.</Text>}
      {recent.kind === "not_found" && <Text variant="body">No decisions yet.</Text>}
      {recent.kind === "error" && <Text variant="body">Recent decisions aren&apos;t available right now.</Text>}
      {recent.kind === "ok" && recent.data.length === 0 && <Text variant="body">No decisions yet.</Text>}
      {recent.kind === "ok" && recent.data.length > 0 && (
        <ul className="flex flex-col">
          {recent.data.slice(0, MAX_ROWS).map((recommendation) => {
            const { tone, label } = recentDecisionState(recommendation);
            return (
              <li key={recommendation.displayId} className="border-b border-border py-sm last:border-b-0">
                <Link
                  href={`/recommendations/${recommendation.displayId}`}
                  className="flex items-center justify-between gap-md rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                >
                  <div className="flex min-w-0 flex-col gap-xs">
                    <Text
                      variant="body"
                      as="span"
                      className="truncate text-text-primary"
                      title={headlineFor(recommendation)}
                    >
                      {headlineFor(recommendation)}
                    </Text>
                    <Text variant="label" as="span">
                      {formatDateTime(recommendation.decidedAt)}
                    </Text>
                  </div>
                  <StateBadge tone={tone} label={label} className="shrink-0" />
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      <Link href="/recommendations" className="text-body text-accent underline">
        See all
      </Link>
    </div>
  );
}
