import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import RootPage from "../page";

const getCurrentUserMock = vi.fn();

vi.mock("@/app/lib/auth", () => ({
  getCurrentUser: () => getCurrentUserMock(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

/**
 * Public Web M1 routing correction (Mac's live mobile validation,
 * 2026-09-02): `/` previously redirected a signed-in visitor to
 * `/onboarding`/`/today` before ever rendering this page -- the
 * confirmed root cause of "authenticated `/` shows Today instead of the
 * landing page." `/` must now render for every visitor, full stop; the
 * only thing that legitimately varies is the nav/CTA wording. These
 * tests cover scenarios 1-3 of HQ's requested regression matrix.
 * Scenarios 4-6 (signed-out protected route -> /sign-in, a fully
 * onboarded user reaching protected routes normally, an
 * onboarding-required user's existing onboarding redirect) are
 * unchanged by this fix and stay covered by their own existing,
 * untouched tests: `app/lib/__tests__/getCurrentUser.test.ts`
 * (`requireUser` -> `/sign-in`) and `app/lib/__tests__/auth.test.ts`
 * (`resolveRootDestination`, still used by `/sign-in` and `/onboarding`
 * themselves to bounce a user who's already past that step).
 */
describe("RootPage (/)", () => {
  beforeEach(() => {
    getCurrentUserMock.mockReset();
  });

  it("scenario 1: signed-out GET / renders the public landing page", async () => {
    getCurrentUserMock.mockResolvedValue(null);

    render(await RootPage());

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "See the game.Know the market.Own the decision.",
    );
    const createAccountLinks = screen.getAllByRole("link", { name: "Create Account" });
    expect(createAccountLinks.length).toBeGreaterThan(0);
    expect(createAccountLinks[0]).toHaveAttribute("href", "/sign-in?mode=sign-up");
    expect(screen.queryByRole("link", { name: "Open MANSA" })).not.toBeInTheDocument();
  });

  it("scenario 2: signed-in GET / ALSO renders the public landing page -- never redirected away, the real bug being fixed here", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });

    render(await RootPage());

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "See the game.Know the market.Own the decision.",
    );
  });

  it("scenario 3: a signed-in visitor's primary CTA is 'Open MANSA' linking to /today, not 'Create Account'", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });

    render(await RootPage());

    expect(screen.queryByRole("link", { name: "Create Account" })).not.toBeInTheDocument();
    const openMansaLinks = screen.getAllByRole("link", { name: "Open MANSA" });
    expect(openMansaLinks.length).toBeGreaterThan(0);
    for (const link of openMansaLinks) {
      expect(link).toHaveAttribute("href", "/today");
    }
  });
});
