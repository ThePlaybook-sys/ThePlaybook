import type { ReactNode } from "react";
import { Text } from "@/components/ds";

export interface TimeMachineStageProps {
  /** 1-6 -- always rendered, even when this stage has nothing but its
   * own honest empty copy (Volume 5's "six stable stages," HQ's M4
   * "all six stages should remain structurally understandable even when
   * some data is unavailable" rule). Never omit a stage from the DOM. */
  index: number;
  title: string;
  children: ReactNode;
}

/**
 * One segment of the six-stage vertical stepper. A plain connected-dot
 * chronology (Quant Broadcast/Desk Open: strong chronology, no Git-
 * commit-history or audit-log appearance, no decorative motion) --
 * reflows to a single column on mobile by construction, since it's
 * already flex-col at every breakpoint.
 */
export function TimeMachineStage({ index, title, children }: TimeMachineStageProps) {
  return (
    <li className="flex gap-md">
      <div className="flex flex-col items-center" aria-hidden="true">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border text-label text-text-secondary">
          {index}
        </span>
        <span className="mt-xs w-px flex-1 bg-border" />
      </div>
      <div className="flex flex-1 flex-col gap-sm pb-xl">
        <Text variant="heading" as="h2">
          {title}
        </Text>
        {children}
      </div>
    </li>
  );
}
