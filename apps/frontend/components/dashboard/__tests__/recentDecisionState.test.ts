import { describe, expect, it } from "vitest";
import { recentDecisionState } from "../recentDecisionState";
import { makeCard, makeGrade } from "@/components/recommendations/__tests__/fixtures";

describe("recentDecisionState", () => {
  it("withdrawn takes priority regardless of type/grade", () => {
    expect(recentDecisionState(makeCard({ status: "withdrawn" }))).toEqual({ tone: "neutral", label: "Withdrawn" });
  });

  it.each([
    ["WIN", "Win", "positive"],
    ["LOSS", "Loss", "negative"],
    ["PUSH", "Push", "neutral"],
    ["VOID_NO_ACTION", "Void", "neutral"],
    ["MIXED_SETTLED", "Mixed Settled", "neutral"],
  ] as const)("graded outcome %s maps to label %s / tone %s", (outcome, label, tone) => {
    expect(recentDecisionState(makeCard({ grade: makeGrade({ outcome }) }))).toEqual({ tone, label });
  });

  it("no_bet with no grade (or NOT_APPLICABLE grade) is labeled No Bet, never calculated as an outcome", () => {
    expect(recentDecisionState(makeCard({ recommendationType: "no_bet", legs: [], grade: null }))).toEqual({
      tone: "neutral",
      label: "No Bet",
    });
  });

  it("bankroll_preservation is labeled distinctly from No Bet", () => {
    expect(
      recentDecisionState(
        makeCard({ recommendationType: "bankroll_preservation", scope: "slate", game: null, legs: [], grade: null }),
      ),
    ).toEqual({ tone: "neutral", label: "Bankroll Preservation" });
  });

  it("an active, ungraded, non-withdrawn recommendation is labeled Active", () => {
    expect(recentDecisionState(makeCard({ status: "active", grade: null }))).toEqual({
      tone: "neutral",
      label: "Active",
    });
  });

  it("NOT_APPLICABLE grade is never rendered as its own state -- falls through to the type-based label", () => {
    expect(
      recentDecisionState(makeCard({ recommendationType: "no_bet", legs: [], grade: makeGrade({ outcome: "NOT_APPLICABLE" }) })),
    ).toEqual({ tone: "neutral", label: "No Bet" });
  });
});
