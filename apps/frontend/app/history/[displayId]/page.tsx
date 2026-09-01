import { Container, Text } from "@/components/ds";
import { EmptyState, RecommendationDetail, headlineFor } from "@/components/recommendations";
import { TimeMachine } from "@/components/history";
import { AppNav } from "@/components/nav/AppNav";
import { getRecommendationDetail, getRecommendationReconstruction } from "@/app/lib/api";

/**
 * Time Machine (Milestone 4). Composes two independent, already-
 * authoritative reads in parallel -- `getRecommendationDetail` (M2/M3)
 * and `getRecommendationReconstruction` (M2 proxy to the Milestone 5.3
 * reconstruction function). Never a second reconstruction engine: every
 * historical fact here is read verbatim from one of these two results.
 */
export default async function HistoryDetailPage({
  params,
}: {
  params: { displayId: string };
}) {
  const [detailResult, reconstructionResult] = await Promise.all([
    getRecommendationDetail(params.displayId),
    getRecommendationReconstruction(params.displayId),
  ]);

  if (detailResult.kind === "unauthenticated") {
    return (
      <>
        <AppNav />
        <Container as="main" className="flex flex-col gap-lg py-xl">
          <EmptyState headline="Sign in to see this recommendation's history." />
        </Container>
      </>
    );
  }
  if (detailResult.kind === "not_found") {
    return (
      <>
        <AppNav />
        <Container as="main" className="flex flex-col gap-lg py-xl">
          <EmptyState headline="Recommendation not found." />
        </Container>
      </>
    );
  }
  if (detailResult.kind === "error") {
    return (
      <>
        <AppNav />
        <Container as="main" className="flex flex-col gap-lg py-xl">
          <EmptyState
            headline="This recommendation's history isn't available right now."
            body="Something went wrong reaching the recommendation service. Try again shortly."
          />
        </Container>
      </>
    );
  }

  // detailResult.kind === "ok" from here -- the product itself is real
  // and visible to this user. Whether its deeper reconstruction is
  // available is a separate question, handled honestly below rather
  // than assumed to track the detail result.
  if (reconstructionResult.kind === "ok") {
    return (
      <>
        <AppNav />
        <Container as="main" className="flex flex-col gap-lg py-xl">
          <Text variant="display" as="h1">
            {headlineFor(detailResult.data)}
          </Text>
          <TimeMachine detail={detailResult.data} reconstruction={reconstructionResult.data} />
        </Container>
      </>
    );
  }

  // Partial reconstruction -- never fabricated. Show what's
  // authoritatively known (the same Layers 1-4 /recommendations already
  // renders) plus an honest note that the six-stage narrative isn't
  // available, rather than a blank page or an invented history.
  return (
    <>
      <AppNav />
      <Container as="main" className="flex flex-col gap-lg py-xl">
        <EmptyState
          headline="Full Time Machine reconstruction is unavailable for this recommendation."
          body="Showing what's available below."
        />
        <RecommendationDetail recommendation={detailResult.data} />
      </Container>
    </>
  );
}
