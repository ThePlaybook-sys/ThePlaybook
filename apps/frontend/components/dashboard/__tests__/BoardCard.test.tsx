import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BoardCard } from "../BoardCard";
import { makeCard, makeGrade } from "@/components/recommendations/__tests__/fixtures";

describe("BoardCard -- game context vs MANSA Decision (M7.4 §1-§4)", () => {
  it("leads with the real matchup and scheduled time, above the MANSA Decision zone", () => {
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

  it("labels the decision zone 'MANSA Decision' and renders the selection as the dominant decision value", () => {
    render(<BoardCard recommendation={makeCard()} />);
    expect(screen.getByText("MANSA Decision")).toBeInTheDocument();
    // makeLeg()'s default selection is "Chiefs" -- the decision value, not
    // merely a leg line buried among metrics.
    expect(screen.getByText("Chiefs")).toBeInTheDocument();
  });
});

describe("BoardCard -- game-specific No Bet always identifies the game (M7.4 §5)", () => {
  it("a game-specific No Bet shows the real matchup, never an anonymous card with only a kickoff time", () => {
    render(
      <BoardCard
        recommendation={makeCard({
          recommendationType: "no_bet",
          legs: [],
          game: { homeTeam: "Cowboys", awayTeam: "Eagles", scheduledStart: "2026-09-02T17:00:00Z", status: "scheduled" },
          oneLineSummary: "no candidate qualified",
        })}
      />,
    );
    expect(screen.getByText("Eagles @ Cowboys")).toBeInTheDocument();
    expect(screen.getByText("MANSA Decision")).toBeInTheDocument();
    expect(screen.getByText("No Bet")).toBeInTheDocument();
    expect(screen.getByText("no candidate qualified")).toBeInTheDocument();
  });
});

describe("BoardCard -- slate-wide Bankroll Preservation never fabricates a matchup (M7.4 §6)", () => {
  it("renders 'Today's Slate' and 'Bankroll Preservation' as the decision, with no game/kickoff text anywhere", () => {
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
    expect(screen.getByText("MANSA Decision")).toBeInTheDocument();
    expect(screen.getByText("Bankroll Preservation")).toBeInTheDocument();
    // No fabricated matchup text (any "@"-joined team pairing) anywhere.
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
  });

  it("game-specific No Bet and slate-wide Bankroll Preservation are visually distinct decisions, never confused", () => {
    const { rerender, container } = render(
      <BoardCard
        recommendation={makeCard({
          recommendationType: "no_bet",
          legs: [],
          game: { homeTeam: "Cowboys", awayTeam: "Eagles", scheduledStart: "2026-09-02T17:00:00Z", status: "scheduled" },
        })}
      />,
    );
    expect(screen.getByText("Eagles @ Cowboys")).toBeInTheDocument();
    expect(screen.getByText("No Bet")).toBeInTheDocument();
    expect(screen.queryByText("Today's Slate")).not.toBeInTheDocument();
    expect(screen.queryByText("Bankroll Preservation")).not.toBeInTheDocument();

    rerender(
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
    expect(screen.getByText("Bankroll Preservation")).toBeInTheDocument();
    expect(screen.queryByText("No Bet")).not.toBeInTheDocument();
    expect(container.querySelector("[data-recommendation-type='bankroll_preservation']")).toBeInTheDocument();
  });
});

describe("BoardCard -- decision remains understandable after settlement and withdrawal (M7.4 §16-§17)", () => {
  it("the original decision text is still present after a WIN", () => {
    render(<BoardCard recommendation={makeCard({ grade: makeGrade({ outcome: "WIN" }) })} />);
    expect(screen.getByText("Chiefs")).toBeInTheDocument();
    expect(screen.getByText("Win")).toHaveAttribute("data-state-tone", "positive");
  });

  it("the original decision text is still present after a LOSS", () => {
    render(<BoardCard recommendation={makeCard({ grade: makeGrade({ outcome: "LOSS" }) })} />);
    expect(screen.getByText("Chiefs")).toBeInTheDocument();
    expect(screen.getByText("Loss")).toHaveAttribute("data-state-tone", "negative");
  });

  it("the original decision text is still present after a VOID/withdrawal, and the withdrawal reason never overwhelms it", () => {
    render(
      <BoardCard
        recommendation={makeCard({
          status: "withdrawn",
          withdrawnAt: "2026-08-28T12:00:00Z",
          withdrawalReason: "Key starter ruled out pregame",
          grade: makeGrade({ outcome: "VOID_NO_ACTION" }),
        })}
      />,
    );
    expect(screen.getByText("Chiefs")).toBeInTheDocument();
    expect(screen.getByText("Withdrawn: Key starter ruled out pregame")).toBeInTheDocument();
    expect(screen.getByText("Withdrawn")).toBeInTheDocument();
    expect(screen.getByText("Void")).toHaveAttribute("data-state-tone", "neutral");
  });
});

describe("BoardCard -- links, metrics, edge treatment (unchanged semantics)", () => {
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

  it("an ungraded active recommendation gets an explicit 'Active' status indicator", () => {
    render(<BoardCard recommendation={makeCard()} />);
    expect(screen.getByText("Active")).toHaveAttribute("data-state-tone", "neutral");
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

  it("a very long selection wraps safely inside the decision zone without losing any text", () => {
    // M7.5's contract audit confirmed `selection` is always a clean
    // provider-reported name, never a compound string with fabricated
    // market-qualifier text -- the realistic stress case is a genuinely
    // long real full team name, not an invented promo-line suffix.
    const longSelection = "Tampa Bay Buccaneers";
    render(
      <BoardCard
        recommendation={makeCard({
          legs: [
            {
              marketType: "spread",
              selection: longSelection,
              sportsbook: "FanDuel",
              americanOdds: -110,
              point: 3.5,
              decimalOdds: 1.91,
              evPerDollar: 0.031,
              finalAggregateConfidence: 0.71,
              legOrder: 1,
            },
          ],
        })}
      />,
    );
    expect(screen.getByText(`${longSelection} +3.5`)).toBeInTheDocument();
  });

  it("renders full team names only, never an invented short abbreviation", () => {
    render(
      <BoardCard
        recommendation={makeCard({
          game: {
            homeTeam: "Kansas City Chiefs",
            awayTeam: "Buffalo Bills",
            scheduledStart: "2026-09-02T20:20:00Z",
            status: "scheduled",
          },
        })}
      />,
    );
    expect(screen.getByText("Buffalo Bills @ Kansas City Chiefs")).toBeInTheDocument();
    expect(screen.queryByText("KC")).not.toBeInTheDocument();
    expect(screen.queryByText("BUF")).not.toBeInTheDocument();
  });

  it("never invents a shortened selection either -- the full leg.selection renders verbatim even when long", () => {
    render(
      <BoardCard
        recommendation={makeCard({
          legs: [
            {
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
        })}
      />,
    );
    expect(screen.getByText("Jacksonville Jaguars +3.5")).toBeInTheDocument();
    expect(screen.queryByText("Jaguars +3.5")).not.toBeInTheDocument();
  });
});

describe("BoardCard -- market-type qualifier (M7.5 §3)", () => {
  it("shows a safely-derivable market label (from the market_type enum) beneath the decision value", () => {
    render(
      <BoardCard
        recommendation={makeCard({
          legs: [
            {
              marketType: "spread",
              selection: "Chiefs",
              sportsbook: "book",
              americanOdds: -135,
              point: -3.5,
              decimalOdds: 1.74,
              evPerDollar: 0.063,
              finalAggregateConfidence: 0.89,
              legOrder: 1,
            },
          ],
        })}
      />,
    );
    expect(screen.getByText("Spread")).toBeInTheDocument();
  });

  it("moneyline/total/prop each get their own real label, never a fabricated qualifier like 'Alternate Spread'", () => {
    const legFor = (marketType: "moneyline" | "total" | "prop") => [
      {
        marketType,
        selection: "Chiefs",
        sportsbook: "book",
        americanOdds: -135,
        point: null,
        decimalOdds: 1.74,
        evPerDollar: 0.063,
        finalAggregateConfidence: 0.89,
        legOrder: 1,
      },
    ];
    const { rerender } = render(<BoardCard recommendation={makeCard({ legs: legFor("moneyline") })} />);
    expect(screen.getByText("Moneyline")).toBeInTheDocument();

    rerender(<BoardCard recommendation={makeCard({ legs: legFor("total") })} />);
    expect(screen.getByText("Total")).toBeInTheDocument();

    rerender(<BoardCard recommendation={makeCard({ legs: legFor("prop") })} />);
    expect(screen.getByText("Player Prop")).toBeInTheDocument();

    expect(screen.queryByText(/alternate/i)).not.toBeInTheDocument();
  });
});

describe("BoardCard -- mobile information density (M7.5 §6)", () => {
  it("card padding and gaps are responsive -- tighter below the sm breakpoint, unchanged at sm and above", () => {
    const { container } = render(<BoardCard recommendation={makeCard()} />);
    const surface = container.querySelector("[data-surface-level='card']");
    expect(surface?.className).toContain("p-md");
    expect(surface?.className).toContain("sm:p-lg");
    expect(surface?.className).toContain("gap-sm");
    expect(surface?.className).toContain("sm:gap-md");
  });

  it("typography sizes are unchanged -- density comes from spacing, never from shrinking the decision value below display scale", () => {
    render(<BoardCard recommendation={makeCard()} />);
    const decisionValue = screen.getByText("Chiefs");
    expect(decisionValue).toHaveClass("text-display");
  });
});
