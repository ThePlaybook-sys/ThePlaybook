import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BoardCard } from "../BoardCard";
import { makeCard, makeGrade } from "@/components/recommendations/__tests__/fixtures";

describe("BoardCard", () => {
  it("leads with matchup/game context (scheduled time) above the decision", () => {
    render(
      <BoardCard
        recommendation={makeCard({
          game: { homeTeam: "Chiefs", awayTeam: "Bills", scheduledStart: "2026-09-02T20:20:00Z", status: "scheduled" },
        })}
      />,
    );
    expect(screen.getByText(/Sep 2/)).toBeInTheDocument();
    expect(screen.getByText("Bills @ Chiefs")).toBeInTheDocument();
  });

  it("a slate-scoped decision (no game) renders 'Today's Slate' as its context, not a blank or error state", () => {
    render(
      <BoardCard
        recommendation={makeCard({
          recommendationType: "bankroll_preservation",
          scope: "slate",
          game: null,
          legs: [],
        })}
      />,
    );
    expect(screen.getByText("Today's Slate")).toBeInTheDocument();
    expect(screen.getByText("MANSA Is Passing Today")).toBeInTheDocument();
  });

  it("No Bet renders as a real, equal-weight MANSA decision -- same card structure as an active recommendation", () => {
    render(
      <BoardCard
        recommendation={makeCard({ recommendationType: "no_bet", legs: [], oneLineSummary: "no candidate qualified" })}
      />,
    );
    expect(screen.getByText("MANSA Is Passing On This Game")).toBeInTheDocument();
    expect(screen.getByText("no candidate qualified")).toBeInTheDocument();
  });

  it("links to the recommendation's existing detail route -- Layer 1-4 architecture is reused, not replaced", () => {
    const { container } = render(<BoardCard recommendation={makeCard({ displayId: "2026-00100" })} />);
    expect(container.querySelector("a")).toHaveAttribute("href", "/recommendations/2026-00100");
  });

  it("renders confidence, EV, and price as instrument metrics, never a fabricated modeled-probability number", () => {
    render(<BoardCard recommendation={makeCard()} />);
    expect(screen.getByText("89%")).toBeInTheDocument();
    expect(screen.getByText("+6.3%")).toBeInTheDocument();
    expect(screen.getByText("-135")).toBeInTheDocument();
    expect(screen.queryByText(/probability/i)).not.toBeInTheDocument();
  });

  it("shows a graded outcome badge when a grade is present", () => {
    render(<BoardCard recommendation={makeCard({ grade: makeGrade({ outcome: "WIN" }) })} />);
    expect(screen.getByText("Win")).toHaveAttribute("data-state-tone", "positive");
  });

  it("No Bet gets a restrained Attention Amber top edge instead of MANSA cobalt/violet Illumination -- a deliberate decline, never an error", () => {
    const { container } = render(
      <BoardCard recommendation={makeCard({ recommendationType: "no_bet", legs: [] })} />,
    );
    const surface = container.querySelector("[data-surface-level='card']");
    expect(surface?.className).toContain("border-t-attention-amber");
    expect(surface?.className).not.toContain("mansa-illuminated-edge-top");
  });

  it("an active recommendation gets the MANSA cobalt/violet Illumination top edge, not the amber decline treatment", () => {
    const { container } = render(<BoardCard recommendation={makeCard()} />);
    const surface = container.querySelector("[data-surface-level='card']");
    expect(surface?.className).toContain("mansa-illuminated-edge-top");
    expect(surface?.className).not.toContain("border-t-attention-amber");
  });
});
