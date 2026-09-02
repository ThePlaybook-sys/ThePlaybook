import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { IllustrativeDecisionCard } from "../IllustrativeDecisionCard";

describe("IllustrativeDecisionCard", () => {
  it("clearly labels itself as illustrative, never presented as a live recommendation", () => {
    render(<IllustrativeDecisionCard />);
    expect(screen.getByText("Illustrative Example")).toBeInTheDocument();
    expect(screen.getByText("Not a live recommendation")).toBeInTheDocument();
  });

  it("labels confidence as Confidence, never as win probability", () => {
    render(<IllustrativeDecisionCard />);
    expect(screen.getByText("Confidence")).toBeInTheDocument();
    expect(screen.queryByText(/win probability/i)).not.toBeInTheDocument();
  });

  it("renders the decision, EV, and formatted price using the real product formatting helpers", () => {
    render(<IllustrativeDecisionCard />);
    expect(screen.getByText("Kansas City Chiefs")).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
    expect(screen.getByText("+5.2%")).toBeInTheDocument();
    expect(screen.getByText("-145")).toBeInTheDocument();
  });

  it("is not an interactive link into the authenticated app", () => {
    render(<IllustrativeDecisionCard />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
