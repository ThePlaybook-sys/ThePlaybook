import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PricingComparisonTable } from "../PricingComparisonTable";
import { COMPARISON_ROWS } from "../pricingData";

describe("PricingComparisonTable (Public Web M3)", () => {
  it("renders a real table with column headers for all three plans", () => {
    render(<PricingComparisonTable />);
    const table = screen.getByRole("table");
    expect(table).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Core" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Pro" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Elite" })).toBeInTheDocument();
  });

  it("renders every row from the shared data source, using row header semantics", () => {
    render(<PricingComparisonTable />);
    for (const row of COMPARISON_ROWS) {
      expect(screen.getByRole("rowheader", { name: new RegExp(row.label) })).toBeInTheDocument();
    }
  });

  it("marks only the not-yet-operational rows, without a badge per cell", () => {
    render(<PricingComparisonTable />);
    const notYetOperational = COMPARISON_ROWS.filter((row) => row.notYetOperational);
    // sr-only text renders once per marked row, plus the one shared legend line.
    const markers = screen.getAllByText("(not yet operational in DEV)");
    expect(markers).toHaveLength(notYetOperational.length);
    expect(screen.getByText(/† Not yet operational in DEV/)).toBeInTheDocument();
  });

  it("gives included/not-included symbols an accessible label", () => {
    render(<PricingComparisonTable />);
    expect(screen.getAllByLabelText("Included").length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText("Not included").length).toBeGreaterThan(0);
  });

  it("never renders an invented numeric limit as a cell value", () => {
    render(<PricingComparisonTable />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\d+\s*(messages|requests|tokens|parlays|refreshes)\b/i);
  });
});
