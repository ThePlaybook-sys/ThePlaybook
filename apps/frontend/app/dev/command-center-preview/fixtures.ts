import type {
  ApiResult,
  RecommendationCardData,
  RecommendationGrade,
  SourceFreshness,
  TrackRecordData,
} from "@/app/lib/api-types";

/**
 * Phase 6 Milestone 7.3 -- MANSA Command Center Visual Validation Showcase.
 *
 * Every value below is explicitly static, hand-authored fixture data. None
 * of it is read from or written to Supabase, none of it round-trips
 * through any API Gateway/AI Orchestrator/Sports Intelligence Layer route,
 * and none of it can ever appear in a real recommendation, Track Record,
 * grading, or adaptive-weighting computation -- this module has no
 * import of `app/lib/api.ts` or any fetch call whatsoever. It exists
 * solely so the real, unmodified `components/dashboard` components can be
 * rendered in every state HQ's M7.3 authorization requires, since DEV has
 * zero real recommendation products today.
 *
 * `displayId` values are deliberately prefixed `PREVIEW-` (never a real
 * `YYYY-NNNNN` id) so that even a stray click-through to
 * `/recommendations/{displayId}` (BoardCard's real, unmodified Link
 * target) surfaces an obviously-fake id on the resulting 404, rather than
 * anything that could be mistaken for a real recommendation reference.
 */

function grade(overrides: Partial<RecommendationGrade>): RecommendationGrade {
  return {
    outcome: "WIN",
    gradedAt: "2026-09-02T02:15:00Z",
    isCorrection: false,
    correctedAt: null,
    ...overrides,
  };
}

const CHIEFS_BILLS = {
  homeTeam: "Kansas City Chiefs",
  awayTeam: "Buffalo Bills",
  scheduledStart: "2026-09-02T20:20:00Z",
  status: "scheduled",
};

const NINERS_JAGUARS = {
  homeTeam: "Jacksonville Jaguars",
  awayTeam: "San Francisco 49ers",
  scheduledStart: "2026-09-02T17:00:00Z",
  status: "scheduled",
};

const EAGLES_COWBOYS = {
  homeTeam: "Dallas Cowboys",
  awayTeam: "Philadelphia Eagles",
  scheduledStart: "2026-09-02T20:20:00Z",
  status: "scheduled",
};

const RAVENS_BENGALS = {
  homeTeam: "Cincinnati Bengals",
  awayTeam: "Baltimore Ravens",
  scheduledStart: "2026-09-02T13:00:00Z",
  status: "final",
};

const PACKERS_VIKINGS = {
  homeTeam: "Minnesota Vikings",
  awayTeam: "Green Bay Packers",
  scheduledStart: "2026-09-02T13:00:00Z",
  status: "final",
};

const LIONS_BEARS = {
  homeTeam: "Chicago Bears",
  awayTeam: "Detroit Lions",
  scheduledStart: "2026-09-02T13:00:00Z",
  status: "final",
};

const DOLPHINS_JETS = {
  homeTeam: "New York Jets",
  awayTeam: "Miami Dolphins",
  scheduledStart: "2026-09-02T13:00:00Z",
  status: "final",
};

const STEELERS_BROWNS = {
  homeTeam: "Cleveland Browns",
  awayTeam: "Pittsburgh Steelers",
  scheduledStart: "2026-09-02T13:00:00Z",
  status: "final",
};

/**
 * Today's Board / MANSA Intelligence source -- 10 products, deliberately
 * dense (HQ's explicit "do not optimize the fixture to make the design
 * artificially easy" instruction), covering every required visual state
 * (§6 A-H) in one realistic slate: an ordinary active recommendation, a
 * long-team-name/long-selection-text stress case that also doubles as
 * two products sharing one game (§6.G), a No Bet, a slate-scoped
 * Bankroll Preservation, and five already-graded products spanning every
 * supported outcome (WIN/LOSS/PUSH/VOID_NO_ACTION/MIXED_SETTLED).
 */
