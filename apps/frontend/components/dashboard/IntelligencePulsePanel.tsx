import { Surface, Text } from "@/components/ds";
import { computeDashboardCounts } from "./dashboardCounts";
import { SourceFreshnessLabel } from "./SourceFreshnessLabel";
import type { ApiResult, RecommendationCardData, SourceFreshness } from "@/app/lib/api-types";

export interface IntelligencePulsePanelProps {
  today: ApiResult<RecommendationCardData[]>;
  freshness: ApiResult<SourceFreshness>;
}

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline justify-between border-b border-border py-xs last:border-b-0">
      <Text variant="body" as="span">
        {label}
      </Text>
      <Text variant="data" as="span">
        {value}
      </Text>
    </div>
  );
}

/**
 * MANSA Intelligence / Market Pulse (Milestone 7.1). Only supported
 * information, exactly as HQ's authorization scoped it: recommendation-
 * product count, No Bet product count, unique games represented, and
 * source freshness state -- nothing else. No "markets analyzed",
 * "markets rejected", "awaiting analysis", weather/injury/market-
 * movement alerts, or live-AI-activity language, since no authoritative
 * Phase 1-5 contract exposes any of those (a real, disclosed gap, not
 * silently invented around).
 *
 * Every count is real, including zero -- a zero-recommendation day
 * shows "0 recommendations", not an empty/error state (HQ's explicit
 * M7.1 empty-state instruction: real zero counts are information, not
 * absence of it).
 */
export function IntelligencePulsePanel({ today, freshness }: IntelligencePulsePanelProps) {
  return (
    <Surface level="card" className="flex flex-col gap-md p-lg" aria-labelledby="intelligence-heading">
      <Text variant="heading" as="h2" id="intelligence-heading">
        MANSA Intelligence
      </Text>

      {today.kind === "unauthenticated" && <Text variant="body">Sign in to see today&apos;s intelligence summary.</Text>}
      {today.kind === "not_found" && <StatRow label="Recommendations" value={0} />}
      {today.kind === "error" && <Text variant="body">Intelligence summary isn&apos;t available right now.</Text>}
      {today.kind === "ok" &&
        (() => {
          const counts = computeDashboardCounts(today.data);
          return (
            <div className="flex flex-col">
              <StatRow label="Recommendations" value={counts.recommendationCount} />
              <StatRow label="No Bet decisions" value={counts.noBetCount} />
              <StatRow label="Games represented" value={counts.gamesRepresentedCount} />
            </div>
          );
        })()}

      <SourceFreshnessLabel freshness={freshness} />
    </Surface>
  );
}
