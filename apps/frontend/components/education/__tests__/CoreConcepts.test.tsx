import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CoreConcepts } from "../CoreConcepts";

describe("CoreConcepts", () => {
  it("renders all four required concepts", () => {
    render(<CoreConcepts />);
    expect(screen.getByText("Confidence")).toBeInTheDocument();
    expect(screen.getByText("Modeled Probability")).toBeInTheDocument();
    expect(screen.getByText("EV")).toBeInTheDocument();
    expect(screen.getByText("No Bet")).toBeInTheDocument();
  });

  it("is explicit that Confidence is not automatically the probability of winning -- the exact distinction HQ required", () => {
    render(<CoreConcepts />);
    expect(screen.getByText(/not automatically the probability that the wager wins/)).toBeInTheDocument();
  });

  it("frames No Bet as a legitimate recommendation, not a failure", () => {
    render(<CoreConcepts />);
    expect(screen.getByText(/legitimate recommendation on its own, not a failure/)).toBeInTheDocument();
  });

  it("never renders 'MANSA' anywhere -- the established product voice is The Playbook", () => {
    render(<CoreConcepts />);
    expect(screen.queryByText(/MANSA/)).not.toBeInTheDocument();
  });

  it("omits the section heading in compact mode (onboarding's first-use pass)", () => {
    const { rerender } = render(<CoreConcepts />);
    expect(screen.getByText("The Basics")).toBeInTheDocument();

    rerender(<CoreConcepts compact />);
    expect(screen.queryByText("The Basics")).not.toBeInTheDocument();
  });
});
