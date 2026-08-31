import type {
  RecommendationCardData,
  RecommendationDetailData,
  RecommendationGrade,
  RecommendationLeg,
  RecommendationLegDetail,
} from "@/app/lib/api-types";

export function makeLeg(overrides: Partial<RecommendationLeg> = {}): RecommendationLeg {
  return {
    marketType: "moneyline",
    selection: "Chiefs",
    sportsbook: "book",
    americanOdds: -135,
    point: null,
    decimalOdds: 1.74,
    evPerDollar: 0.063,
    finalAggregateConfidence: 0.89,
    legOrder: 1,
    ...overrides,
  };
}

export function makeLegDetail(overrides: Partial<RecommendationLegDetail> = {}): RecommendationLegDetail {
  return {
    ...makeLeg(),
    whySelected: "top-ranked qualifying candidate",
    strongestEvidence: "Injury Intelligence, Weather",
    contributingAgents: [{ name: "injury_intelligence_agent", weight: 0.4 }],
    biggestRisks: "elevated outcome variance",
    rejectedAlternatives: [],
    wouldChangeMindIf: "a key starter is ruled out pregame",
    agentContributions: [
      {
        agentId: "agent-1",
        agentName: "injury_intelligence_agent",
        agentConfidence: 0.9,
        weightApplied: 1.05,
        directionalLean: "home",
        modelName: "claude-sonnet-5",
        provider: "anthropic",
        usedFallback: false,
        promptName: "injury_intelligence_agent",
        promptVersion: 1,
      },
    ],
    consensus: {
      aggregateConfidence: 0.87,
      agreementVariance: 0.03,
      finalAggregateConfidence: 0.89,
      belowConfidenceFloor: false,
    },
    ...overrides,
  };
}

export function makeGrade(overrides: Partial<RecommendationGrade> = {}): RecommendationGrade {
  return {
    outcome: "WIN",
    gradedAt: "2026-08-29T02:00:00Z",
    isCorrection: false,
    correctedAt: null,
    ...overrides,
  };
}

export function makeCard(overrides: Partial<RecommendationCardData> = {}): RecommendationCardData {
  return {
    displayId: "2026-00100",
    recommendationType: "single",
    scope: "game",
    status: "active",
    minRequiredTier: "free",
    withdrawnAt: null,
    withdrawalReason: null,
    decidedAt: "2026-08-28T06:00:30Z",
    grade: null,
    game: {
      homeTeam: "Chiefs",
      awayTeam: "Bills",
      scheduledStart: "2026-08-28T18:00:00Z",
      status: "scheduled",
    },
    oneLineSummary: "highest-ranked qualifying candidate",
    legs: [makeLeg()],
    ...overrides,
  };
}

export function makeDetail(overrides: Partial<RecommendationDetailData> = {}): RecommendationDetailData {
  return {
    ...makeCard(),
    legs: [makeLegDetail()],
    whyNotOtherShapes: "no other candidate cleared the confidence floor",
    rejectedAlternatives: [],
    dataLimitations: "Sharp money and public betting data are not yet available.",
    ...overrides,
  };
}
