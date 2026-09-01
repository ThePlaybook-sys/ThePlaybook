import { Container } from "@/components/ds";
import { RecommendationDetail, EmptyState } from "@/components/recommendations";
import { AppNav } from "@/components/nav/AppNav";
import { getRecommendationDetail } from "@/app/lib/api";

/** Recommendation detail -- Layers 1-4 progressive disclosure (Volume 5
 * v5.0 §5). A tier-gated or nonexistent display_id both resolve to the
 * same "not found" render (the API itself already returns 404, never
 * 403, for both cases -- HQ Final Decision 9, no locked-content UI). */
export default async function RecommendationDetailPage({
  params,
}: {
  params: { displayId: string };
}) {
  const result = await getRecommendationDetail(params.displayId);

  return (
    <>
      <AppNav />
      <Container className="flex flex-col gap-lg py-xl">
        {result.kind === "unauthenticated" && <EmptyState headline="Sign in to see this recommendation." />}
        {result.kind === "not_found" && <EmptyState headline="Recommendation not found." />}
        {result.kind === "error" && (
          <EmptyState
            headline="This recommendation isn't available right now."
            body="Something went wrong reaching the recommendation service. Try again shortly."
          />
        )}
        {result.kind === "ok" && <RecommendationDetail recommendation={result.data} />}
      </Container>
    </>
  );
}
