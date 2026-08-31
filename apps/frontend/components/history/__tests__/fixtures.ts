import type {
  ReconstructionActivationSnapshot,
  ReconstructionGradeEvent,
  ReconstructionLegRow,
  ReconstructionLifecycleEvent,
  ReconstructionPostgameReview,
  ReconstructionProductExplanation,
  ReconstructionProductRow,
  RecommendationReconstruction,
} from "@/app/lib/api-types";
import { makeDetail } from "@/components/recommendations/__tests__/fixtures";

export function makeReconstructionProduct(overrides: Partial<ReconstructionProductRow> = {}): ReconstructionProductRow {
  return {
    id: "prod-1",
    display_id: "2026-00100",
    recommendation_type: "single",
    scope: "game",
    game_id: "game-1",
    recommendation_id: "rec-1",
    master_refresh_run_id: null,
    min_required_tier: "free",
    status: "active",
    withdrawn_at: null,
    withdrawal_reason: null,
    deleted_at: null,
    created_at: "2026-08-28T06:00:00Z",
    ...overrides,
  };
}

export function makeActivationSnapshot(
  overrides: Partial<ReconstructionActivationSnapshot> = {},
): ReconstructionActivationSnapshot {
  return {
    id: "snap-1",
    recommendation_product_id: "prod-1",
    activated_at: "2026-08-28T06:00:30Z",
    strategy_version: "v1",
    recommendation_product_explanation_id: "expl-1",
    created_at: "2026-08-28T06:00:30Z",
    ...overrides,
  };
}

export function makeReconstructionExplanation(
  overrides: Partial<ReconstructionProductExplanation> = {},
): ReconstructionProductExplanation {
  return {
    id: "expl-1",
    recommendation_product_id: "prod-1",
    why_this_shape: "highest-ranked qualifying candidate",
    why_not_other_shapes: "no other candidate cleared the confidence floor",
    rejected_alternatives: [],
    data_limitations: "Sharp money and public betting data are not yet available.",
    created_at: "2026-08-28T06:00:00Z",
    ...overrides,
  };
}

export function makeReconstructionLegRow(overrides: Partial<ReconstructionLegRow> = {}): ReconstructionLegRow {
  return {
    id: "leg-1",
    candidate_key: "KC-ML",
    market_type: "moneyline",
    selection: "Chiefs",
    sportsbook: "book",
    american_odds: -135,
    point: null,
    decimal_odds: 1.74,
    ev_per_dollar: 0.063,
    final_aggregate_confidence: 0.89,
    leg_order: 1,
    consensus_snapshot_id: "consensus-1",
    game_id: "game-1",
    recommendation_id: "rec-1",
    ...overrides,
  };
}

export function makeGradeEvent(overrides: Partial<ReconstructionGradeEvent> = {}): ReconstructionGradeEvent {
  return {
    id: "grade-1",
    grading_version: "v1",
    outcome: "WIN",
    computed_at: "2026-08-29T02:00:00Z",
    is_correction: false,
    corrects_grade_event_id: null,
    correction_source: null,
    correction_reason: null,
    created_at: "2026-08-29T02:00:00Z",
    ...overrides,
  };
}

export function makeLifecycleEvent(overrides: Partial<ReconstructionLifecycleEvent> = {}): ReconstructionLifecycleEvent {
  return {
    event_type: "ACTIVATED",
    event_timestamp: "2026-08-28T06:00:30Z",
    reason: null,
    created_at: "2026-08-28T06:00:30Z",
    ...overrides,
  };
}

export function makePostgameReview(overrides: Partial<ReconstructionPostgameReview> = {}): ReconstructionPostgameReview {
  return {
    id: "review-1",
    product_grade_event_id: "grade-1",
    grading_version: "v1",
    postgame_review_version: "v1",
    outcome_summary: "Chiefs covered comfortably.",
    why_it_won_or_lost: "Home favorite closed the game out in the fourth quarter.",
    factual_deltas: null,
    correct_agents: ["injury_intelligence_agent"],
    underperforming_agents: null,
    learning_notes: "Weather had no material effect this week.",
    generated_at: "2026-08-30T04:00:00Z",
    created_at: "2026-08-30T04:00:00Z",
    ...overrides,
  };
}

export function makeReconstruction(overrides: Partial<RecommendationReconstruction> = {}): RecommendationReconstruction {
  return {
    product: makeReconstructionProduct(),
    activation_snapshot: makeActivationSnapshot(),
    strategy_version: "v1",
    product_explanation: makeReconstructionExplanation(),
    legs: [
      {
        leg_order: 1,
        leg: makeReconstructionLegRow(),
        explanation: null,
        grade_history: [],
        current_grade: null,
        weighting_evidence: [],
      },
    ],
    source_products: [],
    user_selection: null,
    lifecycle_events: [makeLifecycleEvent()],
    product_grade_history: [],
    current_product_grade: null,
    postgame_reviews: [],
    ...overrides,
  };
}

export { makeDetail };
