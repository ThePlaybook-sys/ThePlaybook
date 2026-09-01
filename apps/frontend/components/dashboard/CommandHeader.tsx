import { Text } from "@/components/ds";
import { SourceFreshnessLabel } from "./SourceFreshnessLabel";
import type { ApiResult, SourceFreshness } from "@/app/lib/api-types";

export interface CommandHeaderProps {
  freshness: ApiResult<SourceFreshness>;
}

/**
 * The Command Center's entry band (Milestone 7.1) -- MANSA / "Sports
 * Intelligence" plus the source-freshness line, structurally distinct
 * from `/sign-in`'s brand moment (no mantra here; HQ's explicit
 * "do not plaster it" instruction reserves that for sign-in only).
 * Renders once per page, above `TodaysBoard`.
 */
export function CommandHeader({ freshness }: CommandHeaderProps) {
  return (
    <div className="mansa-illuminated-edge-bottom flex flex-col gap-xs border-b border-transparent pb-md">
      <div className="flex flex-wrap items-baseline justify-between gap-sm">
        <div className="flex items-baseline gap-sm">
          <Text variant="display" as="h1">
            MANSA
          </Text>
          <Text variant="label" as="span">
            Sports Intelligence
          </Text>
        </div>
        <SourceFreshnessLabel freshness={freshness} />
      </div>
    </div>
  );
}
