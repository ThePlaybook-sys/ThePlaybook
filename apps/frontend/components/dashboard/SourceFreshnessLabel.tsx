import { Text } from "@/components/ds";
import { formatRelativeTime } from "@/app/lib/format";
import type { ApiResult, SourceFreshness } from "@/app/lib/api-types";

export interface SourceFreshnessLabelProps {
  freshness: ApiResult<SourceFreshness>;
}

/**
 * SOURCE data freshness only (Milestone 7.1, HQ's explicit instruction)
 * -- how recently MANSA's underlying game/odds/intelligence data was
 * refreshed, never a recommendation's own decision timestamp
 * (`FreshnessLabel`, a distinct component, owns that concept). The two
 * are never collapsed into one generic "Updated" label anywhere in
 * this codebase.
 *
 * Takes the wrapped `ApiResult`, not unwrapped data (the established
 * M6 `AccountSummary` pattern) -- an unauthenticated/error read of this
 * one small header line degrades quietly (renders nothing) rather than
 * surfacing its own error block, since the rest of the Command Center
 * still renders normally in that case.
 *
 * When the read succeeds, three real states are rendered honestly: no
 * refresh has ever run in this environment (`status: null`); one is
 * currently running (`completedAt` still null); the latest one
 * completed (show its own timestamp, relative). Never a fabricated
 * time, never implied to be live/ticking -- there is no polling or
 * push infrastructure behind this label, it reflects whatever
 * `GET /v1/system/freshness` returned on this page load.
 */
export function SourceFreshnessLabel({ freshness }: SourceFreshnessLabelProps) {
  if (freshness.kind !== "ok") {
    return null;
  }
  const data = freshness.data;
  if (data.status === null) {
    return <Text variant="label">Awaiting first data refresh</Text>;
  }
  if (data.completedAt === null) {
    return <Text variant="label">Data refresh in progress</Text>;
  }
  return <Text variant="label">Data refreshed {formatRelativeTime(data.completedAt)}</Text>;
}
