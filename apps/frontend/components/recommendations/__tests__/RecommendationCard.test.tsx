import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RecommendationCard } from "../RecommendationCard";
import { makeCard, makeGrade } from "./fixtures";

describe("RecommendationCard", () => {
  it("renders an active single recommendation with its leg, price, and confidence", () => {
    render(<RecommendationCard recommendation={makeCard()} />);
    expect(screen.getByText("Bills @ Chiefs")).toBeInTheDocument();
    expect(screen.getByText("Chiefs")).toBeInTheDocument();
    expect(screen.getByText("-135")).toBeInTheDocument();
    expect(screen.getByText("89%")).toBeInTheDocument();
  });

  it("links to the recommendation's detail route", () => {
    render(<RecommendationCard recommendation={makeCard({ displayId: "2026-00100" })} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/recommendations/2026-00100");
  });

  it("links into a different base path when linkTo is given (Milestone 4 reuse for /history)", () => {
    render(<RecommendationCard recommendation={makeCard({ displayId: "2026-00100" })} linkTo="/history" />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/history/2026-00100");
  });

  it("renders No Bet at equal visual weight -- no leg list, headline carries the verdict", () => {
    render(
      <RecommendationCard
        recommendation={makeCard({
          recommendationType: "no_bet",
          legs: [],
          oneLineSummary: "no candidate qualified",
        })}
      />,
    );
    expect(screen.getByText("MANSA Is Passing On This Game")).toBeInTheDocument();
    expect(screen.getByText("no candidate qualified")).toBeInTheDocument();
    expect(screen.queryByText("-135")).not.toBeInTheDocument();
  });

  it("renders Bankroll Preservation at the slate level", () => {
    render(
      <RecommendationCard
        recommendation={makeCard({
          recommendationType: "bankroll_preservation",
          scope: "slate",
          game: null,
          legs: [],
        })}
      />,
    );
    expect(screen.getByText("MANSA Is Passing Today")).toBeInTheDocument();
  });

  it("renders the withdrawn treatment with its reason", () => {
    render(
      <RecommendationCard
        recommendation={makeCard({
          status: "withdrawn",
          withdrawnAt: "2026-08-28T10:00:00Z",
          withdrawalReason: "line moved past invalidation threshold",
        })}
      />,
    );
    expect(screen.getByText("Withdrawn")).toBeInTheDocument();
    expect(screen.getByText("Withdrawn: line moved past invalidation threshold")).toBeInTheDocument();
  });

  it.each([
    ["WIN", "Win", "positive"],
    ["LOSS", "Loss", "negative"],
    ["PUSH", "Push", "neutral"],
    ["VOID_NO_ACTION", "Void", "neutral"],
    ["MIXED_SETTLED", "Mixed Settled", "neutral"],
  ] as const)("renders the %s grade as a %s badge", (outcome, label, tone) => {
    render(<RecommendationCard recommendation={makeCard({ grade: makeGrade({ outcome }) })} />);
    expect(screen.getByText(label)).toHaveAttribute("data-state-tone", tone);
  });

  it("never renders a badge for an ungraded product", () => {
    render(<RecommendationCard recommendation={makeCard({ grade: null })} />);
    expect(screen.queryByText(/win|loss|push|void|mixed settled/i)).not.toBeInTheDocument();
  });

  it("never renders a badge for NOT_APPLICABLE -- not a settled-bet outcome", () => {
    render(
      <RecommendationCard
        recommendation={makeCard({
          recommendationType: "no_bet",
          legs: [],
          grade: makeGrade({ outcome: "NOT_APPLICABLE" }),
        })}
      />,
    );
    expect(screen.queryByText(/not applicable/i)).not.toBeInTheDocument();
  });

  it("renders a distinct corrected-result sub-label with its own date, never a silent badge swap", () => {
    render(
      <RecommendationCard
        recommendation={makeCard({
          grade: makeGrade({ outcome: "LOSS", isCorrection: true, correctedAt: "2026-08-30T09:00:00Z" }),
        })}
      />,
    );
    expect(screen.getByText("Loss")).toBeInTheDocument();
    expect(screen.getByText(/Result corrected/)).toBeInTheDocument();
  });

  it("shows recommendation-decision freshness, never source/intelligence freshness language", () => {
    render(<RecommendationCard recommendation={makeCard({ decidedAt: "2026-08-28T06:00:30Z" })} />);
    expect(screen.getByText(/^Decided /)).toBeInTheDocument();
    expect(screen.queryByText(/updated/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/refreshed/i)).not.toBeInTheDocument();
  });

  it("real M7 fix: uses the valid `accent` token, not the non-generated `accent-primary`, for hover/focus styling", () => {
    const { container } = render(<RecommendationCard recommendation={makeCard()} />);
    const link = container.querySelector("a");
    expect(link?.className).toContain("focus-visible:outline-accent");
    expect(link?.className).not.toContain("accent-primary");
  });

  it("keeps the headline shrinkable (min-w-0) so a long team name wraps instead of overflowing next to the badge column", () => {
    render(
      <RecommendationCard
        recommendation={makeCard({
          game: {
            awayTeam: "A Very Long Team Name FC",
            homeTeam: "Chiefs",
            scheduledStart: "2026-08-28T18:00:00Z",
            status: "scheduled",
          },
        })}
      />,
    );
    expect(screen.getByText(/A Very Long Team Name FC @ Chiefs/)).toHaveClass("min-w-0");
  });
});
