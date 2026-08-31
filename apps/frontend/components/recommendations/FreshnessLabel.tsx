import { Text } from "@/components/ds";
import { formatDateTime } from "@/app/lib/format";

export interface FreshnessLabelProps {
  decidedAt: string | null;
}

/**
 * Recommendation-decision freshness only (recommendation_activation_
 * snapshots.activated_at) -- never labeled "updated"/"refreshed"/"last
 * confirmed", those words are reserved for source/intelligence
 * freshness (master_refresh_runs.completed_at), a separate page-level
 * concept this component never touches (HQ Final Decision 10).
 */
export function FreshnessLabel({ decidedAt }: FreshnessLabelProps) {
  if (!decidedAt) {
    return null;
  }
  return <Text variant="label">Decided {formatDateTime(decidedAt)}</Text>;
}
