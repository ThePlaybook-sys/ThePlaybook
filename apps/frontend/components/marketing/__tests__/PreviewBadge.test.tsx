import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PreviewBadge } from "../PreviewBadge";

describe("PreviewBadge (Public Web M2.2)", () => {
  it("defaults to the full 'Preview — Coming at Launch' label", () => {
    render(<PreviewBadge />);
    expect(screen.getByText("Preview — Coming at Launch")).toBeInTheDocument();
  });

  it("accepts a shorter custom label for tighter spaces", () => {
    render(<PreviewBadge label="Preview" />);
    expect(screen.getByText("Preview")).toBeInTheDocument();
  });

  it("uses the violet identity tone, never a state-triad color -- this is a roadmap marker, not a win/loss/freshness state", () => {
    render(<PreviewBadge />);
    const badge = screen.getByText("Preview — Coming at Launch");
    expect(badge.className).toContain("mansa-violet");
    expect(badge.className).not.toMatch(/state-(positive|negative|neutral)/);
  });
});
