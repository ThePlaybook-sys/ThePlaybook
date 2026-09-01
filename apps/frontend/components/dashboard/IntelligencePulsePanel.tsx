import { Text } from "@/components/ds";
import { computeDashboardCounts } from "./dashboardCounts";
import { SourceFreshnessLabel } from "./SourceFreshnessLabel";
import type { ApiResult, RecommendationCardData, SourceFreshness } from "@/app/lib/api-types";

export interface IntelligencePulsePanelProps {
  today: ApiResult<RecommendationCardData[]>;
  freshness: ApiResult<SourceFreshness>;
}

function CountReading({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-xs">
      <Text variant="data" as="span">
        {value}
      </Text>
      <Text variant="label" as="span">
        {label}
      </Text>
    </div>
  );
}

/**
 * MANSA Intelligence / Market Pulse. M7.2 renders this as a
 * containerless metric strip directly on the dashboard plane (HQ's "not
 * everything is a card" rule) -- a section label plus a row of
 * number-over-label readings, rather than a boxed stat list. Content
 * scope is unchanged from M7.1: only supported information --
 * recommendation-product count, No Bet product count, unique games
 * represented, and source freshness state -- nothing else. No "markets
 * analyzed", "markets rejected", "awaiting analysis", weather/injury/
 * market-movement alerts, or live-AI-activity language, since no
 * authoritative Phase 1-5 contract exposes any of those (a real,
 * disclosed gap, not silently invented around).
 *
 * Every count is real, including zero -- a zero-recommendation day
 * shows "0 recommendations", not an empty/error state (HQ's explicit
 * M7.1 empty-state instruction: real zero counts are information, not
 * absence of it).
 */
export function IntelligencePulsePanel({ today, freshness }: IntelligencePulsePanelProps) {
  return (
    <div className="flex flex-col gap-md border-t border-border pt-lg" aria-labelledby="intelligence-heading">
      <Text variant="heading" as="h2" id="intelligence-heading">
        MANSA Intelligence
      </Text>

      {today.kind === "unauthenticated" && <Text variant="body">Sign in to see today&apos;s intelligence summary.</Text>}
      {today.kind === "not_found" && (
        <div className="flex flex-wrap gap-xl">
          <CountReading label="Recommendations" value={0} />
        </div>
      )}
      {today.kind === "error" && <Text variant="body">Intelligence summary isn&apos;t available right now.</Text>}
      {today.kind === "ok" &&
        (() => {
          const counts = computeDashboardCounts(today.data);
          return (
            <div className="flex flex-wrap gap-xl">
              <CountReading label="Recommendations" value={counts.recommendationCount} />
              <CountReading label="No Bet Decisions" value={counts.noBetCount} />
              <CountReading label="Games Represented" value={counts.gamesRepresentedCount} />
            </div>
          );
        })()}

      <SourceFreshnessLabel freshness={freshness} />
    </div>
  );
}
