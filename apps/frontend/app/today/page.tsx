import { Container, Text } from "@/components/ds";
import { RecommendationCard, EmptyState } from "@/components/recommendations";
import { AppNav } from "@/components/nav/AppNav";
import { getToday } from "@/app/lib/api";

export const metadata = { title: "Today — The Playbook" };

/**
 * Today's recommendation feed (Volume 5 v5.0 §2/§6). Server Component --
 * fetches directly from api-gateway using the session cookie, never a
 * client-side proxy (M3's pages are read-only, unlike /demo's
 * interactive tool). Every ApiResult kind gets its own honest render;
 * an empty feed is never confused with "still analyzing" or an error.
 */
export default async function TodayPage() {
  const result = await getToday();

  return (
    <>
      <AppNav />
      <Container className="flex flex-col gap-lg py-xl">
        <Text variant="display" as="h1">
          Today
        </Text>

        {result.kind === "unauthenticated" && <EmptyState headline="Sign in to see today's recommendations." />}
        {result.kind === "not_found" && <EmptyState headline="Today's recommendations aren't available yet." />}
        {result.kind === "error" && (
          <EmptyState
            headline="Today's recommendations aren't available right now."
            body="Something went wrong reaching the recommendation service. Try again shortly."
          />
        )}
        {result.kind === "ok" && result.data.length === 0 && (
          <EmptyState headline="Today's recommendations aren't available yet." />
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