export const BOARD_FIXTURES: RecommendationCardData[] = [
  {
    displayId: "PREVIEW-00001",
    recommendationType: "single",
    scope: "game",
    status: "active",
    minRequiredTier: "free",
    withdrawnAt: null,
    withdrawalReason: null,
    decidedAt: "2026-09-02T11:05:00Z",
    grade: null,
    game: CHIEFS_BILLS,
    oneLineSummary: "Highest-ranked qualifying candidate on the early slate.",
    legs: [
      {
        marketType: "moneyline",
        selection: "Kansas City Chiefs",
        sportsbook: "DraftKings",
        americanOdds: -145,
        point: null,
        decimalOdds: 1.69,
        evPerDollar: 0.054,
        finalAggregateConfidence: 0.86,
        legOrder: 1,
      },
    ],
  },
  {
    displayId: "PREVIEW-00002",
    recommendationType: "single",
    scope: "game",
    status: "active",
    minRequiredTier: "free",
    withdrawnAt: null,
    withdrawalReason: null,
    decidedAt: "2026-09-02T11:10:00Z",
    grade: null,
    game: NINERS_JAGUARS,
    oneLineSummary: "Long team names -- wrapping stress case.",
    legs: [
      {
        // M7.5 contract audit: `selection` is always the raw provider
        // outcome name -- a clean team name, never a compound string
        // with market-qualifier text baked in (no such field exists in
        // the schema). The realistic stress case is a genuinely long
        // real full team name, not a fabricated promo-line suffix.
        marketType: "spread",
        selection: "Jacksonville Jaguars",
        sportsbook: "FanDuel",
        americanOdds: -110,
        point: 3.5,
        decimalOdds: 1.91,
        evPerDollar: 0.031,
        finalAggregateConfidence: 0.71,
        legOrder: 1,
      },
    ],
  },
  {
    displayId: "PREVIEW-00003",
    recommendationType: "single",
    scope: "game",
    status: "active",
    minRequiredTier: "elite",
    withdrawnAt: null,
    withdrawalReason: null,
    decidedAt: "2026-09-02T11:12:00Z",
    grade: null,
    game: NINERS_JAGUARS,
    oneLineSummary: "A second, independent product for the same matchup -- multiplicity check.",
    legs: [
      {
        marketType: "total",
        selection: "Over",
        sportsbook: "BetMGM",
        americanOdds: -105,
        point: 47.5,
        decimalOdds: 1.95,
        evPerDollar: 0.022,
        finalAggregateConfidence: 0.68,
        legOrder: 1,
      },
    ],
  },
  {
    displayId: "PREVIEW-00004",
    recommendationType: "no_bet",
    scope: "game",
    status: "active",
    minRequiredTier: "free",
    withdrawnAt: null,
    withdrawalReason: null,
    decidedAt: "2026-09-02T11:15:00Z",
    grade: null,
    game: EAGLES_COWBOYS,
    oneLineSummary: "No candidate cleared the confidence floor for this matchup.",
    legs: [],
  },
  {
    displayId: "PREVIEW-00005",
    recommendationType: "bankroll_preservation",
    scope: "slate",
    status: "active",
    minRequiredTier: "free",
    withdrawnAt: null,
    withdrawalReason: null,
    decidedAt: "2026-09-02T11:20:00Z",
    grade: null,
    game: null,
    oneLineSummary: "Slate-wide risk posture favors preservation today.",
    legs: [],
  },
  {
    displayId: "PREVIEW-00006",
    recommendationType: "single",
    scope: "game",
    status: "active",
    minRequiredTier: "free",
    withdrawnAt: null,
    withdrawalReason: null,
    decidedAt: "2026-09-02T09:00:00Z",
    grade: grade({ outcome: "WIN", gradedAt: "2026-09-02T16:35:00Z" }),
    game: RAVENS_BENGALS,
    oneLineSummary: "Settled WIN -- final score confirmed the moneyline pick.",
    legs: [
      {
        marketType: "moneyline",
        selection: "Baltimore Ravens",
        sportsbook: "DraftKings",
        americanOdds: -120,
        point: null,
        decimalOdds: 1.83,
        evPerDollar: 0.048,
        finalAggregateConfidence: 0.82,
        legOrder: 1,
      },
    ],
  },
  {
    displayId: "PREVIEW-00007",
    recommendationType: "single",
    scope: "game",
    status: "active",
    minRequiredTier: "free",
    withdrawnAt: null,
    withdrawalReason: null,
    decidedAt: "2026-09-02T09:05:00Z",
    grade: grade({ outcome: "LOSS", gradedAt: "2026-09-02T16:40:00Z" }),
    game: PACKERS_VIKINGS,
    oneLineSummary: "Settled LOSS -- final score went against the spread pick.",
    legs: [
      {
        marketType: "spread",
        selection: "Green Bay Packers",
        sportsbook: "Caesars",
        americanOdds: -108,
        point: -2.5,
        decimalOdds: 1.93,
        evPerDollar: 0.019,
        finalAggregateConfidence: 0.74,
        legOrder: 1,
      },
    ],
  },
  {
    displayId: "PREVIEW-00008",
    recommendationType: "single",
    scope: "game",
    status: "active",
    minRequiredTier: "free",
    withdrawnAt: null,
    withdrawalReason: null,
    decidedAt: "2026-09-02T09:10:00Z",
    grade: grade({ outcome: "PUSH", gradedAt: "2026-09-02T16:45:00Z" }),
    game: LIONS_BEARS,
    oneLineSummary: "Settled PUSH -- final total landed exactly on the number.",
    legs: [
      {
        marketType: "total",
        selection: "Under",
        sportsbook: "FanDuel",
        americanOdds: -110,
        point: 44,
        decimalOdds: 1.91,
        evPerDollar: 0.027,
        finalAggregateConfidence: 0.7,
        legOrder: 1,
      },
    ],
  },
  {
    displayId: "PREVIEW-00009",
    recommendationType: "single",
    scope: "game",
    status: "withdrawn",
    minRequiredTier: "free",
    withdrawnAt: "2026-09-02T15:50:00Z",
    withdrawalReason: "Key starter ruled out pregame, invalidating the original edge.",
    decidedAt: "2026-09-02T09:15:00Z",
    grade: grade({ outcome: "VOID_NO_ACTION", gradedAt: "2026-09-02T16:50:00Z" }),
    game: DOLPHINS_JETS,
    oneLineSummary: "Settled VOID/No Action -- withdrawn before kickoff.",
    legs: [
      {
        marketType: "moneyline",
        selection: "Miami Dolphins",
        sportsbook: "BetMGM",
        americanOdds: 115,
        point: null,
        decimalOdds: 2.15,
        evPerDollar: 0.041,
        finalAggregateConfidence: 0.65,
        legOrder: 1,
      },
    ],
  },
  {
    displayId: "PREVIEW-00010",
    recommendationType: "multiple_singles",
    scope: "game",
    status: "active",
    minRequiredTier: "elite",
    withdrawnAt: null,
    withdrawalReason: null,
    decidedAt: "2026-09-02T09:20:00Z",
    grade: grade({ outcome: "MIXED_SETTLED", gradedAt: "2026-09-02T16:55:00Z" }),
    game: STEELERS_BROWNS,
    oneLineSummary: "Settled Mixed -- one leg won, one leg lost.",
    legs: [
      {
        marketType: "moneyline",
        selection: "Pittsburgh Steelers",
        sportsbook: "DraftKings",
        americanOdds: -135,
        point: null,
        decimalOdds: 1.74,
        evPerDollar: 0.037,
        finalAggregateConfidence: 0.79,
        legOrder: 1,
      },
      {
        marketType: "total",
        selection: "Over",
        sportsbook: "DraftKings",
        americanOdds: -110,
        point: 41.5,
        decimalOdds: 1.91,
        evPerDollar: 0.015,
        finalAggregateConfidence: 0.63,
        legOrder: 2,
      },
    ],
  },
];

