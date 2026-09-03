import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConversationalPreview } from "../ConversationalPreview";

describe("ConversationalPreview (Public Web M2.2)", () => {
  it("shows HQ's exact example exchange", () => {
    render(<ConversationalPreview />);
    expect(
      screen.getByText("Build me a 4-leg parlay from Sunday's strongest opportunities."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Three legs meet my threshold. I'm leaving the fourth out rather than forcing it."),
    ).toBeInTheDocument();
  });

  it("shows a compact resulting 3-leg parlay summary, and names the excluded fourth leg only narratively", () => {
    render(<ConversationalPreview />);
    expect(screen.getByText("3-Leg Parlay")).toBeInTheDocument();
    expect(screen.getByText(/Kansas City Chiefs — Moneyline/)).toBeInTheDocument();
    expect(screen.getByText(/Buffalo Bills — Spread/)).toBeInTheDocument();
    expect(screen.getByText(/Under 47.5 — Total/)).toBeInTheDocument();
    expect(screen.getByText(/fourth opportunity was evaluated and excluded/i)).toBeInTheDocument();
  });

  it("never shows fabricated combined confidence/EV numbers for the parlay -- parlay scoring isn't real yet", () => {
    render(<ConversationalPreview />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\d+%/);
    expect(text).not.toMatch(/[+-]\d+(\.\d+)?%/);
  });

  it("is clearly marked as a preview at least twice (the surface itself and the parlay result)", () => {
    render(<ConversationalPreview />);
    expect(screen.getAllByText(/^Preview/).length).toBeGreaterThanOrEqual(2);
  });

  it("is entirely non-interactive -- no inputs, buttons, or links; a single decorative image role carries the accessible summary", () => {
    render(<ConversationalPreview />);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /MANSA Telegram conversation/i }),
    ).toBeInTheDocument();
  });

  it("carries the MANSA-on-Telegram label", () => {
    render(<ConversationalPreview />);
    expect(screen.getByText("MANSA, on Telegram")).toBeInTheDocument();
  });
});
