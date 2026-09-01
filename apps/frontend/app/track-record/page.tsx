import { Container, Text } from "@/components/ds";
import { EmptyState } from "@/components/recommendations";
import { TrackRecordSummary } from "@/components/track-record";
import { getTrackRecord } from "@/app/lib/api";

export const metadata = { title: "Track Record — The Playbook" };

/** Phase 6 Milestone 5. Authoritative product-level graded record only --
 * no units, ROI, CLV, calibration, or hypothetical-bankroll framing (all
 * explicitly excluded by HQ's M5 authorization). Reuses the existing
 * M2 `/v1/track-record` read model verbatim; no new grading algorithm. */
export default async function TrackRecordPage() {
  const result = await getTrackRecord();

  return (
    <Container className="flex flex-col gap-lg py-xl">
      <Text variant="display" as="h1">
        Track Record
      </Text>

      {result.kind === "unauthenticated" && <EmptyState headline="Sign in to see the track record." />}
      {result.kind === "not_found" && <EmptyState headline="No track record found." />}
      {result.kind === "error" && (
        <EmptyState
          headline="Track record isn't available right now."
          body="Something went wrong reaching the track record service. Try again shortly."
        />
      )}
      {result.kind === "ok" && <TrackRecordSummary data={result.data} />}
    </Container>
  );
}
