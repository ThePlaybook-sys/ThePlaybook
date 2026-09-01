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

/**
 * Milestone 4 -- GET /v1/recommendations/{displayId}/reconstruction.
 * This route is a pure proxy to ai-orchestrator's internal wrapper,
 * which serializes `ReconstructedProduct` via `dataclasses.asdict()` --
 * so, unlike every other route in this file, these fields are the raw
 * snake_case Supabase column names verbatim, not camelCase. HQ's
 * "PUBLIC CONTRACT COUPLING NOTE" (M2 close-out) applies: this exact
 * shape is a declared public contract, never refactored for cleanliness
 * to "fix" the casing mismatch with the rest of this file.
 */

export interface ReconstructionProductRow {
  id: string;
  display_id: string;
  recommendation_type: RecommendationType;
  scope: "game" | "slate";
  game_id: string | null;
  recommendation_id: string | null;
  master_refresh_run_id: string | null;
  min_required_tier: string;
  status: RecommendationStatus;
  withdrawn_at: string | null;
  withdrawal_reason: string | null;
  deleted_at: string | null;
  created_at: string;
}

export interface ReconstructionActivationSnapshot {
  id: string;
  recommendation_product_id: string;
  activated_at: string;
  strategy_version: string;
  recommendation_product_explanation_id: string | null;
  created_at: string;
}

export interface ReconstructionProductExplanation {
  id: string;
  recommendation_product_id: string;
  why_this_shape: string;
  why_not_other_shapes: string | null;
  rejected_alternatives: unknown[];
  data_limitations: string | null;
  created_at: string;
}

export interface ReconstructionLegRow {
  id: string;
  candidate_key: string;
  market_type: "moneyline" | "spread" | "total" | "prop";
  selection: string;
  sportsbook: string;
  american_odds: number;
  point: number | null;
  decimal_odds: number;
  ev_per_dollar: number;
  final_aggregate_confidence: number;
  leg_order: number;
  consensus_snapshot_id: string | null;
  game_id: string | null;
  recommendation_id: string | null;
}

export interface ReconstructionLegExplanation {
  id: string;
  recommendation_leg_id: string;
  why_selected: string;
  strongest_evidence: string;
  contributing_agents: Array<{ name: string; weight: number; [key: string]: unknown }>;
  biggest_risks: string;
  rejected_alternatives: unknown[];
  would_change_mind_if: string | null;
  narrative_summary: string | null;
  created_at: string;
}

/** Covers both leg-scope (`authoritative_result`/`graded_at`) and
 * product-scope (`leg_outcome_counts`/`computed_at`) grade events --
 * the two tables share every other column. `PENDING_MISSING_DATA` can
 * appear in a leg's own history (never in product-level history --
 * `app.orchestration.postgame_grading` never persists a product rollup
 * until every leg is terminal). */
export interface ReconstructionGradeEvent {
  id: string;
  grading_version: string;
  outcome: GradeOutcome | "PENDING_MISSING_DATA";
  authoritative_result?: Record<string, unknown>;
  leg_outcome_counts?: Record<string, number> | null;
  graded_at?: string;
  computed_at?: string;
  is_correction: boolean;
  corrects_grade_event_id: string | null;
  correction_source: string | null;
  correction_reason: string | null;
  created_at: string;
}

export interface ReconstructionLifecycleEvent {
  event_type: "ACTIVATED" | "WITHDRAWN" | "SOFT_DELETED";
  event_timestamp: string;
  reason: string | null;
  created_at: string;
}

export interface ReconstructionPostgameReview {
  id: string;
  product_grade_event_id: string;
  grading_version: string;
  postgame_review_version: string;
  outcome_summary: string | null;
  why_it_won_or_lost: string | null;
  factual_deltas: Record<string, unknown> | null;
  correct_agents: string[] | null;
  underperforming_agents: string[] | null;
  learning_notes: string | null;
  generated_at: string;
  created_at: string;
}

export interface ReconstructionWeightProposalObservation {
  id: string;
  proposal_id: string;
  recommendation_leg_grade_event_id: string;
  classification: string;
  directional_lean: string | null;
  notional_pnl: number | null;
  created_at: string;
}

export interface ReconstructionWeightProposal {
  id: string;
  agent_id: string;
  previous_weight: number;
  raw_proposed_weight: number;
  guardrail_adjusted_proposed_weight: number;
  applied_weight: number | null;
  evaluation_window_start: string;
  evaluation_window_end: string;
  sample_size: number;
  roi: number;
  committee_average_roi: number;
  performance_delta: number;
  learning_rate: number;
  weighting_version: string;
  status: string;
  rejection_reason: string | null;
  is_correction: boolean;
  corrects_proposal_id: string | null;
  created_at: string;
}

