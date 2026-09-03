import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import PricingPage from "../pricing/page";

const getCurrentUserMock = vi.fn();

vi.mock("@/app/lib/auth", () => ({
  getCurrentUser: () => getCurrentUserMock(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

/**
 * Public Web M2: How It Works, Features, and About are now real pages
 * with their own dedicated test files (see
 * `app/how-it-works/__tests__/page.test.tsx`,
 * `app/features/__tests__/page.test.tsx`,
 * `app/about/__tests__/page.test.tsx`). Only Pricing remains an M1-style
 * "coming soon" placeholder (M3 scope) -- this file now covers Pricing
 * alone.
 */
describe("Pricing placeholder page", () => {
  beforeEach(() => {
    getCurrentUserMock.mockReset();
    getCurrentUserMock.mockResolvedValue(null);
  });

  it("renders a real heading and a path back into account creation, never a dead end", async () => {
    render(await PricingPage());
    expect(screen.getByRole("heading", { level: 1, name: "Pricing" })).toBeInTheDocument();
    const createAccountLinks = screen.getAllByRole("link", { name: "Create Account" });
    expect(createAccountLinks.length).toBeGreaterThan(0);
    for (const link of createAccountLinks) {
      expect(link).toHaveAttribute("href", "/sign-in?mode=sign-up");
    }
  });

  it("includes the shared public nav so a visitor can always get back to the other public pages", async () => {
    render(await PricingPage());
    expect(screen.getAllByRole("link", { name: "How It Works" }).length).toBeGreaterThan(0);
  });

  it("Web M1 routing correction: a signed-in visitor sees the auth-aware nav here too", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });
    render(await PricingPage());
    expect(screen.getAllByRole("link", { name: "Open MANSA" }).length).toBeGreaterThan(0);
  });

  it("deliberately shows no price -- fabricating one ahead of the real M3 page would be worse than 'coming soon'", async () => {
    render(await PricingPage());
    expect(screen.queryByText(/\$\d/)).not.toBeInTheDocument();
  });
});
