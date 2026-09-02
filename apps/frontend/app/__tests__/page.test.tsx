import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import RootPage from "../page";

const getCurrentUserMock = vi.fn();
const getUserProfileMock = vi.fn();
const redirectMock = vi.fn((destination: string) => {
  throw new Error(`REDIRECT:${destination}`);
});

vi.mock("@/app/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/app/lib/auth")>("@/app/lib/auth");
  return {
    ...actual,
    getCurrentUser: () => getCurrentUserMock(),
  };
});

vi.mock("@/app/lib/api", () => ({
  getUserProfile: () => getUserProfileMock(),
}));

vi.mock("next/navigation", () => ({
  redirect: (destination: string) => redirectMock(destination),
  usePathname: () => "/",
}));

/**
 * Public Web M1 -- `/` is now a real branching point (marketing page vs.
 * product-entry redirect), not pure routing. `resolveRootDestination`
 * itself stays covered by its own existing unit tests
 * (`app/lib/__tests__/auth.test.ts`, untouched); these tests cover the
 * one thing that actually changed: which branch renders content versus
 * redirects.
 */
describe("RootPage (/)", () => {
  beforeEach(() => {
    getCurrentUserMock.mockReset();
    getUserProfileMock.mockReset();
    redirectMock.mockClear();
  });

  it("renders the public landing page for a signed-out visitor, never redirecting to /sign-in", async () => {
    getCurrentUserMock.mockResolvedValue(null);

    render(await RootPage());

    expect(getUserProfileMock).not.toHaveBeenCalled();
    expect(redirectMock).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "See the game.Know the market.Own the decision.",
    );
    const createAccountLinks = screen.getAllByRole("link", { name: "Create Account" });
    expect(createAccountLinks.length).toBeGreaterThan(0);
    expect(createAccountLinks[0]).toHaveAttribute("href", "/sign-in?mode=sign-up");
  });

  it("preserves existing behavior: a signed-in user with incomplete onboarding is redirected to /onboarding, never shown the landing page", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });
    getUserProfileMock.mockResolvedValue({ kind: "ok", data: { onboarding_completed_at: null } });

    await expect(RootPage()).rejects.toThrow("REDIRECT:/onboarding");
    expect(redirectMock).toHaveBeenCalledWith("/onboarding");
  });

  it("preserves existing behavior: a fully onboarded signed-in user is redirected to /today, never shown the landing page", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });
    getUserProfileMock.mockResolvedValue({
      kind: "ok",
      data: { onboarding_completed_at: "2026-08-01T00:00:00Z" },
    });

    await expect(RootPage()).rejects.toThrow("REDIRECT:/today");
    expect(redirectMock).toHaveBeenCalledWith("/today");
  });

  it("preserves existing behavior: a signed-in user with no readable profile row is redirected to /onboarding", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });
    getUserProfileMock.mockResolvedValue({ kind: "error", error: "not found" });

    await expect(RootPage()).rejects.toThrow("REDIRECT:/onboarding");
  });
});