export const BOARD_RESULT: ApiResult<RecommendationCardData[]> = { kind: "ok", data: BOARD_FIXTURES };

/**
 * Recent Decisions -- a separately-ordered, shorter fixture (real
 * `/v1/recommendations` is its own feed, not literally Today's Board),
 * curated so ACTIVE, NO BET, WIN, and LOSS all land inside
 * `RecentDecisionsList`'s own `MAX_ROWS = 6` window, per HQ's §9
 * requirement to show all four simultaneously.
 */
export const RECENT_DECISIONS_FIXTURES: RecommendationCardData[] = [
  BOARD_FIXTURES[0], // ACTIVE
  BOARD_FIXTURES[3], // NO BET
  BOARD_FIXTURES[5], // WIN
  BOARD_FIXTURES[6], // LOSS
  BOARD_FIXTURES[7], // PUSH
  BOARD_FIXTURES[9], // MIXED SETTLED
];

export const RECENT_DECISIONS_RESULT: ApiResult<RecommendationCardData[]> = {
  kind: "ok",
  data: RECENT_DECISIONS_FIXTURES,
};

/**
 * Track Record -- a clearly-labeled static fixture, product-count fields
 * only (no ROI/units/CLV/win-rate -- none of those exist in the real
 * `TrackRecordData` contract either, so none are fabricated here).
 */
export const TRACK_RECORD_RESULT: ApiResult<TrackRecordData> = {
  kind: "ok",
  data: {
    sampleSize: 47,
    sampleStatus: "mature",
    record: { win: 26, loss: 17, push: 2, voidNoAction: 1, mixedSettled: 1 },
    byRecommendationType: {},
  },
};

/** Source-data freshness -- mirrors a normal completed Master Refresh run. */
export const FRESHNESS_RESULT: ApiResult<SourceFreshness> = {
  kind: "ok",
  data: {
    status: "success",
    startedAt: "2026-09-02T11:00:00Z",
    completedAt: "2026-09-02T11:04:12Z",
    gamesInSlate: 14,
  },
};
