import { Text } from "@/components/ds";
import { EmptyState } from "@/components/recommendations";
import { BoardCard } from "./BoardCard";
import type { ApiResult, RecommendationCardData } from "@/app/lib/api-types";

export interface TodaysBoardProps {
  today: ApiResult<RecommendationCardData[]>;
}

/**
 * The Command Center's dominant zone (Milestone 7.1). One `BoardCard`
 * per recommendation product `/v1/recommendations/today` returns --
 * every product preserved, none merged/ranked/hidden, even when two
 * share the same game (HQ's explicit M7.1 correction: the persisted
 * unit is the product, not the game). Cards render in whatever order
 * the API already returned them (neutral chronological, unchanged from
 * every other Phase 6 list).
 *
 * Honest empty state reuses the exact copy `/today` already shipped --
 * "Today's recommendations aren't available yet." -- never implying
 * analysis is in progress or a game/recommendation exists that doesn't.
 */
export function TodaysBoard({ today }: TodaysBoardProps) {
  return (
    <section className="flex flex-col gap-md" aria-labelledby="todays-board-heading">
      <Text variant="heading" as="h2" id="todays-board-heading">
        Today&apos;s Board
      </Text>

      {today.kind === "unauthenticated" && <EmptyState headline="Sign in to see today's board." />}
      {today.kind === "not_found" && <EmptyState headline="Today's recommendations aren't available yet." />}
      {today.kind === "error" && (
        <EmptyState
          headline="Today's board isn't available right now."
          body="Something went wrong reaching the recommendation service. Try again shortly."
        />
      )}
      {today.kind === "ok" && today.data.length === 0 && (
        <EmptyState headline="Today's recommendations aren't available yet." />
      )}
      {today.kind === "ok" && today.data.length > 0 && (
        <div className="grid grid-cols-1 gap-md lg:grid-cols-2">
          {today.data.map((recommendation) => (
            <BoardCard key={recommendation.displayId} recommendation={recommendation} />
          ))}
        </div>
      )}
    </section>
  );
}
