import Link from "next/link";
import { Text } from "@/components/ds";
import type { ApiResult, TrackRecordData } from "@/app/lib/api-types";

export interface TrackRecordSnapshotProps {
  trackRecord: ApiResult<TrackRecordData>;
}

/**
 * Track Record Snapshot -- a compact preview of the existing M2/M5
 * `/v1/track-record` read model, reused verbatim (same route, same
 * fields, no derived win rate/ROI/units/CLV/calibration -- HQ's
 * explicit M7.1 boundary, unchanged from M5's, and reaffirmed in M7.2's
 * §18). The zero-sample copy is byte-for-byte the same as
 * `TrackRecordSummary`'s own, per HQ's "existing zero-sample semantics"
 * instruction -- not a second, drifting copy of the same message.
 *
 * M7.2 renders this as an instrument/result display directly on the
 * dashboard plane (HQ's "not everything is a card" rule): a section
 * label, a hairline top divider for separation, and sample size as the
 * strongest numeric reading with W/L/Push/Void/Mixed as secondary
 * readings -- minimal containment, no boxed card.
 */
export function TrackRecordSnapshot({ trackRecord }: TrackRecordSnapshotProps) {
  return (
    <div
      className="flex flex-col gap-md border-t border-border pt-lg"
      aria-labelledby="track-record-snapshot-heading"
    >
      <Text variant="heading" as="h2" id="track-record-snapshot-heading">
        Track Record
      </Text>

      {trackRecord.kind === "unauthenticated" && <Text variant="body">Sign in to see the track record.</Text>}
      {trackRecord.kind === "not_found" && <Text variant="body">No track record found.</Text>}
      {trackRecord.kind === "error" && <Text variant="body">Track record isn&apos;t available right now.</Text>}
      {trackRecord.kind === "ok" && trackRecord.data.sampleStatus === "zero" && (
        <Text variant="body">
          MANSA hasn&apos;t graded any recommendation products yet. A track record will appear here once
          results are in.
        </Text>
      )}
      {trackRecord.kind === "ok" && trackRecord.data.sampleStatus !== "zero" && (
        <div className="flex flex-col gap-sm">
          <div className="flex flex-col gap-xs">
            <Text variant="data" as="span">
              {trackRecord.data.sampleSize}
            </Text>
            <Text variant="label" as="span">
              Sample Size
            </Text>
          </div>
          {trackRecord.data.sampleStatus === "low" && (
            <Text variant="label">Early sample -- treat as a running count, not an established record.</Text>
          )}
          <div className="flex flex-wrap gap-md">
            <Text variant="body" as="span">
              W {trackRecord.data.record.win}
            </Text>
            <Text variant="body" as="span">
              L {trackRecord.data.record.loss}
            </Text>
            <Text variant="body" as="span">
              P {trackRecord.data.record.push}
            </Text>
            <Text variant="body" as="span">
              Void {trackRecord.data.record.voidNoAction}
            </Text>
            <Text variant="body" as="span">
              Mixed {trackRecord.data.record.mixedSettled}
            </Text>
          </div>
        </div>
      )}

      <Link href="/track-record" className="text-body text-accent underline">
        See full record
      </Link>
    </div>
  );
}
