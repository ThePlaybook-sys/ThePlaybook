import type { RecommendationCardData } from "@/app/lib/api-types";

export interface DashboardCounts {
  recommendationCount: number;
  noBetCount: number;
  gamesRepresentedCount: number;
}

/**
 * Milestone 7.1 -- exact count semantics (HQ's explicit instruction:
 * "do not blur products, legs, games, decisions"). Pure and
 * independently testable, no rendering involved.
 *
 * "Recommendations" counts recommendation PRODUCTS -- the array
 * `/v1/recommendations/today` already returns, one entry per persisted
 * product, never per leg.
 *
 * "No Bet decisions" counts only products with
 * `recommendationType === "no_bet"` -- `bankroll_preservation` is a
 * distinct, separately-worded decision and is not folded into this
 * count.
 *
 * "Games represented" counts distinct GAMES among those products.
 * Slate-scoped products (`game: null`, e.g. bankroll_preservation)
 * contribute no game. Two products sharing one game count as ONE game
 * represented here while still both rendering as two separate
 * `BoardCard`s on the board -- this dedup is deliberately about games,
 * never about collapsing or hiding a product (HQ's explicit M7.1
 * correction: multiple products per game must remain fully
 * representable).
 */
export function computeDashboardCounts(recommendations: RecommendationCardData[]): DashboardCounts {
  const gameKeys = new Set<string>();
  let noBetCount = 0;

  for (const recommendation of recommendations) {
    if (recommendation.recommendationType === "no_bet") {
      noBetCount += 1;
    }
    if (recommendation.game) {
      gameKeys.add(
        `${recommendation.game.homeTeam}|${recommendation.game.awayTeam}|${recommendation.game.scheduledStart}`,
      );
    }
  }

  return {
    recommendationCount: recommendations.length,
    noBetCount,
    gamesRepresentedCount: gameKeys.size,
  };
}
