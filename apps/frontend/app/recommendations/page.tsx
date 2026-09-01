import { Container, Text } from "@/components/ds";
import { RecommendationCard, EmptyState } from "@/components/recommendations";
import { AppNav } from "@/components/nav/AppNav";
import { getRecommendations } from "@/app/lib/api";

export const metadata = { title: "Recommendations — The Playbook" };

/** Broader recommendation feed (trailing 30 days by default, Volume 5
 * v5.0 §2). Same neutral ordering and honest-state handling as /today. */
export default async function RecommendationsPage() {
  const result = await getRecommendations();

  return (
    <>
      <AppNav />
      <Container className="flex flex-col gap-lg py-xl">
        <Text variant="display" as="h1">
          Recommendations
        </Text>

        {result.kind === "unauthenticated" && <EmptyState headline="Sign in to see your recommendations." />}
        {result.kind === "not_found" && <EmptyState headline="No recommendations found." />}
        {result.kind === "error" && (
          <EmptyState
            headline="Recommendations aren't available right now."
            body="Something went wrong reaching the recommendation service. Try again shortly."
          />
        )}
        {result.kind === "ok" && result.data.length === 0 && (
          <EmptyState headline="No recommendations in this range yet." />
        )}
        {result.kind === "ok" && result.data.length > 0 && (
          <div className="flex flex-col gap-md">
            {result.data.map((recommendation) => (
              <RecommendationCard key={recommendation.displayId} recommendation={recommendation} />
            ))}
          </div>
        )}
      </Container>
    </>
  );
}
