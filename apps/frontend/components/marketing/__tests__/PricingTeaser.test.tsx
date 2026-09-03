import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PricingTeaser } from "../PricingTeaser";
import { PRICING_PLANS } from "../pricingData";

describe("PricingTeaser (Public Web M3)", () => {
  it("shows only the three plan names and prices -- no entitlement list, no full matrix", () => {
    render(<PricingTeaser />);
    for (const plan of PRICING_PLANS) {
      expect(screen.getByText(plan.name)).toBeInTheDocument();
      expect(screen.getByText(plan.price)).toBeInTheDocument();
    }
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("Most Popular")).not.toBeInTheDocument();
  });

  it("links to the full /pricing page via a Compare Plans CTA", () => {
    render(<PricingTeaser />);
    const link = screen.getByRole("link", { name: "Compare Plans" });
    expect(link).toHaveAttribute("href", "/pricing");
  });

  it("prices match the shared PRICING_PLANS source exactly, so it can't drift from the full page", () => {
    render(<PricingTeaser />);
    expect(screen.getByText("$19.99")).toBeInTheDocument();
    expect(screen.getByText("$34.99")).toBeInTheDocument();
    expect(screen.getByText("$69.99")).toBeInTheDocument();
  });
});
