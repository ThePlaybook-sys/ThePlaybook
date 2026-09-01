import type { TrackRecordCounts, TrackRecordData, TrackRecordTypeBreakdown } from "@/app/lib/api-types";

export function makeCounts(overrides: Partial<TrackRecordCounts> = {}): TrackRecordCounts {
  return {
    win: 0,
    loss: 0,
    push: 0,
    voidNoAction: 0,
    mixedSettled: 0,
    ...overrides,
  };
}

export function makeTypeBreakdown(
  overrides: Partial<TrackRecordTypeBreakdown> = {},
): TrackRecordTypeBreakdown {
  const counts = makeCounts(overrides);
  return {
    ...counts,
    sampleSize: overrides.sampleSize ?? Object.values(counts).reduce((a, b) => a + b, 0),
  };
}

export function makeTrackRecord(overrides: Partial<TrackRecordData> = {}): TrackRecordData {
  return {
    sampleSize: 0,
    sampleStatus: "zero",
    record: makeCounts(),
    byRecommendationType: {},
    ...overrides,
  };
}
