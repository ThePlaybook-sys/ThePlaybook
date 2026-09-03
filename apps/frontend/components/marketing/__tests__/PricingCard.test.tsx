import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PricingCard } from "../PricingCard";
import { PRICING_PLANS } from "../pricingData";

const [core, pro, elite] = PRICING_PLANS;

describe("PricingCard (Public Web M3)", () => {
  it("renders a plan's name, price, tagline, and highlights concisely -- no full entitlement dump", () => {
    render(<PricingCard plan={core} ctaHref="/sign-in?mode=sign-up" ctaLabel="Create Account" />);
    expect(screen.getByText("Core")).toBeInTheDocument();
    expect(screen.getByText("$19.99")).toBeInTheDocument();
    expect(screen.getByText("/mo")).toBeInTheDocument();
    for (const highlight of core.highlights) {
      expect(screen.getByText(highlight)).toBeInTheDocument();
    }
  });

  it("shows the Most Popular tag only for the plan marked mostPopular", () => {
    const { rerender } = render(
      <PricingCard plan={core} ctaHref="/sign-in?mode=sign-up" ctaLabel="Create Account" />,
    );
    expect(screen.queryByText("Most Popular")).not.toBeInTheDocument();

    rerender(<PricingCard plan={pro} ctaHref="/sign-in?mode=sign-up" ctaLabel="Create Account" />);
    expect(screen.getByText("Most Popular")).toBeInTheDocument();
  });

  it("renders the passed-in CTA href/label rather than a hardcoded checkout link", () => {
    render(<PricingCard plan={elite} ctaHref="/today" ctaLabel="Open MANSA" />);
    const link = screen.getByRole("link", { name: "Open MANSA" });
    expect(link).toHaveAttribute("href", "/today");
  });

  it("never mentions checkout or payment processing", () => {
    render(<PricingCard plan={pro} ctaHref="/sign-in?mode=sign-up" ctaLabel="Create Account" />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/stripe/i);
    expect(text).not.toMatch(/checkout/i);
    expect(text).not.toMatch(/credit card/i);
  });
});