export interface ReconstructionWeightingEvidence {
  observation: ReconstructionWeightProposalObservation;
  proposal: ReconstructionWeightProposal | null;
}

export interface ReconstructionLeg {
  leg_order: number;
  leg: ReconstructionLegRow;
  explanation: ReconstructionLegExplanation | null;
  /** Oldest-first; every original + correction row, never collapsed. */
  grade_history: ReconstructionGradeEvent[];
  /** `grade_history[grade_history.length - 1]` -- the current
   * authoritative grade. `null` when never graded. */
  current_grade: ReconstructionGradeEvent | null;
  weighting_evidence: ReconstructionWeightingEvidence[];
}

export interface ReconstructionSourceProduct {
  recommendation_product_id: string;
  explanation: ReconstructionProductExplanation | null;
}

export interface ReconstructionUserSelection {
  id: string;
  risk_tolerance: string | null;
  bankroll_at_computation: number | null;
  excluded_by_session_preferences: boolean | null;
  full_kelly_fraction: number | null;
  quarter_kelly_fraction: number | null;
  risk_tolerance_multiplier: number | null;
  stake: number | null;
  created_at: string;
}

/** `apps/ai-orchestrator/app/orchestration/reconstruction.py`'s
 * `ReconstructedProduct`, serialized verbatim. `no_bet` products never
 * populate `legs`; `bankroll_preservation` never populates `legs` but
 * does populate `source_products`; `single`/`multiple_singles` populate
 * `legs`, never `source_products`. */
export interface RecommendationReconstruction {
  product: ReconstructionProductRow;
  activation_snapshot: ReconstructionActivationSnapshot;
  strategy_version: string;
  product_explanation: ReconstructionProductExplanation | null;
  legs: ReconstructionLeg[];
  source_products: ReconstructionSourceProduct[];
  user_selection: ReconstructionUserSelection | null;
  /** Oldest-first. Never empty for an activated product -- ACTIVATED is
   * always the first row -- but read exactly as persisted. */
  lifecycle_events: ReconstructionLifecycleEvent[];
  product_grade_history: ReconstructionGradeEvent[];
  current_product_grade: ReconstructionGradeEvent | null;
  postgame_reviews: ReconstructionPostgameReview[];
}

/** `apps/api-gateway/app/track_record.py`'s response, camelCase (unlike
 * the reconstruction route, this one is not a pass-through -- it's
 * built by this codebase's own handler, so it already matches every
 * other M2/M3 route's casing convention). */
export interface TrackRecordCounts {
  win: number;
  loss: number;
  push: number;
  voidNoAction: number;
  mixedSettled: number;
}

export type SampleStatus = "zero" | "low" | "mature";

export interface TrackRecordTypeBreakdown extends TrackRecordCounts {
  sampleSize: number;
}

export interface TrackRecordData {
  sampleSize: number;
  sampleStatus: SampleStatus;
  record: TrackRecordCounts;
  /** May contain a zero-sampleSize entry for `no_bet`/`bankroll_preservation`
   * (every product graded `NOT_APPLICABLE` still creates a `by_type`
   * entry server-side, even though it's never tallied into it -- see
   * `track_record.py`'s own docstring). Callers must filter to
   * `sampleSize > 0` before rendering, so those two types are never
   * shown as a 0-0-0-0-0 "record" that could read as a losing streak. */
  byRecommendationType: Record<string, TrackRecordTypeBreakdown>;
}

/** `GET /v1/user/profile` (Phase 2 Milestone 4, unchanged) is a thin
 * `response.json()[0]` passthrough of the raw `user_profiles` row --
 * snake_case verbatim, unlike every M2/M3 route's camelCase, the same
 * "real backend contract, not renormalized here" pattern already
 * documented for the reconstruction route. Only the fields M6 actually
 * reads are typed; the row carries more (persona_classification,
 * betting_experience, etc.) that M6 does not surface. */
export interface UserProfile {
  id: string;
  display_name: string | null;
  jurisdiction_state: string | null;
  onboarding_completed_at: string | null;
}

/** `PATCH /v1/user/profile` body -- `jurisdiction_state` is the only
 * field M6's onboarding form collects (HQ's explicit "keep onboarding
 * short" instruction); every other field on `OnboardingComplete`
 * (Phase 2 Milestone 4) stays optional/unset here. */
export interface OnboardingUpdate {
  jurisdiction_state: string;
}

/** `GET /v1/user/subscription` (Phase 6 Milestone 2, unchanged) --
 * already camelCase, this route's own handler builds the response
 * rather than passing a raw row through. */
export interface SubscriptionData {
  tier: string | null;
  status: string | null;
  billingPeriod: string | null;
  currentPeriodEnd: string | null;
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
