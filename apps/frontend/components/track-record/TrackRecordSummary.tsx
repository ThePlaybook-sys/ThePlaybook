import { Surface, Text } from "@/components/ds";
import type { TrackRecordCounts, TrackRecordData } from "@/app/lib/api-types";

/** Ordered display list -- the count triad HQ approved, in the order a
 * reader should scan them. No win-rate, no derived percentage anywhere
 * in this component (HQ's explicit M5 STOP condition: the API returns
 * no rate, so none is computed here). */
const COUNT_ROWS: Array<{ key: keyof TrackRecordCounts; label: string }> = [
  { key: "win", label: "Win" },
  { key: "loss", label: "Loss" },
  { key: "push", label: "Push" },
  { key: "voidNoAction", label: "Void / No Action" },
  { key: "mixedSettled", label: "Mixed Settled" },
];

/** Known recommendation-type keys with a stable display label. Any type
 * not in this map (future product shapes) falls back to a title-cased
 * rendering of the raw key rather than being silently dropped -- the
 * breakdown must present only categories the response actually
 * supports, but it must not hide a real one just because this map
 * hasn't been updated yet. */
const TYPE_LABEL: Record<string, string> = {
  single: "Single",
  player_prop: "Player Prop",
  multiple_singles: "Multiple Singles",
  no_bet: "No Bet",
  bankroll_preservation: "Bankroll Preservation",
  same_game_parlay: "Same-Game Parlay",
  multi_game_parlay: "Multi-Game Parlay",
};

function typeLabel(rtype: string): string {
  return TYPE_LABEL[rtype] ?? rtype.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function CountRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline justify-between border-b border-border py-xs last:border-b-0">
      <Text variant="body" as="span">
        {label}
      </Text>
      <Text variant="data">{value}</Text>
    </div>
  );
}

function RecordTable({ record }: { record: TrackRecordCounts }) {
  return (
    <div className="flex flex-col">
      {COUNT_ROWS.map(({ key, label }) => (
        <CountRow key={key} label={label} value={record[key]} />
      ))}
    </div>
  );
}

export interface TrackRecordSummaryProps {
  data: TrackRecordData;
}

/**
 * The one honest presentation of `/v1/track-record` (Volume 5 v5.0 §5/§6
 * Track Record Summary, HQ's M5 authorization). Product-level counts
 * only -- no units, ROI, CLV, EV realization, calibration, or any
 * hypothetical-bankroll framing (all explicitly excluded by HQ). Sample
 * size and sample status are always visible, ahead of the record itself,
 * so a small sample can never read as established long-term performance.
 */
export function TrackRecordSummary({ data }: TrackRecordSummaryProps) {
  const typeBreakdown = Object.entries(data.byRecommendationType).filter(
    ([, breakdown]) => breakdown.sampleSize > 0,
  );

  if (data.sampleStatus === "zero") {
    return (
      <Surface level="card" className="flex flex-col gap-sm p-lg">
        <Text variant="heading" as="h2">
          No graded recommendations yet
        </Text>
        <Text variant="body">
          MANSA hasn&apos;t graded any recommendation products yet. A track record will appear here
          once results are in.
        </Text>
      </Surface>
    );
  }

  return (
    <div className="flex flex-col gap-lg">
      <Surface level="card" className="flex flex-col gap-md p-lg">
        <div className="flex flex-col gap-xs">
          <Text variant="label" as="span">
            Sample Size
          </Text>
          <Text variant="display" as="p">
            {data.sampleSize}
          </Text>
        </div>

        {data.sampleStatus === "low" && (
          <Surface level="elevated" className="p-md">
            <Text variant="body">
              Early sample. {data.sampleSize} graded recommendation{data.sampleSize === 1 ? "" : "s"} is not
              enough history to draw conclusions from -- treat this as a running count, not an established
              track record.
            </Text>
          </Surface>
        )}

        <RecordTable record={data.record} />
      </Surface>

      {typeBreakdown.length > 0 && (
        <Surface level="card" className="flex flex-col gap-md p-lg">
          <Text variant="heading" as="h2">
            By Recommendation Type
          </Text>
          <div className="flex flex-col gap-lg">
            {typeBreakdown.map(([rtype, breakdown]) => (
              <div key={rtype} className="flex flex-col gap-xs">
                <div className="flex items-baseline justify-between">
                  <Text variant="body" as="span" className="text-text-primary">
                    {typeLabel(rtype)}
                  </Text>
                  <Text variant="label" as="span">
                    n={breakdown.sampleSize}
                  </Text>
                </div>
                <RecordTable record={breakdown} />
              </div>
            ))}
          </div>
        </Surface>
      )}
    </div>
  );
}
