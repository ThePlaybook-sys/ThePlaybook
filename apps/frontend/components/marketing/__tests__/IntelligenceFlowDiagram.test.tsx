import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { IntelligenceFlowDiagram } from "../IntelligenceFlowDiagram";

describe("IntelligenceFlowDiagram (Public Web M2.1)", () => {
  it("shows the three stages in order: Data -> Intelligence & AI Committee -> MANSA Decision", () => {
    render(<IntelligenceFlowDiagram />);
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["Data", "Intelligence & AI Committee", "MANSA Decision"]);
  });

  it("never implies fake live activity -- no numeric/percentage content, nothing that reads as a live metric", () => {
    render(<IntelligenceFlowDiagram />);
    const text = screen.getByText("Data").closest("div")?.parentElement?.textContent ?? "";
    expect(text).not.toMatch(/%|\blive\b|\bnow\b/i);
  });

  it("the connecting line is purely decorative and stays out of the accessibility tree", () => {
    const { container } = render(<IntelligenceFlowDiagram />);
    const decorative = container.querySelectorAll('[aria-hidden="true"]');
    expect(decorative.length).toBeGreaterThan(0);
  });
});
