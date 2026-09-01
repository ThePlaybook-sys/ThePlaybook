import { GRADE_LABEL, GRADE_TONE } from "@/components/recommendations";
import type { RecommendationCardData } from "@/app/lib/api-types";

export interface DecisionState {
  tone: "positive" | "negative" | "neutral";
  label: string;
}

/**
 * Milestone 7.1 -- selects which of the nine authoritative states
 * (ACTIVE, NO BET, BANKROLL PRESERVATION, WIN, LOSS, PUSH, VOID/NO
 * ACTION, MIXED SETTLED, WITHDRAWN -- HQ's exact list) describes one
 * row in Recent Decisions. Every branch reads a field the API already
 * returns verbatim (`status`, `recommendationType`, `grade.outcome`) --
 * this picks which already-true label applies, it never derives or
 * calculates an outcome itself (HQ's explicit "do not calculate
 * outcomes in the frontend" instruction). Reuses `GradeBadge`'s own
 * `GRADE_TONE`/`GRADE_LABEL` vocabulary for the graded branch rather
 * than redefining it.
 */
export function recentDecisionState(recommendation: RecommendationCardData): DecisionState {
  if (recommendation.status === "withdrawn") {
    return { tone: "neutral", label: "Withdrawn" };
  }
  if (recommendation.grade !== null && recommendation.grade.outcome !== "NOT_APPLICABLE") {
    const outcome = recommendation.grade.outcome;
    return { tone: GRADE_TONE[outcome], label: GRADE_LABEL[outcome] };
  }
  if (recommendation.recommendationType === "no_bet") {
    return { tone: "neutral", label: "No Bet" };
  }
  if (recommendation.recommendationType === "bankroll_preservation") {
    return { tone: "neutral", label: "Bankroll Preservation" };
  }
  return { tone: "neutral", label: "Active" };
}
