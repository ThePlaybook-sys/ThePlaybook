import Link from "next/link";
import { Surface, Text } from "@/components/ds";
import type { ApiResult, TrackRecordData } from "@/app/lib/api-types";

export interface TrackRecordSnapshotProps {
  trackRecord: ApiResult<TrackRecordData>;
}

/**
 * Track Record Snapshot (Milestone 7.1) -- a compact preview of the
 * existing M2/M5 `/v1/track-record` read model, reused verbatim (same
 * route, same fields, no derived win rate/ROI/units/CLV/calibration --
 * HQ's explicit M7.1 boundary, unchanged from M5's). The zero-sample
 * copy is byte-for-byte the same as `TrackRecordSummary`'s own, per
 * HQ's "existing zero-sample semantics" instruction -- not a second,
 * drifting copy of the same message.
 */
export function TrackRecordSnapshot({ trackRecord }: TrackRecordSnapshotProps) {
  return (
    <Surface level="card" className="flex flex-col gap-md p-lg" aria-labelledby="track-record-snapshot-heading">
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
          <div className="flex items-baseline justify-between">
            <Text variant="label" as="span">
              Sample Size
            </Text>
            <Text variant="data" as="span">
              {trackRecord.data.sampleSize}
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
    </Surface>
  );
}
