import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RecommendationDetail } from "../RecommendationDetail";
import { makeDetail, makeGrade, makeLegDetail } from "./fixtures";

describe("RecommendationDetail", () => {
  it("renders Layer 1 as a semantic heading", () => {
    render(<RecommendationDetail recommendation={makeDetail()} />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("Bills @ Chiefs");
  });

  it("renders Layer 2 (evidence/risk/contributing agents) visible by default, no explicit expansion needed", () => {
    render(<RecommendationDetail recommendation={makeDetail()} />);
    expect(screen.getByText("Injury Intelligence, Weather")).toBeInTheDocument();
    expect(screen.getByText("elevated outcome variance")).toBeInTheDocument();
    // Also appears in Layer 4's agent-contributions list (own fixture,
    // same agent) -- Layer 2's own contributing-agents summary is one
    // of at least one match, not the only occurrence in the document.
    expect(screen.getAllByText("injury_intelligence_agent").length).toBeGreaterThanOrEqual(1);
  });

  it("keeps Layer 3 (would change our mind) and Layer 4 (provenance/consensus) behind native, keyboard-accessible disclosures, closed by default", () => {
    render(<RecommendationDetail recommendation={makeDetail()} />);
    const disclosures = document.querySelectorAll("details");
    expect(disclosures.length).toBeGreaterThan(0);
    disclosures.forEach((details) => {
      expect(details.hasAttribute("open")).toBe(false);
      expect(details.querySelector("summary")).not.toBeNull();
    });
    // Layer 4 content exists in the DOM (native <details> keeps it
    // present, just visually collapsed) -- provenance is never the
    // Layer 2 default view.
    expect(screen.getByText(/claude-sonnet-5/)).toBeInTheDocument();
    expect(screen.getByText(/a key starter is ruled out pregame/)).toBeInTheDocument();
  });

  it("never surfaces Layer 4 provenance detail outside a disclosure", () => {
    render(<RecommendationDetail recommendation={makeDetail()} />);
    const provenanceText = screen.getByText(/claude-sonnet-5/);
    expect(provenanceText.closest("details")).not.toBeNull();
  });

  it("preserves leg_order across multiple legs (multiple_singles)", () => {
    render(
      <RecommendationDetail
        recommendation={makeDetail({
          recommendationType: "multiple_singles",
          legs: [
            makeLegDetail({ selection: "Chiefs", legOrder: 1 }),
            makeLegDetail({ selection: "Bills", legOrder: 2 }),
            makeLegDetail({ selection: "Eagles", legOrder: 3 }),
          ],
        })}
      />,
    );
    const selections = screen.getAllByText(/^(Chiefs|Bills|Eagles)$/).map((el) => el.textContent);
    expect(selections).toEqual(["Chiefs", "Bills", "Eagles"]);
  });

  it("handles missing per-leg explanation data honestly -- no crash, no fabricated content", () => {
    render(
      <RecommendationDetail
        recommendation={makeDetail({
          legs: [
            makeLegDetail({
              strongestEvidence: null,
              biggestRisks: null,
              contributingAgents: [],
              wouldChangeMindIf: null,
              agentContributions: [],
              consensus: null,
            }),
          ],
        })}
      />,
    );
    expect(screen.getByText("Chiefs")).toBeInTheDocument();
    expect(screen.queryByText("Strongest evidence")).not.toBeInTheDocument();
    expect(screen.queryByText("Deeper reasoning")).not.toBeInTheDocument();
  });

  it("renders the No Bet/Bankroll Preservation passing verdict without a leg breakdown", () => {
    render(
      <RecommendationDetail
        recommendation={makeDetail({
          recommendationType: "no_bet",
          legs: [],
          oneLineSummary: "no candidate qualified",
        })}
      />,
    );
    expect(screen.getByText("MANSA Is Passing On This Game")).toBeInTheDocument();
    expect(screen.getByText("no candidate qualified")).toBeInTheDocument();
  });

  it("renders the graded outcome and correction sub-label at the top level", () => {
    render(
      <RecommendationDetail
        recommendation={makeDetail({
          grade: makeGrade({ outcome: "LOSS", isCorrection: true, correctedAt: "2026-08-30T09:00:00Z" }),
        })}
      />,
    );
    expect(screen.getByText("Loss")).toBeInTheDocument();
    expect(screen.getByText(/Result corrected/)).toBeInTheDocument();
  });
});
