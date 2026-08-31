/**
 * TypeScript contracts mirroring apps/api-gateway's Phase 6 Milestone 2
 * JSON responses verbatim (Volume 5 v5.0.2 §11) -- field names and
 * shapes must stay byte-for-byte in sync with
 * apps/api-gateway/app/recommendations.py, track_record.py,
 * subscription.py. Never widen a field's meaning here beyond what the
 * backend actually returns.
 */

export type RecommendationType =
  | "single"
  | "player_prop"
  | "multiple_singles"
  | "no_bet"
  | "bankroll_preservation"
  | "same_game_parlay"
  | "multi_game_parlay";

export type RecommendationStatus = "active" | "withdrawn";

export type GradeOutcome =
  | "WIN"
  | "LOSS"
  | "PUSH"
  | "VOID_NO_ACTION"
  | "NOT_APPLICABLE"
  | "MIXED_SETTLED";

/** Milestone 2.1 -- additive, independent of RecommendationStatus.
 * recommendation_products.status never carries a 'graded' value; grade
 * state lives here instead, null when the product is ungraded. */
export interface RecommendationGrade {
  outcome: GradeOutcome;
  gradedAt: string;
  isCorrection: boolean;
  correctedAt: string | null;
}

export interface GameSummary {
  homeTeam: string;
  awayTeam: string;
  scheduledStart: string;
  status: string;
}

export interface RecommendationLeg {
  marketType: "moneyline" | "spread" | "total" | "prop";
  selection: string;
  sportsbook: string;
  americanOdds: number;
  point: number | null;
  decimalOdds: number;
  evPerDollar: number;
  finalAggregateConfidence: number;
  legOrder: number;
}

export interface RecommendationCardData {
  displayId: string;
  recommendationType: RecommendationType;
  scope: "game" | "slate";
  status: RecommendationStatus;
  minRequiredTier: string;
  withdrawnAt: string | null;
  withdrawalReason: string | null;
  decidedAt: string | null;
  grade: RecommendationGrade | null;
  game: GameSummary | null;
  oneLineSummary: string | null;
  legs: RecommendationLeg[];
}

export interface AgentContribution {
  agentId: string;
  agentName: string | null;
  agentConfidence: number | null;
  weightApplied: number;
  directionalLean: string | null;
  modelName: string | null;
  provider: string | null;
  usedFallback: boolean | null;
  promptName: string | null;
  promptVersion: number | null;
}

export interface ConsensusDetail {
  aggregateConfidence: number | null;
  agreementVariance: number | null;
  finalAggregateConfidence: number | null;
  belowConfidenceFloor: boolean | null;
}

export interface RecommendationLegDetail extends RecommendationLeg {
  whySelected: string | null;
  strongestEvidence: string | null;
  contributingAgents: Array<{ name: string; weight: number; [key: string]: unknown }>;
  biggestRisks: string | null;
  rejectedAlternatives: unknown[];
  wouldChangeMindIf: string | null;
  agentContributions: AgentContribution[];
  consensus: ConsensusDetail | null;
}

export interface RecommendationDetailData extends Omit<RecommendationCardData, "legs"> {
  legs: RecommendationLegDetail[];
  whyNotOtherShapes: string | null;
  rejectedAlternatives: unknown[];
  dataLimitations: string | null;
}

/** Discriminated result type every server-side fetch helper returns --
 * callers render a distinct honest state per outcome, never treating
 * "empty" and "error"/"unauthenticated" as the same thing (HQ's
 * explicit M3 rule). */
export type ApiResult<T> =
  | { kind: "ok"; data: T }
  | { kind: "unauthenticated" }
  | { kind: "not_found" }
  | { kind: "error"; status: number };
