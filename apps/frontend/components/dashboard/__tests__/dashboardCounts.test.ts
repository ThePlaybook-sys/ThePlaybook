import { describe, expect, it } from "vitest";
import { computeDashboardCounts } from "../dashboardCounts";
import { makeCard } from "@/components/recommendations/__tests__/fixtures";

describe("computeDashboardCounts", () => {
  it("all zero for an empty array", () => {
    expect(computeDashboardCounts([])).toEqual({
      recommendationCount: 0,
      noBetCount: 0,
      gamesRepresentedCount: 0,
    });
  });

  it("counts recommendation PRODUCTS, not legs -- a two-leg product counts once", () => {
    const twoLegProduct = makeCard({
      recommendationType: "multiple_singles",
      legs: [
        { marketType: "moneyline", selection: "Chiefs", sportsbook: "book", americanOdds: -135, point: null, decimalOdds: 1.74, evPerDollar: 0.06, finalAggregateConfidence: 0.8, legOrder: 1 },
        { marketType: "spread", selection: "Bills -3", sportsbook: "book", americanOdds: -110, point: -3, decimalOdds: 1.91, evPerDollar: 0.04, finalAggregateConfidence: 0.7, legOrder: 2 },
      ],
    });
    expect(computeDashboardCounts([twoLegProduct]).recommendationCount).toBe(1);
  });

  it("real M7.1 correction: two products sharing the same game count as one game represented, while still both counted as two recommendations", () => {
    const sharedGame = { homeTeam: "Chiefs", awayTeam: "Bills", scheduledStart: "2026-09-02T20:20:00Z", status: "scheduled" };
    const productA = makeCard({ displayId: "2026-00101", game: sharedGame });
    const productB = makeCard({ displayId: "2026-00102", game: sharedGame });

    const counts = computeDashboardCounts([productA, productB]);

    expect(counts.recommendationCount).toBe(2);
    expect(counts.gamesRepresentedCount).toBe(1);
  });

  it("counts distinct games correctly across multiple different games", () => {
    const gameA = { homeTeam: "Chiefs", awayTeam: "Bills", scheduledStart: "2026-09-02T20:20:00Z", status: "scheduled" };
    const gameB = { homeTeam: "Rams", awayTeam: "Seahawks", scheduledStart: "2026-09-02T16:05:00Z", status: "scheduled" };
    const counts = computeDashboardCounts([makeCard({ game: gameA }), makeCard({ game: gameB, displayId: "2026-00103" })]);

    expect(counts.gamesRepresentedCount).toBe(2);
  });

  it("a slate-scoped product (game: null, e.g. bankroll_preservation) contributes to recommendationCount but not gamesRepresentedCount", () => {
    const slateProduct = makeCard({ recommendationType: "bankroll_preservation", scope: "slate", game: null, legs: [] });
    const counts = computeDashboardCounts([slateProduct]);

    expect(counts.recommendationCount).toBe(1);
    expect(counts.gamesRepresentedCount).toBe(0);
  });

  it("counts only no_bet toward noBetCount -- bankroll_preservation is a distinct, separately-worded decision", () => {
    const noBet = makeCard({ recommendationType: "no_bet", legs: [] });
    const bankroll = makeCard({ displayId: "2026-00104", recommendationType: "bankroll_preservation", scope: "slate", game: null, legs: [] });

    const counts = computeDashboardCounts([noBet, bankroll]);

    expect(counts.noBetCount).toBe(1);
    expect(counts.recommendationCount).toBe(2);
  });
});
