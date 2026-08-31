import { StateBadge } from "@/components/ds";
import { formatDateTime } from "@/app/lib/format";
import type { GradeOutcome, RecommendationGrade } from "@/app/lib/api-types";

/** Exported so Milestone 4 (Time Machine) can render the same tone/label
 * vocabulary for historical grade events without redefining it. */
export const GRADE_TONE: Record<GradeOutcome, "positive" | "negative" | "neutral"> = {
  WIN: "positive",
  LOSS: "negative",
  PUSH: "neutral",
  VOID_NO_ACTION: "neutral",
  NOT_APPLICABLE: "neutral",
  MIXED_SETTLED: "neutral",
};

export const GRADE_LABEL: Record<GradeOutcome, string> = {
  WIN: "Win",
  LOSS: "Loss",
  PUSH: "Push",
  VOID_NO_ACTION: "Void",
  NOT_APPLICABLE: "Not Applicable",
  MIXED_SETTLED: "Mixed Settled",
};

const TONE = GRADE_TONE;
const LABEL = GRADE_LABEL;

export interface GradeBadgeProps {
  grade: RecommendationGrade | null;
}

/**
 * NOT_APPLICABLE (no_bet/bankroll_preservation) is never rendered as a
 * badge -- it isn't a settled-bet outcome (mirrors app.track_record's
 * own exclusion of it from anything outcome-shaped), and the card's own
 * passing headline already communicates that verdict. An ungraded
 * product (grade: null) renders nothing here -- never a placeholder
 * "pending" badge implying computation is in progress (HQ's explicit
 * "never equate empty with still analyzing" rule).
 */
export function GradeBadge({ grade }: GradeBadgeProps) {
  if (grade === null || grade.outcome === "NOT_APPLICABLE") {
    return null;
  }

  return (
    <div className="flex flex-col items-end gap-xs">
      <StateBadge tone={TONE[grade.outcome]} label={LABEL[grade.outcome]} />
      {grade.isCorrection && (
        <span className="text-label text-text-meta">
          Result corrected {formatDateTime(grade.correctedAt)}
        </span>
      )}
    </div>
  );
}
