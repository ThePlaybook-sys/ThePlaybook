import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import HowItWorksPage from "../how-it-works/page";
import FeaturesPage from "../features/page";
import PricingPage from "../pricing/page";
import AboutPage from "../about/page";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

/**
 * Public Web M1 -- M2 will build the real How It Works / Features /
 * Pricing / About content. These four are clearly-handled placeholders,
 * never a broken link or a 404; these tests only prove that.
 */
describe.each([
  ["How It Works", HowItWorksPage],
  ["Features", FeaturesPage],
  ["Pricing", PricingPage],
  ["About", AboutPage],
])("%s placeholder page", (title, Page) => {
  it("renders a real heading and a path back into account creation, never a dead end", () => {
    render(<Page />);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    const createAccountLinks = screen.getAllByRole("link", { name: "Create Account" });
    expect(createAccountLinks.length).toBeGreaterThan(0);
    for (const link of createAccountLinks) {
      expect(link).toHaveAttribute("href", "/sign-in?mode=sign-up");
    }
  });

  it("includes the shared public nav so a visitor can always get back to the other public pages", () => {
    render(<Page />);
    expect(screen.getAllByRole("link", { name: "How It Works" }).length).toBeGreaterThan(0);
  });
});
