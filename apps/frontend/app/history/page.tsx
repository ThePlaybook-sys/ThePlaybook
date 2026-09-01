import { Container, Text } from "@/components/ds";
import { RecommendationCard, EmptyState } from "@/components/recommendations";
import { AppNav } from "@/components/nav/AppNav";
import { getRecommendations } from "@/app/lib/api";

export const metadata = { title: "History — The Playbook" };

/**
 * History index (Milestone 4, Volume 5 v5.0 §3). Reuses M2/M2.1's
 * existing `GET /v1/recommendations` feed and M3's `RecommendationCard`
 * verbatim -- no new backend route, no new ranking algorithm. Cards
 * link into `/history/[displayId]` (the Time Machine) instead of
 * `/recommendations/[displayId]` via the card's `linkTo` prop; the
 * card's own content and ordering are otherwise identical to
 * `/recommendations` (neutral chronological, HQ Final Decision 1).
 */
export default async function HistoryPage() {
  const result = await getRecommendations();

  return (
    <>
      <AppNav />
      <Container className="flex flex-col gap-lg py-xl">
        <Text variant="display" as="h1">
          History
        </Text>

        {result.kind === "unauthenticated" && <EmptyState headline="Sign in to see your recommendation history." />}
        {result.kind === "not_found" && <EmptyState headline="No history found." />}
        {result.kind === "error" && (
          <EmptyState
            headline="History isn't available right now."
            body="Something went wrong reaching the recommendation service. Try again shortly."
          />
        )}
        {result.kind === "ok" && result.data.length === 0 && (
          <EmptyState headline="No recommendation history yet." />
        )}
        {result.kind === "ok" && result.data.length > 0 && (
          <div className="flex flex-col gap-md">
            {result.data.map((recommendation) => (
              <RecommendationCard key={recommendation.displayId} recommendation={recommendation} linkTo="/history" />
            ))}
          </div>
        )}
      </Container>
    </>
  );
}
