import type { HTMLAttributes } from "react";

type StateTone = "positive" | "negative" | "neutral";

const TONE_CLASS: Record<StateTone, string> = {
  positive: "bg-state-positive/15 text-state-positive border-state-positive/30",
  negative: "bg-state-negative/15 text-state-negative border-state-negative/30",
  neutral: "bg-state-neutral/15 text-state-neutral border-state-neutral/30",
};

export type StateBadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone: StateTone;
  label: string;
};

/**
 * The one component allowed to render the state triad (win/loss/push,
 * confidence-floor pass/fail, freshness). Never apply --state-* colors
 * directly elsewhere — this keeps the state vocabulary exhaustive and
 * auditable as real screens (grade badges, freshness indicators) get
 * built in later milestones.
 */
export function StateBadge({ tone, label, className, ...rest }: StateBadgeProps) {
  const classes = [
    "inline-flex items-center rounded-sm border px-sm py-xs text-label",
    TONE_CLASS[tone],
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <span data-state-tone={tone} className={classes} {...rest}>
      {label}
    </span>
  );
}
