import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import HowItWorksPage from "../how-it-works/page";
import FeaturesPage from "../features/page";
import PricingPage from "../pricing/page";
import AboutPage from "../about/page";

const getCurrentUserMock = vi.fn();

vi.mock("@/app/lib/auth", () => ({
  getCurrentUser: () => getCurrentUserMock(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

/**
 * Public Web M1 -- M2 will build the real How It Works / Features /
 * Pricing / About content. These four are clearly-handled placeholders,
 * never a broken link or a 404; these tests only prove that. Each page
 * is async (Web M1 routing correction) so its shared `PublicNav` can be
 * auth-aware, exactly like `/` -- rendered here via `await Page()`, the
 * same pattern `app/__tests__/page.test.tsx` already establishes for
 * `RootPage`.
 */
describe.each([
  ["How It Works", HowItWorksPage],
  ["Features", FeaturesPage],
  ["Pricing", PricingPage],
  ["About", AboutPage],
])("%s placeholder page", (title, Page) => {
  beforeEach(() => {
    getCurrentUserMock.mockReset();
    getCurrentUserMock.mockResolvedValue(null);
  });

  it("renders a real heading and a path back into account creation, never a dead end", async () => {
    render(await Page());
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    const createAccountLinks = screen.getAllByRole("link", { name: "Create Account" });
    expect(createAccountLinks.length).toBeGreaterThan(0);
    for (const link of createAccountLinks) {
      expect(link).toHaveAttribute("href", "/sign-in?mode=sign-up");
    }
  });

  it("includes the shared public nav so a visitor can always get back to the other public pages", async () => {
    render(await Page());
    expect(screen.getAllByRole("link", { name: "How It Works" }).length).toBeGreaterThan(0);
  });

  it("Web M1 routing correction: a signed-in visitor sees the auth-aware nav here too, not a stale Create Account prompt in the header", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });
    render(await Page());
    expect(screen.getAllByRole("link", { name: "Open MANSA" }).length).toBeGreaterThan(0);
  });
});
