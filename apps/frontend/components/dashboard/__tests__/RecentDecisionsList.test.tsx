import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RecentDecisionsList } from "../RecentDecisionsList";
import { makeCard, makeGrade } from "@/components/recommendations/__tests__/fixtures";
import type { ApiResult, RecommendationCardData } from "@/app/lib/api-types";

function ok(data: RecommendationCardData[]): ApiResult<RecommendationCardData[]> {
  return { kind: "ok", data };
}

describe("RecentDecisionsList", () => {
  it("renders each row's authoritative state as a real StateBadge, never computed in the frontend", () => {
    render(
      <RecentDecisionsList
        recent={ok([
          makeCard({ displayId: "1", grade: makeGrade({ outcome: "WIN" }) }),
          makeCard({ displayId: "2", recommendationType: "no_bet", legs: [], grade: null }),
        ])}
      />,
    );
    expect(screen.getByText("Win")).toHaveAttribute("data-state-tone", "positive");
    expect(screen.getByText("No Bet")).toHaveAttribute("data-state-tone", "neutral");
  });

  it("links each row to the existing recommendation detail route", () => {
    render(<RecentDecisionsList recent={ok([makeCard({ displayId: "2026-00100" })])} />);
    expect(screen.getByRole("link", { name: /Bills @ Chiefs/ })).toHaveAttribute(
      "href",
      "/recommendations/2026-00100",
    );
  });

  it("links out to the full feed", () => {
    render(<RecentDecisionsList recent={ok([])} />);
    expect(screen.getByRole("link", { name: "See all" })).toHaveAttribute("href", "/recommendations");
  });

  it("honest empty state, never implying analysis is pending", () => {
    render(<RecentDecisionsList recent={ok([])} />);
    expect(screen.getByText("No decisions yet.")).toBeInTheDocument();
  });

  it("unauthenticated state renders distinctly from empty", () => {
    render(<RecentDecisionsList recent={{ kind: "unauthenticated" }} />);
    expect(screen.getByText("Sign in to see recent decisions.")).toBeInTheDocument();
  });

  it("shows at most 6 rows even when the feed returns more", () => {
    const many = Array.from({ length: 10 }, (_, i) => makeCard({ displayId: `2026-0010${i}` }));
    render(<RecentDecisionsList recent={ok(many)} />);
    expect(screen.getAllByRole("link").length).toBe(6 + 1); // 6 rows + "See all"
  });

  it("M7.5: a truncated matchup title exposes the full text via a title attribute -- mobile truncation stays understandable", () => {
    render(
      <RecentDecisionsList
        recent={ok([
          makeCard({
            displayId: "1",
            game: {
              homeTeam: "San Francisco 49ers",
              awayTeam: "Jacksonville Jaguars",
              scheduledStart: "2026-09-02T20:20:00Z",
              status: "scheduled",
            },
          }),
        ])}
      />,
    );
    expect(screen.getByText("Jacksonville Jaguars @ San Francisco 49ers")).toHaveAttribute(
      "title",
      "Jacksonville Jaguars @ San Francisco 49ers",
    );
  });
});
